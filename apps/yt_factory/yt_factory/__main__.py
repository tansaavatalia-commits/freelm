"""CLI.

  python -m yt_factory run                 # giornata completa per tutti i canali (dry-run: nessun upload)
  python -m yt_factory run --publish       # ... e carica su YouTube (programmato negli orari di config)
  python -m yt_factory run --channel fatti --count 1 --long
  python -m yt_factory trends --channel soldi
  python -m yt_factory auth --channel fatti   # una volta per canale, sul tuo computer
  python -m yt_factory stats               # avanzamento monetizzazione di ogni canale
  python -m yt_factory status              # ultimi video prodotti
  python -m yt_factory rerender 12         # rimonta il video #12 (immagini/montaggio) senza riscriverlo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from . import config


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="yt_factory", description="Fabbrica multi-agente di canali YouTube (LLM gratuiti via freelm)")
    p.add_argument("--config", help="percorso di channels.toml")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="produce (e pubblica) i video di oggi")
    r.add_argument("--channel", action="append", help="solo questi canali (ripetibile)")
    r.add_argument("--count", type=int, help="Shorts per canale (default: videos_per_day)")
    r.add_argument("--long", action="store_true", help="produci anche il video lungo settimanale oggi")
    r.add_argument("--publish", action="store_true", help="carica davvero su YouTube (default: dry-run)")
    r.add_argument("--offline", action="store_true", help="test senza rete: agenti finti + voce muta")
    t = sub.add_parser("trends", help="mostra i dati di tendenza e l'analisi del Trend Analyst")
    t.add_argument("--channel", required=True)
    a = sub.add_parser("auth", help="collega un canale YouTube (OAuth, una volta)")
    a.add_argument("--channel", required=True)
    rr = sub.add_parser("rerender", help="rimonta un video già scritto (immagini/montaggio) senza rifare gli script")
    rr.add_argument("id", type=int, nargs="+", help="numero del video (vedi `status`)")
    sub.add_parser("stats", help="statistiche e avanzamento Programma Partner")
    sub.add_parser("status", help="ultimi video prodotti")
    args = p.parse_args(argv)
    s = config.load(args.config)

    if args.cmd == "auth":
        from .auth import authorize

        authorize(s.channel(args.channel))
        return 0
    if args.cmd == "status":
        from .db import DB

        db = DB(s.data_dir / "factory.sqlite")
        for v in db.videos(limit=40):
            yt = f"https://youtu.be/{v['youtube_id']}" if v["youtube_id"] else ""
            print(f"#{v['id']:<5} {v['day']} {v['channel']:<8} {v['format']:<5} {v['status']:<9} {v['views']:>8}v  {v['title'] or v['topic']}  {yt}")
        return 0
    return asyncio.run(_async(args, s))


async def _async(args, s) -> int:
    from .pipeline import Factory

    if args.cmd == "run":
        channels = [s.channel(c) for c in args.channel] if args.channel else s.channels
        brain = None
        if args.offline:
            from .offline import OfflineBrain

            os.environ.update(YTF_OFFLINE_TTS="1", YTF_OFFLINE="1", YTF_NO_AI_IMAGES="1")
            brain = OfflineBrain()
        f = Factory(s, dry_run=not args.publish, brain=brain)
        try:
            results = await f.daily(channels, per_channel=args.count, force_long=args.long)
        finally:
            await f.close()
        print("\n=== RIEPILOGO ===")
        failed = 0
        for res in results:
            print(f"\n{res.channel}: {len(res.produced)} video")
            for v in res.produced:
                where = f"https://youtu.be/{v['youtube_id']}" if v["youtube_id"] else v["file"]
                print(f"  - [{v['format']}] {v['title']}\n    {where}")
            for e in res.errors:
                print(f"  ! {e}")
            failed += 1 if res.errors and not res.produced else 0  # "niente da fare oggi" non è un errore
        return 1 if results and failed == len(results) else 0

    if args.cmd == "rerender":
        f = Factory(s, dry_run=True)
        try:
            for vid in args.id:
                print(await f.rerender(vid))
        finally:
            await f.close()
        return 0

    if args.cmd == "trends":
        import httpx

        from . import agents as A
        from . import trends
        from .llm import Brain

        ch = s.channel(args.channel)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            report = await trends.collect(ch, http, log=lambda m: print("!", m, file=sys.stderr))
        print(A.fmt_trends(report))
        brain = Brain(s.llm_model)
        try:
            print(json.dumps(await A.TREND_ANALYST.run(brain, ch, A.fmt_trends(report)), ensure_ascii=False, indent=2))
        finally:
            await brain.aclose()
        return 0

    if args.cmd == "stats":
        import httpx

        from .youtube import YouTube, configured, ypp_progress

        async with httpx.AsyncClient(timeout=30) as http:
            for ch in s.channels:
                print(f"\n== {ch.name} ({ch.id})")
                if not configured(ch):
                    print("  non collegato: esegui `python -m yt_factory auth --channel", ch.id + "`")
                    continue
                st = await YouTube(ch, http).channel_stats()
                for k, v in {**st, **ypp_progress(st)}.items():
                    print(f"  {k}: {v}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
