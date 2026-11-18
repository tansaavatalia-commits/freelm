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
