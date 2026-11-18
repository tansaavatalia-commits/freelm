"""Orchestratore: i team di ogni canale lavorano in parallelo, e dentro ogni canale più video sono in produzione
contemporaneamente.

Per ogni canale, ogni giorno:
  analytics  -> lezioni dai video già pubblicati (cosa ha funzionato)
  ricerca    -> dati di tendenza live + analisi dei pattern virali
  creativo   -> idee (senza ripetizioni) -> script (Short) o scaletta + capitoli in parallelo (video lungo)
  qualità    -> revisione con voto; riscrittura guidata se sotto soglia; scarto se viola le policy
  SEO        -> titolo, descrizione, tag, hashtag, testo miniatura, commento
  produzione -> voce neurale + sottotitoli animati + montaggio ffmpeg (+ miniatura)
  pubblicazione -> upload programmato negli orari migliori, dichiarazione AI, commento, controllo quota
  crescita   -> (settimanale) avanzamento verso la monetizzazione e priorità
"""
from __future__ import annotations

import asyncio
import difflib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

from . import agents as A
from . import render, trends, tts
from .config import APP_DIR, Channel, Settings
from .db import DB
from .llm import Brain
from .youtube import YouTube, YouTubeError, configured, project_of, ypp_progress


def _log(channel: str, team: str, msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} [{channel:<8}] {team:<13} {msg}", flush=True)


@dataclass
class RunResult:
    channel: str
    produced: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Factory:
    def __init__(self, settings: Settings, *, dry_run: bool = True, brain: Optional[Brain] = None):
        self.s = settings
        self.dry_run = dry_run
        self.db = DB(settings.data_dir / "factory.sqlite")
        self.brain = brain or Brain(settings.llm_model, concurrency=6,
                                    log=lambda m: _log("*", "llm", m))
        self.render_sem = asyncio.Semaphore(settings.max_parallel_renders)
        self.quota_lock = asyncio.Lock()
        self.tz = ZoneInfo(settings.timezone)
        self.http: httpx.AsyncClient

    # ================================================================== entry point
    async def daily(self, channels: List[Channel], *, per_channel: Optional[int] = None,
                    force_long: bool = False) -> List[RunResult]:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as self.http:
            results = await asyncio.gather(*(self._channel_day(ch, per_channel, force_long) for ch in channels))
        _log("*", "orchestra", f"fatto: {sum(len(r.produced) for r in results)} video, chiamate LLM {self.brain.calls}")
        return list(results)

    async def close(self) -> None:
        await self.brain.aclose()
        self.db.close()

    # ================================================================== un canale
    async def _channel_day(self, ch: Channel, per_channel: Optional[int], force_long: bool) -> RunResult:
        res = RunResult(ch.id)
        today = datetime.now(self.tz).date()
        day = today.isoformat()
        try:
            learnings, insights = await asyncio.gather(self.analytics(ch), self.research(ch))
            jobs: List[Dict[str, Any]] = []
            want = per_channel if per_channel is not None else self.s.videos_per_day
            for i in range(self.db.count_day(ch.id, day, "short"), want):
                jobs.append({"format": "short", "slot": self.s.publish_slots[i % len(self.s.publish_slots)]})
            if (force_long or (self.s.weekly_long_video and today.weekday() == self.s.long_video_weekday)) \
                    and self.db.count_day(ch.id, day, "long") == 0:
                jobs.append({"format": "long", "slot": self.s.long_video_slot})
            if not jobs:
                _log(ch.id, "orchestra", "quota giornaliera già raggiunta, niente da fare")
                return res
            ideas = await self.ideate(ch, insights, learnings, len(jobs) + 3)
            queue: asyncio.Queue = asyncio.Queue()
            for idea in ideas:
                queue.put_nowait(idea)
            sem = asyncio.Semaphore(self.s.max_parallel_videos)
            refill_lock, refills = asyncio.Lock(), [2]  # max 2 nuove sessioni di brainstorming

            async def next_idea() -> Optional[Dict[str, Any]]:
                async with refill_lock:
                    if queue.empty() and refills[0] > 0:
                        refills[0] -= 1
                        _log(ch.id, "creativo", "idee finite: nuovo brainstorming")
                        try:
                            for idea in await self.ideate(ch, insights, learnings, 3):
                                queue.put_nowait(idea)
                        except Exception as e:
                            _log(ch.id, "creativo", f"brainstorming fallito: {e}")
                    return None if queue.empty() else queue.get_nowait()

            async def worker(job: Dict[str, Any]) -> None:
                async with sem:
                    while (idea := await next_idea()) is not None:
                        try:
                            out = await self.produce(ch, idea, job["format"], job["slot"], day, insights)
                        except Exception as e:  # un video fallito non ferma gli altri
                            res.errors.append(f"{idea.get('topic')}: {e}")
                            _log(ch.id, "orchestra", f"ERRORE su '{idea.get('topic')}': {e}")
                            continue
                        if out:
                            res.produced.append(out)
                            return
                    res.errors.append(f"idee esaurite per uno slot {job['format']} {job['slot']}")

            await asyncio.gather(*(worker(j) for j in jobs))
            if force_long or today.weekday() == self.s.long_video_weekday:
                await self.growth(ch)
        except Exception as e:
            res.errors.append(str(e))
            _log(ch.id, "orchestra", f"ERRORE canale: {e}")
        return res

    # ================================================================== team analytics
    async def analytics(self, ch: Channel) -> str:
        cached = self.db.latest_learning(ch.id)
        if not configured(ch):
            return cached
        yt = YouTube(ch, self.http)
        vids = [v for v in self.db.videos(ch.id, "uploaded", limit=60) if v.get("youtube_id")]
        if not vids:
            return cached
        try:
            stats = await yt.video_stats([v["youtube_id"] for v in vids])
        except (httpx.HTTPError, YouTubeError) as e:
            _log(ch.id, "analytics", f"statistiche non disponibili: {e}")
            return cached
        rows = []
        for v in vids:
            s = stats.get(v["youtube_id"])
            if s:
                self.db.update_video(v["id"], views=s["viewCount"], likes=s["likeCount"],
                                     comments=s["commentCount"], stats_at=time.time())
                rows.append(f"- {s['viewCount']:>8} views {s['likeCount']:>5} like {s['commentCount']:>4} comm | "
                            f"{v['format']} | {v['title']}")
        if len(rows) < 3:
            return cached
        out = await A.ANALYST.run(self.brain, ch, "Statistiche dei video del canale:\n" + "\n".join(rows))
        text = "\n".join(f"- {x}" for x in out.get("lessons", []))
        if text:
            self.db.add_learning(ch.id, text)
            _log(ch.id, "analytics", f"{len(out.get('lessons', []))} nuove lezioni dai dati")
        return text or cached

    # ================================================================== team ricerca
    async def research(self, ch: Channel) -> Dict[str, Any]:
        report = self.db.latest_json("trends", ch.id, max_age=6 * 3600)
        if report is None:
            report = await trends.collect(ch, self.http, log=lambda m: _log(ch.id, "ricerca", m))
            self.db.save_json("trends", ch.id, report)
        _log(ch.id, "ricerca", f"{len(report['videos'])} video di tendenza, {len(report['searches'])} ricerche in crescita")
        insights = await A.TREND_ANALYST.run(self.brain, ch,
                                             f"Dati di tendenza di oggi:\n{A.fmt_trends(report)}\n\n"
                                             f"Parole chiave della nicchia: {', '.join(ch.keywords)}")
        _log(ch.id, "ricerca", f"argomenti caldi: {', '.join(map(str, insights.get('hot_topics', [])[:4]))}")
        return insights

    # ================================================================== team creativo
    async def ideate(self, ch: Channel, insights: Dict[str, Any], learnings: str, n: int) -> List[Dict[str, Any]]:
        recent = self.db.recent_topics(ch.id)
        task = (f"Genera {n + 2} idee di video.\n\nAnalisi trend:\n{A.dumps(insights)}\n\n"
                f"Lezioni dai nostri video:\n{learnings or '(canale nuovo, nessun dato)'}\n\n"
                f"Argomenti GIÀ FATTI (vietato ripeterli):\n" + "\n".join(f"- {t}" for t in recent[:60]))
        out = await A.IDEATOR.run(self.brain, ch, task)
        ideas = [i for i in out.get("ideas", []) if isinstance(i, dict) and i.get("topic")]
        fresh = []
        for idea in sorted(ideas, key=lambda i: -_num(i.get("viral_score"))):
            if not any(_similar(idea["topic"], t) for t in recent + [f["topic"] for f in fresh]):
                fresh.append(idea)
        _log(ch.id, "creativo", f"{len(fresh)} idee nuove (scartate {len(ideas) - len(fresh)} ripetizioni)")
        if not fresh:
            raise RuntimeError("nessuna idea nuova generata")
        return fresh

    async def write_short(self, ch: Channel, idea: Dict[str, Any], insights: Dict[str, Any], fixes: str) -> Dict[str, Any]:
        task = (f"Scrivi uno YouTube Short di 40-55 secondi (110-140 parole parlate in totale, 6-9 scene).\n"
                f"Idea: {A.dumps(idea)}\nFormule di hook che funzionano ora: "
                f"{A.dumps(insights.get('hook_formulas', [])[:5])}" + (f"\n\nCORREZIONI OBBLIGATORIE dal revisore:\n{fixes}" if fixes else ""))
        return await A.SCRIPTWRITER.run(self.brain, ch, task)

    async def write_long(self, ch: Channel, idea: Dict[str, Any], fixes: str) -> Dict[str, Any]:
        outline = await A.OUTLINER.run(self.brain, ch, f"Video lungo su: {A.dumps(idea)}"
                                       + (f"\nCorrezioni: {fixes}" if fixes else ""))
        chapters = outline.get("chapters", [])[:7]

        async def chapter(i: int, c: Dict[str, Any]) -> List[Dict[str, Any]]:
            task = (f"Scrivi il capitolo {i + 1}/{len(chapters)} di un video lungo intitolato "
                    f"\"{outline.get('title_idea', idea['topic'])}\". Capitolo: {A.dumps(c)}. "
                    f"170-220 parole parlate, 4-6 scene. "
                    + ("Inizia con questo hook: " + str(outline.get("hook", "")) if i == 0 else
                       "Non salutare, continua il racconto dal capitolo precedente."))
            return (await A.SCRIPTWRITER.run(self.brain, ch, task)).get("scenes", [])

        parts = await asyncio.gather(*(chapter(i, c) for i, c in enumerate(chapters)))  # capitoli in parallelo
        return {"title_idea": outline.get("title_idea", idea["topic"]), "scenes": [s for p in parts for s in p],
                "cta": "Iscriviti per il prossimo video."}

    # ================================================================== un video, dall'idea all'upload
    async def produce(self, ch: Channel, idea: Dict[str, Any], fmt: str, slot: str, day: str,
                      insights: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        vid = self.db.add_video(ch.id, day, fmt, idea["topic"])
        tag = f"#{vid} {fmt}"
        _log(ch.id, "creativo", f"{tag} scrivo: {idea['topic']}")
        fixes, script, review = "", {}, {}
        for attempt in range(self.s.max_rewrites + 1):
            script = await (self.write_short(ch, idea, insights, fixes) if fmt == "short"
                            else self.write_long(ch, idea, fixes))
            scenes = [s for s in script.get("scenes", []) if isinstance(s, dict) and str(s.get("text", "")).strip()]
            if len(scenes) < 3:
                fixes = "Lo script deve avere almeno 6 scene con testo parlato."
                continue
            script["scenes"] = scenes
            review = await A.REVIEWER.run(self.brain, ch, f"Formato: {fmt}\nScript:\n{A.dumps(script)}")
            score = _score(review.get("score"))
            _log(ch.id, "qualità", f"{tag} voto {score}/10, verdetto {review.get('verdict')}, rischio {review.get('factual_risk')}")
            if review.get("verdict") == "reject" and review.get("policy_issues"):
                self.db.update_video(vid, status="rejected", data={"script": script, "review": review})
                _log(ch.id, "qualità", f"{tag} SCARTATO: {review.get('policy_issues')}")
                return None
            if score >= self.s.min_quality_score and review.get("verdict") != "rewrite" \
                    or attempt == self.s.max_rewrites and score >= self.s.min_quality_score - 1:
                break
            fixes = "\n".join(f"- {f}" for f in review.get("fixes", [])) or "- hook più forte, frasi più corte"
            _log(ch.id, "qualità", f"{tag} riscrittura {attempt + 1}")
        else:
            self.db.update_video(vid, status="rejected", data={"script": script, "review": review})
            _log(ch.id, "qualità", f"{tag} SCARTATO: qualità insufficiente dopo le riscritture")
            return None
        if not script.get("scenes"):
            self.db.update_video(vid, status="rejected", error="script vuoto")
            return None

        seo = await A.SEO.run(self.brain, ch, f"Formato: {fmt}\nScript:\n{A.dumps(script)}")
        title = str(seo.get("title") or script.get("title_idea") or idea["topic"])[:100]
        self.db.update_video(vid, status="scripted", title=title, data={"idea": idea, "script": script,
                                                                         "review": review, "seo": seo})
        _log(ch.id, "SEO", f"{tag} titolo: {title}")

        # ------------------------------------------------ produzione
        out_dir = self.s.data_dir / "videos" / ch.id / day
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{vid:05d}_{fmt}"
        cta = str(script.get("cta", "")).strip()
        if cta:
            script["scenes"][-1]["text"] = f"{script['scenes'][-1]['text']} {cta}"
        spoken = " ".join(str(s["text"]).strip() for s in script["scenes"])
        audio = out_dir / f"{stem}.mp3"
        words = await tts.synthesize(spoken, ch.voice, audio)
        _log(ch.id, "produzione", f"{tag} voce pronta ({words[-1].end:.0f}s, {len(words)} parole)")
        video = out_dir / f"{stem}.mp4"
        async with self.render_sem:
            await render.render(scenes=script["scenes"], words=words, audio=audio, out=video, fmt=fmt,
                                palette=ch.palette, workdir=out_dir / f"{stem}_work", http=self.http,
                                stock_cache=self.s.data_dir / "stock", music_dir=APP_DIR / "assets" / "music")
        audio.unlink(missing_ok=True)
        thumb = render.thumbnail(str(seo.get("thumbnail_text") or title), ch.palette, out_dir / f"{stem}.png", stem)
        description = self.description(ch, seo, fmt)
        meta = {"title": title, "description": description, "tags": seo.get("tags", []),
                "pinned_comment": seo.get("pinned_comment", ""), "format": fmt, "slot": slot}
        (out_dir / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.db.update_video(vid, status="rendered", file=str(video))
        _log(ch.id, "produzione", f"{tag} video pronto: {video.relative_to(self.s.data_dir)} ({render.duration(video):.0f}s)")

        # ------------------------------------------------ pubblicazione
        result = {"id": vid, "channel": ch.id, "format": fmt, "title": title, "file": str(video), "youtube_id": None}
        if self.dry_run or not configured(ch):
            why = "dry-run" if self.dry_run else "credenziali YouTube non configurate"
            _log(ch.id, "pubblicazione", f"{tag} non caricato ({why}): pronto per upload manuale")
            return result
        publish_at = self.publish_time(day, slot)
        async with self.quota_lock:
            project = project_of(ch)
            if self.db.quota_used(project, day) + self.s.upload_quota_cost > self.s.daily_quota:
                _log(ch.id, "pubblicazione", f"{tag} quota API esaurita oggi: resta in coda (data/videos)")
                return result
            self.db.spend_quota(project, day, self.s.upload_quota_cost)
        yt = YouTube(ch, self.http)
        privacy = "private" if self.s.privacy_mode == "private" else "public"
        yid = await yt.upload(video, title=title, description=description, tags=list(seo.get("tags", [])),
                              category_id=ch.category_id, language=ch.language, privacy=privacy,
                              publish_at=publish_at if self.s.privacy_mode == "schedule" else None)
        self.db.update_video(vid, status="uploaded", youtube_id=yid, publish_at=publish_at)
        result["youtube_id"] = yid
        _log(ch.id, "pubblicazione", f"{tag} caricato https://youtu.be/{yid} (uscita {publish_at})")
        for step, coro in (("miniatura", yt.set_thumbnail(yid, thumb) if fmt == "long" else None),
                           ("commento", yt.comment(yid, meta["pinned_comment"]) if meta["pinned_comment"] else None)):
            if coro is None:
                continue
            try:
                await coro
            except (YouTubeError, httpx.HTTPError) as e:
                _log(ch.id, "pubblicazione", f"{tag} {step} saltato: {e}")
        return result

    def description(self, ch: Channel, seo: Dict[str, Any], fmt: str) -> str:
        body = str(seo.get("description", "")).strip()
        found = re.findall(r"#\w+", body)
        body = re.sub(r"(?:^|\s)#\w+", "", body).strip()  # gli hashtag vanno tutti in fondo, una volta sola
        tags: List[str] = []
        for h in (["#shorts"] if fmt == "short" else []) + [str(x) for x in seo.get("hashtags", [])] + found:
            h = h if h.startswith("#") else f"#{h}"
            if h.lower() not in (t.lower() for t in tags):
                tags.append(h)
        parts = [body]
        if ch.affiliate_links:
            parts.append("\n".join(ch.affiliate_links) + "\n(link affiliati: se acquisti tramite questi link "
                                                          "il canale riceve una piccola commissione)")
        parts.append(" ".join(tags[:6]))
        return "\n\n".join(p for p in parts if p)

    def publish_time(self, day: str, slot: str) -> str:
        """Orario di uscita in UTC (RFC3339). Se lo slot di oggi è passato, esce fra 30 minuti."""
        hh, mm = (int(x) for x in slot.split(":"))
        local = datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=self.tz)
        soonest = datetime.now(self.tz) + timedelta(minutes=30)
        when = max(local, soonest)
        return when.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ================================================================== team crescita
    async def growth(self, ch: Channel) -> None:
        stats: Dict[str, Any] = {}
        if configured(ch):
            try:
                stats = await YouTube(ch, self.http).channel_stats()
                self.db.save_json("channel_stats", ch.id, stats)
            except (YouTubeError, httpx.HTTPError) as e:
                _log(ch.id, "crescita", f"statistiche canale non disponibili: {e}")
        progress = ypp_progress(stats) if stats else {"nota": "canale non ancora collegato"}
        produced = len(self.db.videos(ch.id, limit=1000))
        out = await A.GROWTH.run(self.brain, ch, f"Statistiche: {A.dumps(stats)}\nAvanzamento Programma Partner: "
                                 f"{A.dumps(progress)}\nVideo prodotti finora: {produced}\n"
                                 f"Lezioni recenti:\n{self.db.latest_learning(ch.id)}")
        report = self.s.data_dir / "reports" / f"{ch.id}-{datetime.now(self.tz).date()}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {ch.name} — report crescita", "", "## Programma Partner", *[f"- {k}: {v}" for k, v in progress.items()],
                 "", f"**Stato:** {out.get('status', '')}", f"**Stima:** {out.get('eta', '')}", "", "## Priorità",
                 *[f"- {p}" for p in out.get("priorities", [])], "", "## Entrate extra",
                 *[f"- {p}" for p in out.get("extra_revenue", [])]]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _log(ch.id, "crescita", f"report salvato: {report.relative_to(self.s.data_dir)}")


def _score(x: Any) -> float:
    """Voto 0-10 anche se il modello risponde in centesimi (es. 75 -> 7.5)."""
    v = _num(x)
    return v / 10 if v > 10 else v


def _num(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _similar(a: str, b: str) -> bool:
    """Stesso argomento? Parole significative in comune o testo quasi identico."""
    wa = {w for w in re.findall(r"\w+", a.lower()) if len(w) > 3}
    wb = {w for w in re.findall(r"\w+", b.lower()) if len(w) > 3}
    if wa and wb and len(wa & wb) / len(wa | wb) >= 0.6:
        return True
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.85


__all__ = ["Factory", "RunResult", "Path"]
