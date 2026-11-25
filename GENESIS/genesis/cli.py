"""Command-line interface: ``python -m genesis`` (or ``genesis`` once installed).

Whoever runs the CLI is the owner of this GÉNESIS installation.
Exit codes: 0 ok · 1 GÉNESIS error · 2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .app import Genesis, import_data
from .core.config import set_online
from .core.worker import TaskWorker
from .errors import ConfigError, GenesisError
from .intelligence.base import TASK_TYPES, Request
from .intelligence.online import FreelmProvider
from .security.permissions import OWNER, Level

DEFAULT_PORT = 8765

MARKS = {"ok": "OK", "warn": "!!", "fail": "KO"}


def _json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _gb(mb: int | None) -> str:
    return "non rilevata" if mb is None else f"{mb / 1024:.1f} GB"


# -- commands ------------------------------------------------------------------


def cmd_status(g: Genesis, args: argparse.Namespace) -> int:
    s = g.status()
    if args.json:
        _json(s)
    else:
        chain = "OK" if s["audit_chain_ok"] else f"INTERROTTA alla voce {s['audit_first_bad_seq']}"
        print(f"GÉNESIS {s['version']} · profilo {s['profile']} ({s['profile_reason']})")
        print(f"Dati:          {s['home']}")
        print(f"Database:      schema v{s['schema_version']} · {s['backups']} backup")
        print(f"Progetti:      {s['projects']} attivi")
        print("Compiti:       " + " · ".join(f"{k} {v}" for k, v in s["tasks"].items()))
        print(f"Approvazioni:  {s['pending_approvals']} in attesa")
        print(f"Audit:         {s['audit_entries']} voci · catena {chain}")
        print("Provider IA:   nessuno configurato (arrivano in Fase 3)")
    return 0 if s["audit_chain_ok"] else 1


def cmd_doctor(g: Genesis, args: argparse.Namespace) -> int:
    hw, checks = g.hardware, g.doctor()
    failed = any(c["status"] == "fail" for c in checks)
    if args.json:
        _json({"hardware": hw.to_dict(), "profile": g.profile.name, "profile_reason": g.profile_reason,
               "checks": checks})
        return 1 if failed else 0
    if hw.gpus is None:
        gpus = "non rilevata"
    elif not hw.gpus:
        gpus = "nessuna"
    else:
        gpus = ", ".join(f"{x.name} (VRAM {x.vram_mb} MB)" if x.vram_mb else x.name for x in hw.gpus)
    disk = "non rilevato" if hw.disk_total_gb is None else f"{hw.disk_free_gb} GB liberi su {hw.disk_total_gb} GB"
    p = g.profile
    print(f"GÉNESIS {__version__} - diagnostica")
    print(f"Sistema:    {hw.os_name} {hw.os_release} ({hw.os_version}) {hw.machine} · Python {hw.python}")
    print(f"CPU:        {hw.cpu_model or 'non rilevata'} · {hw.cpu_logical or '?'} thread logici")
    print(f"RAM:        {_gb(hw.ram_total_mb)} totali · {_gb(hw.ram_available_mb)} disponibili ora")
    print(f"Disco:      {disk} ({hw.disk_path})")
    print(f"GPU:        {gpus}")
    print(f"Profilo:    {p.name} - {g.profile_reason}")
    print(f"            compiti in parallelo {p.max_workers} · chiamate IA in parallelo {p.max_parallel_online}"
          f" · modelli locali {'sì' if p.local_models else 'no'}")
    for note in hw.notes:
        print(f"Nota:       {note}")
    print("Controlli:")
    for c in checks:
        print(f"  [{MARKS[c['status']]}] {c['check']}: {c['detail']}")
    return 1 if failed else 0


def cmd_project_add(g: Genesis, args: argparse.Namespace) -> int:
    p = g.projects.create(args.name, args.description)
    print(f"Progetto creato: {p['name']} ({p['id']})")
    return 0


def cmd_project_list(g: Genesis, args: argparse.Namespace) -> int:
    rows = g.projects.list(include_archived=args.all)
    if not rows:
        print("Nessun progetto.")
    for p in rows:
        print(f"{p['name']:<30} {p['status']:<9} creato {p['created_at'][:19]}  {p['description']}")
    return 0


def cmd_project_archive(g: Genesis, args: argparse.Namespace) -> int:
    p = g.projects.archive(args.name)
    print(f"Progetto archiviato: {p['name']}")
    return 0


def cmd_task_kinds(g: Genesis, args: argparse.Namespace) -> int:
    for spec in g.tasks.kinds():
        print(f"{spec.kind:<26} livello {int(spec.level)}  {spec.description}")
    return 0


def cmd_task_submit(g: Genesis, args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.payload)
    except ValueError as exc:
        print(f"errore: --payload non è JSON valido ({exc})", file=sys.stderr)
        return 2
    project_id = None
    if args.project:
        project = g.projects.get(args.project)
        if project is None:
            raise GenesisError(f"progetto inesistente: {args.project}")
        project_id = project["id"]
    t = g.tasks.submit(args.kind, payload, principal=OWNER, project_id=project_id, priority=args.priority,
                       max_attempts=args.attempts, approval_id=args.approval)
    print(f"Compito in coda: {t['id']} ({t['kind']}, livello {t['level']})")
    return 0


def cmd_task_list(g: Genesis, args: argparse.Namespace) -> int:
    rows = g.tasks.list(status=args.status, limit=args.limit)
    if not rows:
        print("Nessun compito.")
    for t in rows:
        print(f"{t['id']}  {t['status']:<10} {t['kind']:<26} {t['created_at'][:19]}")
    return 0


def cmd_task_show(g: Genesis, args: argparse.Namespace) -> int:
    task = g.tasks.get(args.id)
    if task is None:
        raise GenesisError(f"compito inesistente: {args.id}")
    _json(task)
    return 0


def cmd_task_run(g: Genesis, args: argparse.Namespace) -> int:
    recovered, done = TaskWorker(g).run_once(args.max)
    if recovered:
        print(f"{recovered} compiti interrotti da un arresto precedente sono stati ripresi.")
    if not done:
        print("Nessun compito in coda.")
    for t in done:
        line = f"{t['id']}  {t['status']:<10} {t['kind']}"
        if t["status"] in ("failed", "pending") and t["error"]:
            line += f"  ({'errore' if t['status'] == 'failed' else 'nuovo tentativo'}: {t['error']})"
        print(line)
    return 0


def cmd_task_cancel(g: Genesis, args: argparse.Namespace) -> int:
    outcome = g.tasks.cancel(args.id)
    messages = {"cancelled": "Compito annullato.", "cancel_requested": "Richiesta di annullamento inviata al compito."}
    print(messages.get(outcome, f"Il compito è già concluso (stato '{outcome}')."))
    return 0


def cmd_approvals_list(g: Genesis, args: argparse.Namespace) -> int:
    rows = g.permissions.list_approvals(args.status)
    if not rows:
        print("Nessuna approvazione.")
    for a in rows:
        print(f"{a['id']}  {a['status']:<9} livello {a['level']}  {a['principal']} -> {a['action']}")
    return 0


def cmd_approvals_decide(g: Genesis, args: argparse.Namespace) -> int:
    g.permissions.decide(args.id, args.approve, decided_by=OWNER)
    print("Approvata." if args.approve else "Negata.")
    return 0


def cmd_ask(g: Genesis, args: argparse.Namespace) -> int:
    result = g.router.route(Request(args.text, args.type, args.private))
    check = "verificato (algoritmo)" if result["verified"] else "non verificato (modello esterno)"
    print(result["output"])
    print(f"[motore: {result['engine']} · tipo: {result['task_type']} · {check}]")
    return 0


def cmd_providers(g: Genesis, args: argparse.Namespace) -> int:
    for e in g.router.describe():
        state = "ATTIVO" if e["usable"] else "spento"
        print(f"{e['id']:<8} {e['kind']:<7} costo {e['cost']:<5} {state:<7} {e['reason']}")
        print(f"         {e['name']} · capacità: {', '.join(e['capabilities'])}")
    return 0


def cmd_online(g: Genesis, args: argparse.Namespace) -> int:
    enable = args.action == "enable"
    if enable and not args.confirm:
        print("Accende il motore online: OpenRouter, solo modelli gratuiti :free (verificati il 2026-11-24).\n"
              "Le richieste non private lasceranno questo computer; le chiamate sono registrate nell'audit.\n"
              "Per procedere ripeti il comando aggiungendo --confirm.", file=sys.stderr)
        return 2
    action = "intelligence.online_" + args.action
    approval_id = g.permissions.request_approval(OWNER, action, Level.SYSTEM_CHANGE, {})
    g.permissions.decide(approval_id, True, decided_by=OWNER)
    g.permissions.require(OWNER, action, Level.SYSTEM_CHANGE, approval_id=approval_id)
    path = set_online(g.config.home, enable)
    print(f"Motore online {'acceso' if enable else 'spento'} ({path}).")
    if enable:
        available, reason = FreelmProvider().status()
        print(f"Stato: {reason}" + ("" if available else " -> vedi README, sezione 'Motore online'"))
    return 0


def cmd_agents(g: Genesis, args: argparse.Namespace) -> int:
    if args.action == "list":
        for a in g.agents.describe():
            print(f"{a['id']:<12} livello {a['level']}  {a['name']} ({a['role']}) - tipi: {', '.join(a['task_types'])}")
        return 0
    if args.action == "runs":
        for r in g.agents.runs(args.limit):
            print(f"{r['created_at'][:19]}  {r['mode']:<8} {r['agent_id']:<11} {r['status']:<9} {r['goal'][:60]}")
        return 0
    if args.action == "run":
        result = g.agents.run(args.agent, args.text, args.private)
    elif args.action == "direct":
        result = g.agents.direct(args.text, args.private)
    else:
        result = g.agents.council(args.text, args.members.split(",") if args.members else None, args.private)
        c = result["council"]
        print(f"[consiglio: {c['answered']}/{len(c['members'])} risposte · accordo {c['agreement']} · "
              f"contraddizioni: {'; '.join(c['contradictions']) or 'nessuna'}]")
    print(result["output"])
    return 0 if result["ok"] else 1


def cmd_tools(g: Genesis, args: argparse.Namespace) -> int:
    if args.action == "list":
        for s in g.tools.specs():
            state = "" if s.enabled else f"  [spento: {s.note}]"
            print(f"{s.name:<24} livello {s.level}  {s.description}{state}")
        return 0
    try:
        params = json.loads(args.params)
    except ValueError as exc:
        print(f"errore: --params non è JSON valido ({exc})", file=sys.stderr)
        return 2
    result = g.tools.call(OWNER, args.name, params, approval_id=args.approval)
    if result["untrusted"]:
        print("[dati esterni NON FIDATI]")
    _json(result["result"])
    return 0


def cmd_lab(g: Genesis, args: argparse.Namespace) -> int:
    lab = g.lab
    if args.action == "datasets":
        for d in lab.datasets.list():
            print(f"{d['ref']:<18} {d['items']:>4} elementi  sha256 {d['hash'][:12]}  {d['description']}")
        return 0
    if args.action == "import":
        info = lab.datasets.import_file(args.path)
        print(f"Dataset importato: {info['ref']} ({info['items']} elementi, sha256 {info['hash'][:12]})")
        return 0
    if args.action == "list":
        for e in lab.list(args.limit):
            m = e["metrics"] or {}
            acc = f"{m.get('correct', '?')}/{m.get('n', '?')}" if m else "—"
            print(f"{e['id'][:8]}  {e['status']:<11} {e['subject']:<18} {e['dataset']:<16} {acc:>7}  {e['created_at'][:19]}")
        return 0
    if args.action == "show":
        _json(lab.get(args.id))
        return 0
    if args.action == "compare":
        c = lab.compare(args.a, args.b)
        print(c["verdict"])
        if c["comparable"]:
            print(f"A {c['a_subject']}: {c['accuracy_a']:.1%} · B {c['b_subject']}: {c['accuracy_b']:.1%} · "
                  f"{c['paired_items']} elementi appaiati · solo A {c['only_a_correct']} · solo B {c['only_b_correct']} · "
                  f"IC95% {c['diff_ci95']}")
        return 0
    if args.action == "report":
        print(f"Rapporto scritto: {lab.report(args.id, args.compare)}")
        return 0
    if args.action == "reproduce":
        payload, kind = {"experiment_id": lab.resolve(args.id)}, "lab.reproduce"
    else:
        payload = {"dataset": args.dataset, "subject": args.subject, "seed": args.seed, "sample": args.sample,
                   "allow_remote": args.allow_remote, "name": args.name, "objective": args.objective,
                   "hypothesis": args.hypothesis, "baseline_id": args.baseline}
        kind = "lab.run"
    task = g.tasks.submit(kind, payload, principal=OWNER)
    try:
        _, done = TaskWorker(g).run_once()
    except GenesisError as exc:  # a running 'genesis serve' will execute it
        print(f"Esperimento in coda ({task['id']}): {exc}")
        return 0
    finished = next((t for t in done if t["id"] == task["id"]), g.tasks.get(task["id"]))
    if finished["status"] != "succeeded":
        print(f"errore: {finished['error']}", file=sys.stderr)
        return 1
    _json(finished["result"])
    return 0


def cmd_engines(g: Genesis, args: argparse.Namespace) -> int:
    if args.action == "list":
        for e in g.engines.describe():
            ext = "usa un modello esterno" if e["uses_external_model"] else "solo algoritmi propri"
            print(f"{e['id']:<11} {e['name']} v{e['version']} - {ext}")
            for c in e["components"]:
                note = "" if c["available"] else " [non disponibile]"
                print(f"             · {c['name']} ({c['kind']}){note}")
            print("             operazioni: " + ", ".join(o["name"] for o in e["operations"]))
        return 0
    try:
        payload = json.loads(args.payload)
    except ValueError as exc:
        print(f"errore: --payload non è JSON valido ({exc})", file=sys.stderr)
        return 2
    _json(g.engines.run(OWNER, args.engine, args.op, payload))
    return 0


def cmd_models(g: Genesis, args: argparse.Namespace) -> int:
    from .models.catalog import card_dict
    from .models.feasibility import assess, best_option
    from .models.finetune import plan, plan_markdown
    if args.action == "list":
        print(f"Hardware: RAM {g.hardware.ram_total_mb or '?'} MB, VRAM {g.hardware.max_vram_mb} MB, profilo {g.profile.name}")
        for card in sorted(g.models.values(), key=lambda c: c.params_b):
            best = best_option(card.params_b, g.hardware, g.profile)
            print(f"{card.id:<26} {card.params_b:>5.2f} B  {card.license:<34} -> {best['verdict']} "
                  f"({best['quant']}, {best['need']['total_gb']} GB)")
        print("Dati dei modelli NON verificati: controllare sempre la scheda ufficiale prima dell'uso.")
        return 0
    card = g.models.get(args.id)
    if card is None:
        raise GenesisError(f"modello sconosciuto: {args.id} (vedi 'genesis models list')")
    if args.action == "check":
        _json({"model": card_dict(card), **assess(card.params_b, g.hardware, g.profile, args.quant, args.context)})
        return 0
    p = plan(card.params_b, args.method, args.examples, args.tokens, g.hardware, args.seq_len, args.batch, args.epochs)
    folder = g.config.reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"piano-{card.id}-{args.method}.md"
    path.write_text(plan_markdown(card_dict(card), p), encoding="utf-8")
    print(f"{p['verdict']}\nPiano scritto: {path}")
    return 0


def cmd_backup_create(g: Genesis, args: argparse.Namespace) -> int:
    print(f"Backup creato e verificato: {g.create_backup()}")
    return 0


def cmd_backup_list(g: Genesis, args: argparse.Namespace) -> int:
    rows = g.backups()
    if not rows:
        print("Nessun backup.")
    for path in rows:
        print(f"{path}  ({path.stat().st_size // 1024} KB)")
    return 0


def cmd_backup_restore(g: Genesis, args: argparse.Namespace) -> int:
    if not args.confirm:
        print("Il ripristino sostituisce tutti i dati attuali con quelli del backup.\n"
              "Prima viene salvata una copia di sicurezza dello stato attuale.\n"
              "Per procedere ripeti il comando aggiungendo --confirm.", file=sys.stderr)
        return 2
    # The owner at the keyboard approves explicitly with --confirm; the approval is recorded and single-use.
    approval_id = g.permissions.request_approval(OWNER, "memory.restore", Level.SYSTEM_CHANGE,
                                                 {"source": str(args.path)})
    g.permissions.decide(approval_id, True, decided_by=OWNER)
    safety = g.restore_backup(args.path, approval_id)
    print(f"Ripristino completato da {args.path}\nCopia di sicurezza dello stato precedente: {safety}")
    return 0


def cmd_export(g: Genesis, args: argparse.Namespace) -> int:
    path, counts = g.export_data(args.path)
    print(f"Esportazione creata: {path}")
    print("Contenuto: " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


def cmd_audit_verify(g: Genesis, args: argparse.Namespace) -> int:
    ok, first_bad = g.audit.verify()
    print(f"Catena di audit intatta ({g.audit.count()} voci)." if ok else f"Catena di audit INTERROTTA alla voce {first_bad}.")
    return 0 if ok else 1


def cmd_audit_tail(g: Genesis, args: argparse.Namespace) -> int:
    for r in g.audit.tail(args.n):
        print(f"{r['seq']:>6}  {r['ts'][:19]}  {r['principal']:<10} {r['outcome']:<8} {r['action']}")
    return 0


# -- parser --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genesis", description="GÉNESIS - core della piattaforma (Fase 1).")
    parser.add_argument("--version", action="version", version=f"genesis {__version__}")
    parser.add_argument("--home", type=Path, default=None,
                        help="cartella dati (predefinita: GENESIS_HOME o la cartella dati utente del sistema)")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, text in (("status", cmd_status, "stato del sistema"),
                             ("doctor", cmd_doctor, "hardware, profilo e controlli")):
        s = sub.add_parser(name, help=text)
        s.add_argument("--json", action="store_true", help="uscita in JSON")
        s.set_defaults(func=func)

    project = sub.add_parser("project", help="progetti").add_subparsers(dest="action", required=True)
    s = project.add_parser("add", help="crea un progetto")
    s.add_argument("name")
    s.add_argument("-d", "--description", default="")
    s.set_defaults(func=cmd_project_add)
    s = project.add_parser("list", help="elenca i progetti")
    s.add_argument("--all", action="store_true", help="includi gli archiviati")
    s.set_defaults(func=cmd_project_list)
    s = project.add_parser("archive", help="archivia un progetto")
    s.add_argument("name")
    s.set_defaults(func=cmd_project_archive)

    task = sub.add_parser("task", help="coda dei compiti").add_subparsers(dest="action", required=True)
    task.add_parser("kinds", help="tipi di compito disponibili").set_defaults(func=cmd_task_kinds)
    s = task.add_parser("submit", help="mette un compito in coda")
    s.add_argument("kind")
    s.add_argument("--payload", default="{}", help="oggetto JSON")
    s.add_argument("--project", help="nome o id del progetto")
    s.add_argument("--priority", type=int, default=0)
    s.add_argument("--attempts", type=int, default=1, help="tentativi massimi (1-10)")
    s.add_argument("--approval", help="id di un'approvazione (livelli 4-5)")
    s.set_defaults(func=cmd_task_submit)
    s = task.add_parser("list", help="elenca i compiti")
    s.add_argument("--status")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_task_list)
    s = task.add_parser("show", help="dettagli di un compito")
    s.add_argument("id")
    s.set_defaults(func=cmd_task_show)
    s = task.add_parser("run", help="esegue i compiti in coda, uno alla volta")
    s.add_argument("--max", type=int, help="numero massimo di compiti")
    s.set_defaults(func=cmd_task_run)
    s = task.add_parser("cancel", help="annulla un compito")
    s.add_argument("id")
    s.set_defaults(func=cmd_task_cancel)

    approvals = sub.add_parser("approvals", help="approvazioni del proprietario").add_subparsers(
        dest="action", required=True)
    s = approvals.add_parser("list", help="elenca le approvazioni")
    s.add_argument("--status", choices=["pending", "approved", "denied", "used"])
    s.set_defaults(func=cmd_approvals_list)
    for name, approve in (("approve", True), ("deny", False)):
        s = approvals.add_parser(name, help="approva" if approve else "nega")
        s.add_argument("id")
        s.set_defaults(func=cmd_approvals_decide, approve=approve)

    backup = sub.add_parser("backup", help="backup del database").add_subparsers(dest="action", required=True)
    backup.add_parser("create", help="crea un backup verificato").set_defaults(func=cmd_backup_create)
    backup.add_parser("list", help="elenca i backup").set_defaults(func=cmd_backup_list)
    s = backup.add_parser("restore", help="ripristina un backup (livello 4)")
    s.add_argument("path", type=Path)
    s.add_argument("--confirm", action="store_true", help="conferma esplicita del proprietario")
    s.set_defaults(func=cmd_backup_restore)

    s = sub.add_parser("export", help="esporta tutti i dati in JSON (per migrare su un altro PC)")
    s.add_argument("path", type=Path, nargs="?")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("import", help="importa un'esportazione in una cartella dati vuota")
    s.add_argument("path", type=Path)
    s.set_defaults(func=None)

    s = sub.add_parser("ask", help="chiede al router dei motori (locale o online gratuito)")
    s.add_argument("text")
    s.add_argument("--type", choices=TASK_TYPES, help="tipo di richiesta (predefinito: classificazione automatica)")
    s.add_argument("--private", action="store_true", help="la richiesta non lascia questo computer")
    s.set_defaults(func=cmd_ask)
    agents = sub.add_parser("agents", help="agenti: elenco, esecuzione, Director, Consiglio").add_subparsers(
        dest="action", required=True)
    agents.add_parser("list", help="agenti disponibili").set_defaults(func=cmd_agents)
    s = agents.add_parser("runs", help="ultime esecuzioni")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_agents)
    s = agents.add_parser("run", help="esegue un agente")
    s.add_argument("agent")
    s.add_argument("text")
    s.add_argument("--private", action="store_true")
    s.set_defaults(func=cmd_agents)
    for name, text in (("direct", "il Director scompone l'obiettivo e delega"), ("council", "consiglio di specialisti")):
        s = agents.add_parser(name, help=text)
        s.add_argument("text")
        s.add_argument("--private", action="store_true")
        if name == "council":
            s.add_argument("--members", help="es. researcher,analyst,manager")
        s.set_defaults(func=cmd_agents)

    tools = sub.add_parser("tools", help="strumenti: elenco ed esecuzione").add_subparsers(dest="action", required=True)
    tools.add_parser("list", help="strumenti, livelli e stato").set_defaults(func=cmd_tools)
    s = tools.add_parser("call", help="esegue uno strumento come proprietario")
    s.add_argument("name")
    s.add_argument("--params", default="{}", help="oggetto JSON")
    s.add_argument("--approval", help="id di un'approvazione (strumenti di livello 4-5)")
    s.set_defaults(func=cmd_tools)

    lab = sub.add_parser("lab", help="Research Lab: dataset, esperimenti, confronti").add_subparsers(
        dest="action", required=True)
    lab.add_parser("datasets", help="dataset disponibili").set_defaults(func=cmd_lab)
    s = lab.add_parser("import", help="importa un dataset JSON")
    s.add_argument("path", type=Path)
    s.set_defaults(func=cmd_lab)
    s = lab.add_parser("run", help="esegue un esperimento")
    s.add_argument("--dataset", required=True)
    s.add_argument("--subject", required=True, help="classifier, baseline:majority, local.math, router, council, agent:<id>")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--sample", type=int)
    s.add_argument("--allow-remote", action="store_true", help="consente il motore online (consuma quota gratuita)")
    s.add_argument("--name")
    s.add_argument("--objective", default="")
    s.add_argument("--hypothesis", default="")
    s.add_argument("--baseline", help="id dell'esperimento di riferimento da confrontare")
    s.set_defaults(func=cmd_lab)
    s = lab.add_parser("list", help="ultimi esperimenti")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_lab)
    for name in ("show", "reproduce"):
        s = lab.add_parser(name, help="dettagli" if name == "show" else "riesegue con stessa configurazione e seed")
        s.add_argument("id")
        s.set_defaults(func=cmd_lab)
    s = lab.add_parser("compare", help="confronto appaiato A contro B")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(func=cmd_lab)
    s = lab.add_parser("report", help="rapporto Markdown in <home>/reports")
    s.add_argument("id")
    s.add_argument("--compare", help="id dell'esperimento di riferimento")
    s.set_defaults(func=cmd_lab)

    engines = sub.add_parser("engines", help="motori GÉNESIS: elenco ed esecuzione").add_subparsers(
        dest="action", required=True)
    engines.add_parser("list", help="motori, componenti e operazioni").set_defaults(func=cmd_engines)
    s = engines.add_parser("run", help="esegue un'operazione come proprietario")
    s.add_argument("engine")
    s.add_argument("op")
    s.add_argument("--payload", default="{}", help="oggetto JSON")
    s.set_defaults(func=cmd_engines)

    models = sub.add_parser("models", help="Model Development Lab: catalogo, fattibilità, piani").add_subparsers(
        dest="action", required=True)
    models.add_parser("list", help="modelli aperti e fattibilità su questo PC").set_defaults(func=cmd_models)
    s = models.add_parser("check", help="fattibilità dettagliata")
    s.add_argument("id")
    s.add_argument("--quant", default="q4_k_m", choices=["f16", "q8_0", "q6_k", "q5_k_m", "q4_k_m", "q3_k_m", "q2_k"])
    s.add_argument("--context", type=int, default=4096)
    s.set_defaults(func=cmd_models)
    s = models.add_parser("plan", help="piano di fine-tuning (non addestra nulla)")
    s.add_argument("id")
    s.add_argument("--method", default="qlora", choices=["full", "lora", "qlora"])
    s.add_argument("--examples", type=int, default=1000)
    s.add_argument("--tokens", type=int, default=300, help="token medi per esempio")
    s.add_argument("--seq-len", type=int, default=1024)
    s.add_argument("--batch", type=int, default=4)
    s.add_argument("--epochs", type=int, default=3)
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("online", help="accende o spegne il motore online (OpenRouter gratuito)")
    s.add_argument("action", choices=["enable", "disable"])
    s.add_argument("--confirm", action="store_true", help="conferma esplicita del proprietario")
    s.set_defaults(func=cmd_online)
    sub.add_parser("providers", help="motori disponibili e perché sono attivi o spenti").set_defaults(func=cmd_providers)

    s = sub.add_parser("serve", help="avvia l'interfaccia nel browser e l'esecuzione dei compiti")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--no-browser", action="store_true", help="non aprire il browser")
    s.set_defaults(func=None)

    audit = sub.add_parser("audit", help="registro di audit").add_subparsers(dest="action", required=True)
    audit.add_parser("verify", help="verifica la catena di hash").set_defaults(func=cmd_audit_verify)
    s = audit.add_parser("tail", help="ultime voci")
    s.add_argument("-n", type=int, default=20)
    s.set_defaults(func=cmd_audit_tail)
    return parser


def _serve(args: argparse.Namespace) -> int:
    import webbrowser

    from .api.server import ApiServer

    try:
        server = ApiServer(args.home, port=args.port)
    except OSError as exc:
        print(f"errore: impossibile usare la porta {args.port} ({exc}). Prova con --port 8766", file=sys.stderr)
        return 1
    print(f"GÉNESIS è in esecuzione: {server.url}")
    print("Lascia aperta questa finestra. Per fermare GÉNESIS premi Ctrl+C.")
    if not args.no_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto in corso: attendo la fine dell'eventuale compito in esecuzione...")
    finally:
        server.shutdown()
    print("GÉNESIS è stato fermato.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            # UTF-8 also when redirected: Windows would otherwise use the legacy code page ("GÉNESIS" -> "G?NESIS").
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args)
        if args.command == "import":
            counts = import_data(args.home, args.path)
            with Genesis(args.home) as g:
                g.audit.record(OWNER, "memory.import", "ok", Level.WORKSPACE_WRITE,
                               {"source": str(args.path), "counts": counts})
            print("Importazione completata: " + " · ".join(f"{k} {v}" for k, v in counts.items()))
            return 0
        with Genesis(args.home) as g:
            return int(args.func(g, args))
    except ConfigError as exc:
        print(f"errore di configurazione: {exc}", file=sys.stderr)
        return 2
    except GenesisError as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 1
