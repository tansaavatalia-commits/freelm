"""Test senza rete: parsing JSON, sottotitoli, orari, quota, descrizioni e una giornata completa offline."""
import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from yt_factory import config, pipeline, render
from yt_factory.db import DB
from yt_factory.llm import extract_json
from yt_factory.offline import OfflineBrain
from yt_factory.tts import Word
from yt_factory.youtube import _tags, ypp_progress


def test_extract_json_variants():
    assert extract_json('ecco:\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('blah {"t": "con } graffa", "n": {"x": 1}} coda') == {"t": "con } graffa", "n": {"x": 1}}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json('{"a": 1')


def test_similarity_dedupe():
    assert pipeline._similar("Perché i gatti fanno le fusa", "perché i gatti fanno le fusa?")
    assert pipeline._similar("Il mistero del triangolo delle Bermuda", "Triangolo delle Bermuda: il mistero")
    assert not pipeline._similar("Il mistero del triangolo delle Bermuda", "Come risparmiare sulla spesa")


def test_score_normalisation():
    assert pipeline._score(75) == 7.5
    assert pipeline._score("8") == 8
    assert pipeline._score(None) == 0


def test_scene_times_cover_audio():
    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(20)]
    scenes = [{"text": "a" * 10}, {"text": "b" * 30}, {"text": "c" * 10}]
    t = render.scene_times(scenes, words, 10.5)
    assert t[0][0] == 0 and t[-1][1] == 10.5
    assert all(a < b for a, b in t) and all(t[i][1] == t[i + 1][0] for i in range(2))


def test_ass_breaks_groups_at_sentence_end(tmp_path):
    words = [Word("Uno.", 0, 0.3), Word("Due", 0.4, 0.6), Word("tre", 0.7, 0.9)]
    out = tmp_path / "c.ass"
    render.build_ass(words, [{"text": "x", "on_screen": "ciao {x}"}], [(0, 1)], "short", ["#000000", "#ffcc00"], out)
    text = out.read_text()
    caps = [ln for ln in text.splitlines() if ln.startswith("Dialogue: 2")]
    assert len(caps) == 3
    assert "DUE" not in caps[0] and "UNO" not in caps[1]   # "Uno." chiude la frase: gruppo separato
    assert "CIAO (X)" in text                               # graffe neutralizzate (sono comandi ASS)


def test_tags_limit_and_ypp():
    tags = _tags(["#" + "x" * 50] * 20)
    assert sum(len(t) + 2 for t in tags) <= 480 and not tags[0].startswith("#")
    p = ypp_progress({"subscribers": 1200, "watch_hours_365d": 10, "shorts_views_90d": 11_000_000})
    assert p["eligible_ads"] and p["eligible_fan_funding"]
    assert not ypp_progress({"subscribers": 400})["eligible_fan_funding"]


def test_quota_and_idempotent_counts(tmp_path):
    db = DB(tmp_path / "f.sqlite")
    db.spend_quota("p", "2026-01-01", 1600)
    db.spend_quota("p", "2026-01-01", 1600)
    assert db.quota_used("p", "2026-01-01") == 3200
    vid = db.add_video("c", "2026-01-01", "short", "topic")
    assert db.count_day("c", "2026-01-01", "short") == 0
    db.update_video(vid, status="rendered", data={"k": "v"})
    assert db.count_day("c", "2026-01-01", "short") == 1
    assert db.video(vid)["data"] == {"k": "v"}


def _settings(tmp_path):
    os.environ["YTF_DATA_DIR"] = str(tmp_path)
    return config.load()


def test_description_and_publish_time(tmp_path):
    s = _settings(tmp_path)
    f = pipeline.Factory(s, brain=OfflineBrain())
    ch = s.channel("fatti")
    ch.affiliate_links = ["Libro: https://example.com"]
    d = f.description(ch, {"description": "Testo #curiosità bello", "hashtags": ["curiosità", "#Scienza"]}, "short")
    assert d.endswith("#shorts #curiosità #Scienza")
    assert "commissione" in d and d.count("#curiosità") == 1
    when = f.publish_time("2000-01-01", "12:30")  # slot passato -> fra 30 minuti, comunque nel futuro
    assert when.endswith("Z") and when > "2000-01-02"
    f.db.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="serve ffmpeg")
def test_offline_day_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("YTF_OFFLINE_TTS", "1")
    monkeypatch.setenv("YTF_OFFLINE", "1")
    monkeypatch.setenv("YTF_NO_AI_IMAGES", "1")
    s = _settings(tmp_path)

    async def no_trends(ch, http, log=None):
        return {"videos": [], "searches": [], "live_youtube": False}

    monkeypatch.setattr(pipeline.trends, "collect", no_trends)
    f = pipeline.Factory(s, dry_run=True, brain=OfflineBrain())

    async def go():
        try:
            return await f.daily([s.channel("fatti")], per_channel=2)
        finally:
            await f.close()

    (res,) = asyncio.run(go())
    assert len(res.produced) == 2, res.errors
    for v in res.produced:
        p = Path(v["file"])
        assert p.exists() and render.duration(p) > 5
        meta = json.loads(p.with_suffix(".json").read_text())
        assert "#shorts" in meta["description"]
    # rilanciare lo stesso giorno non riproduce video già fatti
    f2 = pipeline.Factory(s, dry_run=True, brain=OfflineBrain())

    async def again():
        try:
            return await f2.daily([s.channel("fatti")], per_channel=2)
        finally:
            await f2.close()

    (res2,) = asyncio.run(again())
    assert res2.produced == []


def test_upload_request_shape(tmp_path, monkeypatch):
    """Upload ripristinabile: token -> sessione -> PUT; AI dichiarata, non per bambini, programmato."""
    import httpx

    from yt_factory.youtube import YouTube

    monkeypatch.setenv("YT_CLIENT_ID", "cid")
    monkeypatch.setenv("YT_CLIENT_SECRET", "sec")
    monkeypatch.setenv("YT_REFRESH_TOKEN_FATTI", "rt")
    s = _settings(tmp_path)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com":
            assert b"refresh_token=rt" in req.content
            return httpx.Response(200, json={"access_token": "AT"})
        if req.method == "POST":
            assert req.headers["authorization"] == "Bearer AT"
            seen["meta"] = json.loads(req.content)
            return httpx.Response(200, headers={"Location": "https://upload.example/session"})
        seen["bytes"] = len(req.content)
        return httpx.Response(200, json={"id": "VID123"})

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await YouTube(s.channel("fatti"), http).upload(
                video, title="T", description="D", tags=["#a", "b"], category_id="27", language="it",
                privacy="public", publish_at="2030-01-01T10:00:00Z")

    assert asyncio.run(go()) == "VID123"
    st = seen["meta"]["status"]
    assert st["privacyStatus"] == "private" and st["publishAt"] == "2030-01-01T10:00:00Z"
    assert st["containsSyntheticMedia"] is True and st["selfDeclaredMadeForKids"] is False
    assert seen["meta"]["snippet"]["tags"] == ["a", "b"] and seen["bytes"] == 1000


def test_plan_shots_alternate_and_cover_timeline(tmp_path):
    img, clip = tmp_path / "i.jpg", tmp_path / "c.mp4"
    times = [(0.0, 7.5), (7.5, 9.5)]
    shots = render.plan_shots(times, [{"image": img, "stock": clip}, {"image": None, "stock": None}], 2.8)
    assert shots[0]["start"] == 0 and shots[-1]["end"] == 9.5
    assert all(s["end"] - s["start"] <= 3.1 for s in shots)
    first = [s for s in shots if s["scene"] == 0]
    assert [s["kind"] for s in first] == ["image", "video", "image"]       # alterna AI e stock
    assert len({s["motion"] for s in shots}) == len(shots)                 # movimento diverso a ogni taglio
    assert shots[-1]["path"] is None                                       # fallback: grafica generata


def test_ai_image_crops_watermark_and_caches(tmp_path, monkeypatch):
    import io

    import httpx
    from PIL import Image

    from yt_factory import visuals

    monkeypatch.delenv("YTF_NO_AI_IMAGES", raising=False)
    calls = []

    def handler(req):
        calls.append(str(req.url))
        buf = io.BytesIO()
        Image.new("RGB", (768, 1472), (200, 10, 10)).save(buf, "JPEG")
        return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/jpeg"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            a = await visuals.ai_image(http, "foggy castle", "dark cinematic", "short", 7, tmp_path)
            b = await visuals.ai_image(http, "foggy castle", "dark cinematic", "short", 7, tmp_path)
            return a, b

    a, b = asyncio.run(go())
    assert a == b and len(calls) == 1                       # cache: una sola richiesta
    w, h = Image.open(a).size
    assert w >= 1080 * 1.15 - 1 and h >= 1920 * 1.15 - 1    # pronto per il movimento di camera
    assert "foggy%20castle" in calls[0] and "seed=7" in calls[0]


def test_hook_panel_picks_highest_average(tmp_path):
    s = _settings(tmp_path)

    class Brain(OfflineBrain):
        async def ask_json(self, system, user, *, schema, max_tokens=0, model=None, temperature=0.0):
            if '"hooks"' in schema:
                return {"hooks": ["debole", "forte", "medio"]}
            if '"scores"' in schema:
                return {"scores": {"chat": [2, 9, 6], "large": [3, 8, 9], "fast": [1, 9, 5]}[model]}
            return await super().ask_json(system, user, schema=schema)

    f = pipeline.Factory(s, brain=Brain())
    hook = asyncio.run(f.best_hook(s.channel("mysteries"), {"topic": "t"}, "#1"))
    assert hook == "forte"
    f.db.close()


def test_english_channels_configured(tmp_path):
    s = _settings(tmp_path)
    langs = {c.id: c.language for c in s.channels}
    assert list(langs.values()).count("en") == 2 and langs["fatti"] == "it"
    assert all(c.voice.startswith(c.language) for c in s.channels)


def test_clean_scenes_strips_labels_and_forces_hook():
    scenes = [{"text": "Off the coast of Japan, something sleeps.", "on_screen": "X"},
              {"text": "Kimura says it was carved. DISPUTED.", "on_screen": ""},
              {"text": "[dramatic pause] NASA confirmed it in 1998.", "on_screen": ""},
              {"text": "MAINSTREAM VIEW.", "on_screen": ""}, "junk"]
    out = pipeline.clean_scenes(scenes, hook="It was carved by hand. Or was it?")
    spoken = " ".join(s["text"] for s in out)
    assert out[0]["text"] == "It was carved by hand. Or was it?"          # l'hook vincitore apre sempre il video
    assert "DISPUTED" not in spoken and "MAINSTREAM" not in spoken and "pause" not in spoken
    assert "NASA confirmed it in 1998." in spoken                          # le sigle dentro una frase restano
    assert len(out) == 4


def test_real_photo_skips_banners_and_credits_cc_by(tmp_path, monkeypatch):
    import io

    import httpx
    from PIL import Image

    from yt_factory import visuals

    monkeypatch.delenv("YTF_OFFLINE", raising=False)
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), (10, 10, 200)).save(buf, "JPEG")

    def handler(req):
        if req.url.host == "api.openverse.org":
            assert "by" in req.url.params["license"] and "sa" not in req.url.params["license"]
            return httpx.Response(200, json={"results": [
                {"url": "https://img/banner.jpg", "width": 3000, "height": 400, "license": "cc0"},
                {"url": "https://img/ok.jpg", "width": 1600, "height": 1200, "license": "by", "license_version": "4.0",
                 "title": "Terraces", "creator": "Ann", "foreign_landing_url": "https://commons/x"}]})
        return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/jpeg"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await visuals.real_photo(http, "yonaguni terraces", "short", tmp_path)

    got = asyncio.run(go())
    assert got and "Ann" in got["credit"] and "CC BY 4.0" in got["credit"]
    w, h = Image.open(got["path"]).size
    assert h >= 1920 * 1.15 - 1


def test_description_lists_photo_credits(tmp_path):
    s = _settings(tmp_path)
    f = pipeline.Factory(s, brain=OfflineBrain())
    d = f.description(s.channel("mysteries"), {"description": "x", "hashtags": []}, "short", ["\"T\" by Ann, CC BY 4.0"])
    assert "Photos: \"T\" by Ann, CC BY 4.0" in d
    f.db.close()


def test_keeps_best_version_when_revisions_get_worse(tmp_path, monkeypatch):
    monkeypatch.setenv("YTF_OFFLINE", "1")
    s = _settings(tmp_path)
    s.writer_models = ["chat"]
    s.min_quality_score = 8
    scores = iter([7, 5, 4])

    class Brain(OfflineBrain):
        async def ask_json(self, system, user, *, schema, max_tokens=0, model=None, temperature=0.0):
            if '"watch_to_end"' in schema:
                return {"score": next(scores), "verdict": "rewrite", "fixes": ["x"]}
            if '"scenes"' in schema:
                tag = "REVISED" if "REVISE" in user else "FIRST"
                return {"scenes": [{"text": f"{tag} line {i}.", "on_screen": ""} for i in range(4)]}
            return await super().ask_json(system, user, schema=schema)

    f = pipeline.Factory(s, brain=Brain())
    seen = {}

    async def fake_render(**kw):
        seen["scenes"] = kw["scenes"]
        raise RuntimeError("stop qui")

    monkeypatch.setattr(pipeline.render, "render", fake_render)
    monkeypatch.setattr(pipeline.tts, "synthesize", lambda *a, **k: _words())

    async def _words():
        from yt_factory.tts import Word
        return [Word("x", 0, 1)]

    async def go():
        import httpx
        async with httpx.AsyncClient() as f.http:
            await f.produce(s.channel("mysteries"), {"topic": "t"}, "short", "12:30", "2030-01-01", {})

    with pytest.raises(RuntimeError, match="stop qui"):
        asyncio.run(go())
    assert "FIRST" in seen["scenes"][1]["text"]   # la bozza da 7 batte le revisioni da 5 e 4
    f.db.close()


def test_clean_wikitext():
    from yt_factory.factcheck import clean_wikitext
    src = ("{{Short description|x}}'''Track 61''' is a [[railway platform|platform]] under the [[Waldorf Astoria]]."
           "<ref>{{cite web|url=x}}</ref> Used by [[Franklin D. Roosevelt|FDR]].\n== History ==\nBuilt in 1910s."
           "\n== References ==\njunk")
    t = clean_wikitext(src)
    assert t.startswith("Track 61 is a platform under the Waldorf Astoria.") and "FDR" in t
    assert "History:" in t and "junk" not in t and "{{" not in t and "<ref" not in t


def test_concept_without_sources_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("YTF_OFFLINE", raising=False)
    s = _settings(tmp_path)
    f = pipeline.Factory(s, brain=OfflineBrain())

    async def no_notes(*a, **k):
        return ""

    monkeypatch.setattr(pipeline.factcheck, "research_notes", no_notes)

    async def go():
        import httpx
        async with httpx.AsyncClient() as f.http:
            return await f.produce(s.channel("mysteries"), {"topic": "invented"}, "short", "12:30", "2030-01-01", {})

    assert asyncio.run(go()) is None
    assert f.db.videos("mysteries")[0]["status"] == "rejected"
    f.db.close()
