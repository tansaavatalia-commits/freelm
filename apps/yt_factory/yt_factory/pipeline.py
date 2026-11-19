"""Orchestratore dello studio: i canali lavorano in parallelo, e dentro ogni canale più video sono in produzione
contemporaneamente. Ogni video attraversa tutti i reparti:

  INSIGHTS   lezioni dai video già pubblicati (cosa ha funzionato)
  RESEARCH   dati live (YouTube più visti + views/ora, RSS concorrenti, Google Trends, autocompletamento YouTube,
             commenti) -> Viral Deconstructor + Audience Researcher (in parallelo)
  CREATIVE   Concept Developer: concetti ORIGINALI che battono i riferimenti virali (mai copie)
             Hook Lab (8 hook) -> Audience Panel: giuria di modelli diversi vota il migliore
             Scriptwriter (Short) | Showrunner + capitoli in parallelo (video lungo)
  QUALITY    Fact Checker con fonti Wikipedia -> Retention Editor & Compliance (voto, riscritture, scarto)
  ART        Art Director -> immagini AI originali + clip stock per scena (in parallelo)
  PACKAGING  3 titoli -> scelta, descrizione, tag, hashtag, testo miniatura, primo commento
  PRODUCTION voce neurale, inquadrature dinamiche, sottotitoli pop, barra, effetti sonori
  PUBLISHING upload programmato, dichiarazione AI, miniatura, commento, controllo quota
  GROWTH     (settimanale) avanzamento monetizzazione + priorità
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
from . import factcheck, render, trends, tts, visuals
from .config import APP_DIR, Channel, Settings
from .db import DB
from .llm import Brain
from .youtube import YouTube, YouTubeError, configured, project_of, ypp_progress


def _log(channel: str, desk: str, msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} [{channel:<9}] {desk:<11} {msg}", flush=True)


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
        self.brain = brain or Brain(settings.llm_model, concurrency=6, log=lambda m: _log("*", "llm", m))
        self.render_sem = asyncio.Semaphore(settings.max_parallel_renders)
        self.quota_lock = asyncio.Lock()
        self.tz = ZoneInfo(settings.timezone)
        self.http: httpx.AsyncClient

    # ================================================================== entry point
    async def daily(self, channels: List[Channel], *, per_channel: Optional[int] = None,
                    force_long: bool = False) -> List[RunResult]:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as self.http:
            results = await asyncio.gather(*(self._channel_day(ch, per_channel, force_long) for ch in channels))
        _log("*", "studio", f"fatto: {sum(len(r.produced) for r in results)} video, chiamate LLM {self.brain.calls}")
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
            jobs: List[Dict[str, Any]] = []
            want = per_channel if per_channel is not None else self.s.videos_per_day
            for i in range(self.db.count_day(ch.id, day, "short"), want):
                jobs.append({"format": "short", "slot": self.s.publish_slots[i % len(self.s.publish_slots)]})
            weekly = force_long or (self.s.weekly_long_video and today.weekday() == self.s.long_video_weekday)
            if weekly and self.db.count_day(ch.id, day, "long") == 0:
                jobs.append({"format": "long", "slot": self.s.long_video_slot})
            if not jobs:
                _log(ch.id, "studio", "quota giornaliera già raggiunta, niente da fare")
                return res
            learnings, insights = await asyncio.gather(self.analytics(ch), self.research(ch))
            concepts = await self.ideate(ch, insights, learnings, len(jobs) + 3)
            queue: asyncio.Queue = asyncio.Queue()
            for c in concepts:
                queue.put_nowait(c)
            sem = asyncio.Semaphore(self.s.max_parallel_videos)
            refill_lock, refills = asyncio.Lock(), [2]

            async def next_concept() -> Optional[Dict[str, Any]]:
                async with refill_lock:
                    if queue.empty() and refills[0] > 0:
                        refills[0] -= 1
                        _log(ch.id, "creative", "concetti finiti: nuovo brainstorming")
                        try:
                            for c in await self.ideate(ch, insights, learnings, 3):
                                queue.put_nowait(c)
                        except Exception as e:
                            _log(ch.id, "creative", f"brainstorming fallito: {e}")
                    return None if queue.empty() else queue.get_nowait()

            async def worker(job: Dict[str, Any]) -> None:
                async with sem:
                    while (concept := await next_concept()) is not None:
                        try:
                            out = await self.produce(ch, concept, job["format"], job["slot"], day, insights)
                        except Exception as e:  # un video fallito non ferma gli altri
                            res.errors.append(f"{concept.get('topic')}: {e}")
                            _log(ch.id, "studio", f"ERRORE su '{concept.get('topic')}': {e}")
                            continue
                        if out:
                            res.produced.append(out)
                            return
                    res.errors.append(f"concetti esauriti per uno slot {job['format']} {job['slot']}")

            await asyncio.gather(*(worker(j) for j in jobs))
            if weekly:
                await self.growth(ch)
        except Exception as e:
            res.errors.append(str(e))
            _log(ch.id, "studio", f"ERRORE canale: {e}")
        return res

    # ================================================================== insights
    async def analytics(self, ch: Channel) -> str:
        cached = self.db.latest_learning(ch.id)
        if not configured(ch):
            return cached
        vids = [v for v in self.db.videos(ch.id, "uploaded", limit=60) if v.get("youtube_id")]
        if not vids:
            return cached
        try:
            stats = await YouTube(ch, self.http).video_stats([v["youtube_id"] for v in vids])
        except (httpx.HTTPError, YouTubeError) as e:
            _log(ch.id, "insights", f"statistiche non disponibili: {e}")
            return cached
        rows = []
        for v in vids:
            s = stats.get(v["youtube_id"])
            if s:
                self.db.update_video(v["id"], views=s["viewCount"], likes=s["likeCount"],
                                     comments=s["commentCount"], stats_at=time.time())
                rows.append(f"- {s['viewCount']:>8} views {s['likeCount']:>5} likes {s['commentCount']:>4} comments | "
                            f"{v['format']} | {v['title']}")
        if len(rows) < 3:
            return cached
        out = await A.ANALYST.run(self.brain, ch, "Channel video statistics:\n" + "\n".join(rows))
        text = "\n".join(f"- {x}" for x in out.get("lessons", []))
        if text:
            self.db.add_learning(ch.id, text)
            _log(ch.id, "insights", f"{len(out.get('lessons', []))} nuove lezioni dai dati")
        return text or cached

    # ================================================================== research
    async def research(self, ch: Channel) -> Dict[str, Any]:
        report = self.db.latest_json("trends", ch.id, max_age=6 * 3600)
        if report is None:
            log = lambda m: _log(ch.id, "research", m)  # noqa: E731
            report = await trends.collect(ch, self.http, log=log)
            report["audience"] = await trends.audience(ch, self.http, report["videos"], log=log)
            self.db.save_json("trends", ch.id, report)
        aud = report.get("audience", {})
        _log(ch.id, "research", f"{len(report['videos'])} video virali, {len(report['searches'])} ricerche in crescita, "
                                f"{len(aud.get('suggestions', []))} ricerche YouTube, {len(aud.get('comments', []))} commenti")
        blue, audience = await asyncio.gather(
            A.DECONSTRUCTOR.run(self.brain, ch, f"Live trend data today:\n{A.fmt_trends(report)}\n\n"
                                                f"Niche keywords: {', '.join(ch.keywords)}"),
            A.AUDIENCE.run(self.brain, ch, f"Audience signals:\n{A.fmt_audience(aud)}"),
        )
        insights = {**blue, "audience": audience}
        _log(ch.id, "research", f"{len(blue.get('blueprints', []))} blueprint virali, "
                                f"{len(audience.get('gaps', []))} lacune del pubblico da sfruttare")
        return insights

    # ================================================================== creative
    async def ideate(self, ch: Channel, insights: Dict[str, Any], learnings: str, n: int) -> List[Dict[str, Any]]:
        recent = self.db.recent_topics(ch.id)
        task = (f"Develop {n + 2} concepts.\n\nViral blueprints and trends:\n{A.dumps({k: v for k, v in insights.items() if k != 'audience'})}"
                f"\n\nAudience research:\n{A.dumps(insights.get('audience', {}))}\n\n"
                f"Lessons from our own videos:\n{learnings or '(new channel, no data yet)'}\n\n"
                "Topics ALREADY COVERED (forbidden):\n" + "\n".join(f"- {t}" for t in recent[:60]))
        out = await A.CONCEPTS.run(self.brain, ch, task)
        items = out.get("concepts") or out.get("ideas") or out.get("items") or []
        concepts = [c for c in items if isinstance(c, dict) and c.get("topic")]
        fresh: List[Dict[str, Any]] = []
        for c in sorted(concepts, key=lambda c: -_num(c.get("viral_score"))):
            if not any(_similar(c["topic"], t) for t in recent + [f["topic"] for f in fresh]):
                fresh.append(c)
        _log(ch.id, "creative", f"{len(fresh)} concetti originali (scartate {len(concepts) - len(fresh)} ripetizioni)")
        if not fresh:
            raise RuntimeError("nessun concetto nuovo generato")
        return fresh

    async def best_hook(self, ch: Channel, concept: Dict[str, Any], tag: str) -> str:
        """Hook Lab scrive 8 hook; la giuria (un giurato per modello) li vota; vince la media più alta."""
        lab = await A.HOOK_LAB.run(self.brain, ch, f"Write 8 hooks for this concept:\n{A.dumps(concept)}")
        hooks = [str(h).strip() for h in (lab.get("hooks") or lab.get("items") or []) if str(h).strip()][:8]
        if not hooks:
            return str(concept.get("hook") or concept.get("topic"))
        listing = "\n".join(f"{i}. {h}" for i, h in enumerate(hooks))

        async def juror(model: str) -> Optional[List[float]]:
            try:
                v = await A.PANEL.run(self.brain, ch, f"Concept: {concept.get('topic')}\nHooks:\n{listing}", model=model)
            except Exception:
                return None
            scores = [_num(x) for x in v.get("scores", [])]
            return scores if len(scores) == len(hooks) else None

        votes = [v for v in await asyncio.gather(*(juror(m) for m in self.s.panel_models)) if v]
        if not votes:
            return hooks[0]
        avg = [sum(v[i] for v in votes) / len(votes) for i in range(len(hooks))]
        best = max(range(len(hooks)), key=lambda i: avg[i])
        _log(ch.id, "creative", f"{tag} giuria ({len(votes)} modelli) sceglie hook {avg[best]:.1f}/10: {hooks[best]}")
        return hooks[best]

    async def write_short(self, ch: Channel, concept: Dict[str, Any], hook: str, insights: Dict[str, Any],
                          fixes: str, previous: Optional[Dict[str, Any]] = None,
                          model: Optional[str] = None) -> Dict[str, Any]:
        aud = insights.get("audience", {})
        if previous and fixes:  # revisione mirata: si corregge la bozza, non si riparte da zero
            task = (f"REVISE this draft. Apply every fix below, keep everything that works, keep the beat sheet and "
                    f"85-115 spoken words. Weave attribution into the story instead of adding disclaimers.\n"
                    f"Keep this exact first line: {hook}\nFixes:\n{fixes}\n\nDraft:\n{A.dumps(previous)}")
            return await A.SCRIPTWRITER.run(self.brain, ch, task, model=model)
        task = (f"Write the Short.\nConcept: {A.dumps(concept)}\nOpening hook (first words, verbatim): {hook}\n"
                f"Questions the audience is asking: {A.dumps(aud.get('questions', [])[:6])}")
        return await A.SCRIPTWRITER.run(self.brain, ch, task, model=model)

    async def write_long(self, ch: Channel, concept: Dict[str, Any], fixes: str) -> Dict[str, Any]:
        outline = await A.SHOWRUNNER.run(self.brain, ch, f"Long video about: {A.dumps(concept)}"
                                         + (f"\nFixes: {fixes}" if fixes else ""))
        chapters = outline.get("chapters", [])[:7]

        async def chapter(i: int, c: Dict[str, Any]) -> List[Dict[str, Any]]:
            task = (f"Write chapter {i + 1}/{len(chapters)} of a long video titled "
                    f"\"{outline.get('title_idea', concept['topic'])}\". Chapter: {A.dumps(c)}. "
                    f"This is a LONG-VIDEO chapter: ignore the Short word budget, write 170-220 spoken words, 4-6 scenes. "
                    + (f"Start with this hook verbatim: {outline.get('hook', '')}" if i == 0 else
                       "No greeting: continue the story from the previous chapter. The first line does not need a hook."))
            return (await A.SCRIPTWRITER.run(self.brain, ch, task)).get("scenes", [])

        parts = await asyncio.gather(*(chapter(i, c) for i, c in enumerate(chapters)))
        return {"title_idea": outline.get("title_idea", concept["topic"]), "scenes": [s for p in parts for s in p],
                "cta": ""}

    async def first_draft(self, ch: Channel, concept: Dict[str, Any], hook: str, insights: Dict[str, Any],
                          fmt: str, tag: str) -> Any:
        if fmt != "short":
            return await self.write_long(ch, concept, ""), {}
        models = self.s.writer_models or [None]
        drafts = await asyncio.gather(*(self.write_short(ch, concept, hook, insights, "", None, model=m) for m in models),
                                      return_exceptions=True)
        drafts = [d for d in drafts if isinstance(d, dict) and len(clean_scenes(d.get("scenes", []), hook)) >= 3]
        if not drafts:
            raise RuntimeError("nessuna bozza valida dagli sceneggiatori")
        if len(drafts) == 1:
            return drafts[0], {}
        reviews = await asyncio.gather(*(self.edit(ch, {**d, "scenes": clean_scenes(d["scenes"], hook)}, fmt, [])
                                         for d in drafts))
        best = max(range(len(drafts)), key=lambda i: _score(reviews[i].get("score")))
        _log(ch.id, "creative", f"{tag} {len(drafts)} bozze in gara, vince la n.{best + 1} "
                                f"({' vs '.join(str(_score(r.get('score'))) for r in reviews)})")
        return drafts[best], reviews[best]

    async def edit(self, ch: Channel, script: Dict[str, Any], fmt: str, facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        spoken = " ".join(str(x.get("text", "")) for x in script.get("scenes", []))
        return await A.EDITOR.run(self.brain, ch, f"Format: {fmt}\nWord count: {len(spoken.split())}\n"
                                                  f"Script:\n{A.dumps(script)}\n\nFact-check results:\n{A.dumps(facts)}")

    # ================================================================== quality
    async def fact_check(self, ch: Channel, script: Dict[str, Any], tag: str) -> List[Dict[str, Any]]:
        spoken = " ".join(str(s.get("text", "")) for s in script.get("scenes", []))
        try:
            claims = (await A.FACT_EXTRACT.run(self.brain, ch, f"Script:\n{spoken}")).get("claims", [])
            if not claims:
                return []
            sourced = await factcheck.gather_sources(self.http, claims)
            verdict = await A.FACT_JUDGE.run(self.brain, ch, A.dumps(sourced))
        except Exception as e:
            _log(ch.id, "quality", f"{tag} fact-check non disponibile: {e}")
            return []
        results = [r for r in verdict.get("results", []) if isinstance(r, dict)]
        bad = [r for r in results if r.get("verdict") == "false"]
        _log(ch.id, "quality", f"{tag} fact-check: {len(results)} affermazioni, {len(bad)} false")
        return results

    # ================================================================== un video, dal concetto all'upload
    async def produce(self, ch: Channel, concept: Dict[str, Any], fmt: str, slot: str, day: str,
                      insights: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        vid = self.db.add_video(ch.id, day, fmt, concept["topic"])
        tag = f"#{vid} {fmt}"
        _log(ch.id, "creative", f"{tag} concetto: {concept['topic']}  (meglio perché: {concept.get('upgrade', '-')})")
        hook = await self.best_hook(ch, concept, tag) if fmt == "short" else ""
        fixes, review, facts = "", {}, []
        # prima stesura: più sceneggiatori (modelli diversi) in parallelo, il caporedattore sceglie la migliore
        script, review = await self.first_draft(ch, concept, hook, insights, fmt, tag)
        best: Optional[tuple] = None  # (voto, script, review, facts): una revisione può peggiorare, si tiene il meglio
        for attempt in range(self.s.max_rewrites + 1):
            if attempt:
                script = await (self.write_short(ch, concept, hook, insights, fixes, script) if fmt == "short"
                                else self.write_long(ch, concept, fixes))
                review = {}
            script["scenes"] = clean_scenes(script.get("scenes", []), hook)
            if len(script["scenes"]) < 3:
                fixes = "The script must have at least 6 beats with spoken text."
                continue
            facts = await self.fact_check(ch, script, tag)
            wrong = [f for f in facts if f.get("verdict") == "false"]
            if not review or wrong:
                review = await self.edit(ch, script, fmt, facts)
            score = _score(review.get("score"))
            _log(ch.id, "quality", f"{tag} voto {score}/10 (guarderei fino alla fine: {review.get('watch_to_end', '?')}), "
                                   f"verdetto {review.get('verdict')}, rischio {review.get('factual_risk')}")
            if review.get("verdict") == "reject" and review.get("policy_issues"):
                self.db.update_video(vid, status="rejected", data={"script": script, "review": review})
                _log(ch.id, "quality", f"{tag} SCARTATO: {review.get('policy_issues')}")
                return None
            if not wrong and (best is None or score > best[0]):
                best = (score, json.loads(json.dumps(script)), review, facts)
            good = score >= self.s.min_quality_score and review.get("verdict") != "rewrite"
            if good and not wrong:
                break
            if attempt == self.s.max_rewrites and best and best[0] >= self.s.min_quality_score - 1:
                score, script, review, facts = best
                _log(ch.id, "quality", f"{tag} tengo la versione migliore ({score}/10)")
                break
            fixes = "\n".join(f"- {f}" for f in review.get("fixes", [])[:4])
            fixes += "".join(f"\n- FALSE CLAIM: '{w.get('claim')}' -> {w.get('fix') or 'remove it'}" for w in wrong)
            fixes = fixes.strip() or "- stronger hook, more concrete details, a clearer twist"
            _log(ch.id, "quality", f"{tag} revisione {attempt + 1}")
        else:
            self.db.update_video(vid, status="rejected", data={"script": script, "review": review, "facts": facts})
            _log(ch.id, "quality", f"{tag} SCARTATO: qualità insufficiente dopo le revisioni")
            return None
        _log(ch.id, "quality", f"{tag} script approvato ({len(' '.join(x['text'] for x in script['scenes']).split())} parole)")

        # ------------------------------------------------ art + packaging (in parallelo)
        art, seo = await asyncio.gather(
            A.ART_DIRECTOR.run(self.brain, ch, f"Visual style: {ch.visual_style}\nScenes:\n"
                               + "\n".join(f"{i}. {s['text']}" for i, s in enumerate(script["scenes"]))),
            A.PACKAGING.run(self.brain, ch, f"Format: {fmt}\nScript:\n{A.dumps(script)}"),
        )
        title = str(seo.get("title") or (seo.get("titles") or [None])[0] or script.get("title_idea") or concept["topic"])[:100]
        self.db.update_video(vid, status="scripted", title=title, data={
            "concept": concept, "hook": hook, "script": script, "review": review, "facts": facts, "art": art, "seo": seo})
        _log(ch.id, "packaging", f"{tag} titolo: {title}")

        out_dir = self.s.data_dir / "videos" / ch.id / day
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{vid:05d}_{fmt}"
        assets = await self.acquire_assets(ch, script["scenes"], art, fmt, vid)
        n_photo = sum(1 for a in assets if a.get("photo"))
        n_ai = sum(1 for a in assets if (a.get("image") and not a.get("photo")) or a.get("image2"))
        n_stock = sum(1 for a in assets if a.get("stock"))
        _log(ch.id, "art", f"{tag} {n_photo} foto reali, {n_ai} immagini AI originali, {n_stock} clip stock")
        credits = list(dict.fromkeys(a["credit"] for a in assets if a.get("credit")))

        # ------------------------------------------------ produzione
        cta = str(script.get("cta", "")).strip()
        if cta:
            script["scenes"][-1]["text"] = f"{script['scenes'][-1]['text']} {cta}"
        spoken = " ".join(str(s["text"]).strip() for s in script["scenes"])
        audio = out_dir / f"{stem}.mp3"
        words = await tts.synthesize(spoken, ch.voice, audio, rate=ch.voice_rate)
        _log(ch.id, "production", f"{tag} voce pronta ({words[-1].end:.0f}s, {len(words)} parole)")
        video = out_dir / f"{stem}.mp4"
        async with self.render_sem:
            await render.render(scenes=script["scenes"], words=words, audio=audio, out=video, fmt=fmt,
                                palette=ch.palette, workdir=out_dir / f"{stem}_work", assets=assets,
                                shot_seconds=self.s.shot_seconds, music_dir=APP_DIR / "assets" / "music",
                                ambient=ch.ambient)
        audio.unlink(missing_ok=True)
        first_img = next((a["image"] for a in assets if a.get("image")), None)
        thumb = render.thumbnail(str(seo.get("thumbnail_text") or title), ch.palette, out_dir / f"{stem}.png", stem,
                                 background=first_img)
        description = self.description(ch, seo, fmt, credits)
        meta = {"title": title, "titles": seo.get("titles", []), "description": description,
                "tags": seo.get("tags", []), "pinned_comment": seo.get("pinned_comment", ""), "format": fmt,
                "slot": slot, "hook": hook, "concept": concept}
        (out_dir / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.db.update_video(vid, status="rendered", file=str(video))
        _log(ch.id, "production", f"{tag} video pronto: {video.relative_to(self.s.data_dir)} ({render.duration(video):.0f}s)")

        # ------------------------------------------------ pubblicazione
        result = {"id": vid, "channel": ch.id, "format": fmt, "title": title, "file": str(video), "youtube_id": None}
        if self.dry_run or not configured(ch):
            why = "dry-run" if self.dry_run else "credenziali YouTube non configurate"
            _log(ch.id, "publishing", f"{tag} non caricato ({why}): pronto per upload manuale")
            return result
        publish_at = self.publish_time(day, slot)
        async with self.quota_lock:
            project = project_of(ch)
            if self.db.quota_used(project, day) + self.s.upload_quota_cost > self.s.daily_quota:
                _log(ch.id, "publishing", f"{tag} quota API esaurita oggi: resta in coda (data/videos)")
                return result
            self.db.spend_quota(project, day, self.s.upload_quota_cost)
        yt = YouTube(ch, self.http)
        privacy = "private" if self.s.privacy_mode == "private" else "public"
        yid = await yt.upload(video, title=title, description=description, tags=list(seo.get("tags", [])),
                              category_id=ch.category_id, language=ch.language, privacy=privacy,
                              publish_at=publish_at if self.s.privacy_mode == "schedule" else None)
        self.db.update_video(vid, status="uploaded", youtube_id=yid, publish_at=publish_at)
        result["youtube_id"] = yid
        _log(ch.id, "publishing", f"{tag} caricato https://youtu.be/{yid} (uscita {publish_at})")
        for step, coro in (("miniatura", yt.set_thumbnail(yid, thumb) if fmt == "long" else None),
                           ("commento", yt.comment(yid, meta["pinned_comment"]) if meta["pinned_comment"] else None)):
            if coro is None:
                continue
            try:
                await coro
            except (YouTubeError, httpx.HTTPError) as e:
                _log(ch.id, "publishing", f"{tag} {step} saltato: {e}")
        return result

    async def acquire_assets(self, ch: Channel, scenes: List[Dict[str, Any]], art: Dict[str, Any], fmt: str,
                             vid: int) -> List[Dict[str, Any]]:
        """Per scena: foto reale (se c'è un soggetto reale), immagine AI originale, clip stock — tutto in parallelo."""
        shots = {int(_num(s.get("scene"))): s for s in art.get("shots", []) if isinstance(s, dict)}
        cache = self.s.data_dir / "media"

        async def one(i: int, scene: Dict[str, Any]) -> Dict[str, Any]:
            spec = shots.get(i, {})
            prompt = str(spec.get("image_prompt") or scene.get("text", ""))[:400]
            photo, img, stock = await asyncio.gather(
                visuals.real_photo(self.http, str(spec.get("photo_query") or ""), fmt, cache, pick=i),
                visuals.ai_image(self.http, prompt, ch.visual_style, fmt, vid * 100 + i, cache)
                if self.s.ai_images else _none(),
                visuals.pexels_clip(self.http, str(spec.get("stock_query") or ""), fmt, cache / "stock", pick=vid + i),
                return_exceptions=True)
            photo = photo if isinstance(photo, dict) else None
            img = img if isinstance(img, Path) else None
            main = Path(photo["path"]) if photo else img
            return {"image": main, "image2": img if photo else None,
                    "stock": stock if isinstance(stock, Path) else None,
                    "photo": bool(photo), "credit": photo["credit"] if photo else ""}

        return list(await asyncio.gather(*(one(i, s) for i, s in enumerate(scenes))))

    def description(self, ch: Channel, seo: Dict[str, Any], fmt: str, credits: Optional[List[str]] = None) -> str:
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
            note = ("(affiliate links: if you buy through them the channel earns a small commission)" if ch.language == "en"
                    else "(link affiliati: se acquisti tramite questi link il canale riceve una piccola commissione)")
            parts.append("\n".join(ch.affiliate_links) + "\n" + note)
        if credits:
            parts.append(("Photos: " if ch.language == "en" else "Foto: ") + "; ".join(credits))
        parts.append(" ".join(tags[:6]))
        return "\n\n".join(p for p in parts if p)

    def publish_time(self, day: str, slot: str) -> str:
        """Orario di uscita in UTC (RFC3339). Se lo slot di oggi è passato, esce fra 30 minuti."""
        hh, mm = (int(x) for x in slot.split(":"))
        local = datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=self.tz)
        when = max(local, datetime.now(self.tz) + timedelta(minutes=30))
        return when.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ================================================================== growth
    async def growth(self, ch: Channel) -> None:
        stats: Dict[str, Any] = {}
        if configured(ch):
            try:
                stats = await YouTube(ch, self.http).channel_stats()
                self.db.save_json("channel_stats", ch.id, stats)
            except (YouTubeError, httpx.HTTPError) as e:
                _log(ch.id, "growth", f"statistiche canale non disponibili: {e}")
        progress = ypp_progress(stats) if stats else {"note": "channel not connected yet"}
        produced = len(self.db.videos(ch.id, limit=1000))
        out = await A.GROWTH.run(self.brain, ch, f"Stats: {A.dumps(stats)}\nPartner Program progress: "
                                 f"{A.dumps(progress)}\nVideos produced so far: {produced}\n"
                                 f"Recent lessons:\n{self.db.latest_learning(ch.id)}")
        report = self.s.data_dir / "reports" / f"{ch.id}-{datetime.now(self.tz).date()}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {ch.name} — growth report", "", "## Partner Program", *[f"- {k}: {v}" for k, v in progress.items()],
                 "", f"**Status:** {out.get('status', '')}", f"**ETA:** {out.get('eta', '')}", "", "## Priorities",
                 *[f"- {p}" for p in out.get("priorities", [])], "", "## Extra revenue",
                 *[f"- {p}" for p in out.get("extra_revenue", [])]]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _log(ch.id, "growth", f"report salvato: {report.relative_to(self.s.data_dir)}")


def clean_scenes(scenes: Any, hook: str = "") -> List[Dict[str, Any]]:
    """Ripulisce il parlato da etichette in MAIUSCOLO/indicazioni di regia e garantisce che il video apra con l'hook."""
    out: List[Dict[str, Any]] = []
    for sc in scenes if isinstance(scenes, list) else []:
        if not isinstance(sc, dict):
            continue
        text = re.sub(r"\[[^\]]*\]|\([^)]*(?:pause|beat|music|sfx|cut)[^)]*\)", " ", str(sc.get("text", "")), flags=re.I)
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        kept = [x for x in sentences if not (re.search(r"[A-Za-zÀ-ÿ]{2}", x) and x == x.upper() and len(x.split()) <= 4)]
        text = re.sub(r"\s+", " ", " ".join(kept)).strip()
        if text:
            out.append({**sc, "text": text, "on_screen": str(sc.get("on_screen") or "")[:28]})
    if hook and out and not _norm(out[0]["text"]).startswith(_norm(hook)[:25]):
        out.insert(0, {"text": hook, "on_screen": ""})
    return out


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


async def _none() -> None:
    return None


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
