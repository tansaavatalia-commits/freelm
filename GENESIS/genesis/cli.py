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
from .errors import ConfigError, GenesisError
from .security.permissions import OWNER, Level

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
    done = g.tasks.run_pending(args.max)
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

    audit = sub.add_parser("audit", help="registro di audit").add_subparsers(dest="action", required=True)
    audit.add_parser("verify", help="verifica la catena di hash").set_defaults(func=cmd_audit_verify)
    s = audit.add_parser("tail", help="ultime voci")
    s.add_argument("-n", type=int, default=20)
    s.set_defaults(func=cmd_audit_tail)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
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
