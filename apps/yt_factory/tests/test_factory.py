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
                 "title": "Yonaguni Monument Terraces", "creator": "Ann", "foreign_landing_url": "https://commons/x"}]})
        return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/jpeg"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await visuals.real_photo(http, "yonaguni terraces", "short", tmp_path)

    got = asyncio.run(go())
    assert got and "Ann" in got["credit"] and "CC BY 4.0" in got["credit"]
    assert "Monument Terraces" in got["credit"]
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


def test_wikipedia_429_is_retried_then_reported_as_unavailable(tmp_path, monkeypatch):
    import httpx

    from yt_factory import factcheck

    monkeypatch.delenv("YTF_OFFLINE", raising=False)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(factcheck.asyncio, "sleep", fake_sleep)
    factcheck._CACHE.clear()
    factcheck._SEM = None

    async def go(handler):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await factcheck.research_notes(http, "The 1518 dancing plague in Strasbourg", "en")

    with pytest.raises(factcheck.SourcesUnavailable):
        asyncio.run(go(lambda req: httpx.Response(429, headers={"retry-after": "2"})))
    assert 2.0 in sleeps                                         # rispetta Retry-After

    calls = []

    def ok(req):
        calls.append(req.url.params.get("q"))
        if "search" in req.url.path:
            return httpx.Response(200, json={"pages": [{"key": "Dancing_plague_of_1518", "title": "Dancing plague of 1518"}]})
        return httpx.Response(200, json={"source": "'''The dancing plague''' happened in [[Strasbourg]]. " * 20})

    notes = asyncio.run(go(ok))
    assert "Dancing plague of 1518" in notes and "Strasbourg" in notes
    assert calls[0] == "1518 dancing plague Strasbourg"          # query ridotta alle parole chiave


def test_weak_hooks_trigger_a_second_round(tmp_path):
    s = _settings(tmp_path)
    rounds = []

    class Brain(OfflineBrain):
        async def ask_json(self, system, user, *, schema, max_tokens=0, model=None, temperature=0.0):
            if '"hooks"' in schema:
                rounds.append(user)
                return {"hooks": ["vago 1", "vago 2"] if len(rounds) == 1 else ["forte", "medio"]}
            if '"scores"' in schema:
                return {"scores": [3, 2], "why": "troppo vaghi"} if "vago" in user else {"scores": [8, 5]}
            return await super().ask_json(system, user, schema=schema)

    f = pipeline.Factory(s, brain=Brain())
    assert asyncio.run(f.best_hook(s.channel("mysteries"), {"topic": "t"}, "#1")) == "forte"
    assert len(rounds) == 2 and "troppo vaghi" in rounds[1]
    f.db.close()


def test_real_photo_rejects_off_topic_titles(tmp_path, monkeypatch):
    import httpx

    from yt_factory import visuals

    monkeypatch.delenv("YTF_OFFLINE", raising=False)

    def handler(req):
        return httpx.Response(200, json={"results": [
            {"url": "https://img/t.jpg", "width": 2000, "height": 1500, "license": "by",
             "title": "Woolpit Steam Rally, Vintage Tractors", "tags": [{"name": "suffolk"}]}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await visuals.real_photo(http, "Woolpit Suffolk village", "short", tmp_path)

    assert asyncio.run(go()) is None


def test_github_models_provider_caps_output_and_scopes_limits(monkeypatch):
    from yt_factory.ghmodels import GitHubModels, github_models_providers

    monkeypatch.delenv("GITHUB_MODELS_TOKEN", raising=False)
    assert github_models_providers() == []
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "ghs_x")
    (p,) = github_models_providers()
    assert isinstance(p, GitHubModels) and p.url == "https://models.github.ai/inference/chat/completions"
    assert p.adapt_payload({"max_tokens": 9000})["max_tokens"] == 4000
    assert p.adapt_payload({"max_tokens": 100})["max_tokens"] == 100
    assert p.rate_limit_scope("") == "model"


def test_telegram_report_sends_summary_and_videos(tmp_path, monkeypatch):
    import httpx

    from yt_factory import notify

    monkeypatch.delenv("YTF_OFFLINE", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    video = tmp_path / "00001_short.mp4"
    video.write_bytes(b"mp4")
    video.with_suffix(".json").write_text(json.dumps({"description": "desc"}))
    sent = []

    def handler(req):
        sent.append((req.url.path.rsplit("/", 1)[-1], req.content))
        return httpx.Response(200, json={"ok": True})

    res = pipeline.RunResult("mysteries", produced=[{"channel": "mysteries", "title": "T", "file": str(video),
                                                     "youtube_id": None}], errors=["e"])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await notify.daily_report(http, [res])

    asyncio.run(go())
    assert [m for m, _ in sent] == ["sendMessage", "sendVideo"]
    assert b"desc" in sent[1][1] and b"chat_id" in sent[1][1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="serve ffmpeg")
def test_qc_blocks_black_silent_and_wrong_format(tmp_path, monkeypatch):
    import subprocess

    from yt_factory import qc

    monkeypatch.delenv("YTF_OFFLINE_TTS", raising=False)
    monkeypatch.delenv("YTF_NO_AI_IMAGES", raising=False)
    bad = tmp_path / "bad.mp4"   # 6 s di nero orizzontale con audio muto
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=1920x1080:d=6",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "6", "-shortest", str(bad)], check=True)
    r = qc.inspect(bad, "short", 6.0, fallback_ratio=0.8)
    text = " ".join(i["issue"] for i in r["issues"])
    assert not r["ok"]
    assert "risoluzione" in text and "nero" in text and "silenzio" in text and "presentazione" in text
    good = tmp_path / "good.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=5",
                    "-f", "lavfi", "-i", "sine=f=220:d=5", "-shortest", str(good)], check=True)
    assert qc.inspect(good, "short", 5.0)["ok"]


def test_deterministic_grounding_checks():
    from yt_factory.factcheck import numbers_not_in_notes, quote_in_notes
    notes = "In 2011, 98% of people reported earworms. Lyrics caused 73.7% of cases. Population 1,234,567 in 1990."
    spoken = "Il 98% delle persone, il 73,7% dei casi, in 3 secondi, nel 2015 il campo salì del 40%, 1.234.567 nel 1990"
    assert numbers_not_in_notes(spoken, notes) == ["2015", "40%"]   # cifre inventate; "3 secondi" è un'espressione
    assert quote_in_notes("Lyrics caused 73.7% of cases", notes)
    assert not quote_in_notes("workers saw a tall glowing figure at the pumps", notes)


def test_story_without_quotes_in_sources_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("YTF_OFFLINE", raising=False)
    s = _settings(tmp_path)

    class Brain(OfflineBrain):
        async def ask_json(self, system, user, *, schema, max_tokens=0, model=None, temperature=0.0):
            if '"quote"' in schema:
                return {"angle": "a", "twist": "t", "payoff": "p", "facts": [
                    {"fact": f"f{i}", "quote": "a glowing figure measured by a 2015 electromagnetic test"} for i in range(4)]}
            return await super().ask_json(system, user, schema=schema)

    f = pipeline.Factory(s, brain=Brain())

    async def notes(*a, **k):
        return "### Elizabeth, New Jersey\\nElizabeth is a city in Union County, New Jersey. " * 20

    monkeypatch.setattr(pipeline.factcheck, "research_notes", notes)

    async def go():
        import httpx
        async with httpx.AsyncClient() as f.http:
            return await f.produce(s.channel("mysteries"), {"topic": "NJ glowing figure"}, "short", "12:30", "2030-01-01", {})

    assert asyncio.run(go()) is None
    assert "fonti" in f.db.videos("mysteries")[0]["error"]
    f.db.close()


def test_off_topic_sources_are_detected():
    from yt_factory.factcheck import notes_on_topic
    notes = "### Agriculture in ancient Rome (Wikipedia en)\nWheat...\n### Trade route (Wikipedia en)\nSilk..."
    assert not notes_on_topic(notes, "Claude-only side hustle profit experiment")
    assert notes_on_topic("### Endowment effect (Wikipedia en)\n...", "endowment effect subscriptions")
    assert notes_on_topic("### Felix Moncla (Wikipedia en)\n...", "Felix Moncla Kinross incident")


def test_keyless_models_are_only_a_fallback_when_github_models_exist(monkeypatch):
    from yt_factory.llm import Brain

    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "ghs_x")
    b = Brain()
    pri = {p.name: p.priority for p in b.llm.providers}
    assert pri["github"] < pri["kilo"] and pri["github"] < pri["ovh"]


def test_motion_cards_only_use_data_spoken_in_the_scene():
    from yt_factory.motion import validate
    scene = "In 2011 the Durbin Amendment cut swipe fees from 44¢ to 21¢ and saved merchants $9.4 billion."
    assert validate({"kind": "stat", "value": "$9.4 billion", "label": "saved"}, scene)["value"] == "$9.4 billion"
    assert validate({"kind": "stat", "value": "$12 billion", "label": "saved"}, scene) is None       # cifra inventata
    ok = validate({"kind": "compare", "a": {"value": "44¢", "label": "Before"}, "b": {"value": "21¢", "label": "After"}}, scene)
    assert ok and ok["b"]["value"] == "21¢"
    assert validate({"kind": "compare", "a": {"value": "44¢"}, "b": {"value": "30¢"}}, scene) is None
    assert validate({"kind": "timeline", "points": [{"year": "2011", "label": "x"}, {"year": "2015", "label": "y"}]}, scene) is None
    assert validate({"kind": "quote", "text": "nobody expected this"}, scene) is None
    assert validate({"kind": "chart3d"}, scene) is None


def test_card_scene_is_a_single_shot(tmp_path):
    card = tmp_path / "card_01.mp4"
    shots = render.plan_shots([(0.0, 6.0), (6.0, 12.0)], [{"image": None}, {"image": None}], 2.8, {1: card})
    assert [s["kind"] for s in shots if s["scene"] == 1] == ["card"]
    assert shots[-1]["path"] == card and shots[-1]["end"] == 12.0
    assert len([s for s in shots if s["scene"] == 0]) == 2


def test_pipeline_keeps_first_and_last_scene_free_of_cards(tmp_path):
    s = _settings(tmp_path)
    f = pipeline.Factory(s, brain=OfflineBrain())
    scenes = [{"text": "Hook 2011."}, {"text": "Fees fell from 44¢ to 21¢."}, {"text": "End 2011."}]
    cards = f.validate_cards(s.channel("money"), scenes, {"cards": [
        {"scene": 0, "kind": "stat", "value": "2011"},
        {"scene": 1, "kind": "compare", "a": {"value": "44¢", "label": "a"}, "b": {"value": "21¢", "label": "b"}},
        {"scene": 2, "kind": "stat", "value": "2011"}]}, "#1")
    assert list(cards) == ["1"]
    f.db.close()


def test_split_beats_one_image_per_sentence():
    beats = pipeline.split_beats([
        {"text": "In 1953 a jet took off from Kinross. Vanished. Radar lost it over Lake Superior.", "on_screen": "1953"},
        {"text": "The Air Force blamed a crash into the lake.", "on_screen": ""}])
    assert [b["text"] for b in beats] == ["In 1953 a jet took off from Kinross.",
                                         "Vanished. Radar lost it over Lake Superior.",
                                         "The Air Force blamed a crash into the lake."]
    assert beats[0]["on_screen"] == "1953" and beats[1]["on_screen"] == ""


def test_scene_times_follow_spoken_words():
    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(10)]
    t = render.scene_times([{"text": "one two"}, {"text": "three four five six seven eight nine ten!!!!!!!!!!!!"}],
                           words, 5.2)
    assert t[0][1] == 1.0          # cambio immagine esattamente all'inizio della terza parola detta


def test_visual_qa_replaces_mismatched_images(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    calls = []

    class Brain(OfflineBrain):
        async def ask_vision(self, prompt, image, *, schema, max_tokens=0):
            calls.append(prompt)
            return {"match": "jet" in str(image), "shows": "x", "fix_prompt": "1950s F-89 jet over a lake"}

    f = pipeline.Factory(s, brain=Brain())

    async def fake_ai(http, prompt, style, fmt, seed, cache):
        return tmp_path / "regenerated_jet.jpg"

    monkeypatch.setattr(pipeline.visuals, "ai_image", fake_ai)
    assets = [{"image": tmp_path / "jet.jpg"}, {"image": tmp_path / "fog.jpg"},
              {"image": tmp_path / "photo.jpg", "image2": tmp_path / "ai_jet.jpg", "photo": True, "credit": "c"}]
    scenes = [{"text": "A jet took off."}, {"text": "The jet vanished."}, {"text": "Radar saw the jet."}]

    async def go():
        import httpx
        async with httpx.AsyncClient() as f.http:
            await f.visual_qa(s.channel("mysteries"), scenes, {}, assets, "short", 1)

    asyncio.run(go())
    assert assets[0]["image"].name == "jet.jpg"                  # corrispondeva: resta
    assert assets[1]["image"].name == "regenerated_jet.jpg"      # nebbia generica: rifatta
    assert assets[2]["image"].name == "ai_jet.jpg" and not assets[2]["photo"]   # foto fuori tema -> immagine AI
    assert len(calls) == 3 and "Radar saw the jet" in calls[2]
    f.db.close()
