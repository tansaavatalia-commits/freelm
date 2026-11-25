"""Versioned datasets. A dataset is identified by name@version and by the SHA-256 of its items:
changing any item without changing the version is refused, so results stay comparable."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.clock import Now, utcnow
from ..errors import GenesisError
from ..intelligence.base import TASK_TYPES
from ..memory.db import Database
from .scoring import SCORERS

MAX_ITEMS = 2000
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z._-]{1,20}$")


@dataclass(frozen=True)
class Item:
    input: str
    expected: Any
    scorer: str
    task_type: str | None = None


@dataclass(frozen=True)
class Dataset:
    name: str
    version: str
    description: str
    items: tuple[Item, ...]
    builtin: bool = False

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def hash(self) -> str:
        canonical = json.dumps([[i.input, i.expected, i.scorer, i.task_type] for i in self.items],
                               ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def items_json(self) -> str:
        return json.dumps([{"input": i.input, "expected": i.expected, "scorer": i.scorer, "task_type": i.task_type}
                           for i in self.items], ensure_ascii=False)


def parse_dataset(raw: Any, builtin: bool = False) -> Dataset:
    if not isinstance(raw, dict) or set(raw) - {"name", "version", "description", "items"}:
        raise GenesisError("dataset: servono name, version, description, items")
    name, version, description, items = (raw.get(k) for k in ("name", "version", "description", "items"))
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise GenesisError("dataset: nome non valido (minuscole, cifre, - e _)")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise GenesisError("dataset: versione non valida")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise GenesisError(f"dataset: da 1 a {MAX_ITEMS} elementi")
    parsed = []
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict) or set(it) - {"input", "expected", "scorer", "task_type"}:
            raise GenesisError(f"elemento {n}: chiavi ammesse input, expected, scorer, task_type")
        if not isinstance(it.get("input"), str) or not it["input"].strip():
            raise GenesisError(f"elemento {n}: input deve essere un testo non vuoto")
        scorer, expected, task_type = it.get("scorer"), it.get("expected"), it.get("task_type")
        if scorer not in SCORERS:
            raise GenesisError(f"elemento {n}: scorer deve essere uno di {', '.join(SCORERS)}")
        if task_type is not None and task_type not in TASK_TYPES:
            raise GenesisError(f"elemento {n}: task_type non valido")
        valid = {"numeric": isinstance(expected, (int, float)) and not isinstance(expected, bool),
                 "label": isinstance(expected, str),
                 "exact": isinstance(expected, str),
                 "contains": isinstance(expected, str) or (isinstance(expected, list) and expected
                                                           and all(isinstance(x, str) and x for x in expected))}
        if not valid[scorer]:
            raise GenesisError(f"elemento {n}: expected non adatto allo scorer {scorer}")
        parsed.append(Item(it["input"], expected, scorer, task_type))
    return Dataset(name, version, description if isinstance(description, str) else "", tuple(parsed), builtin)


def _num(items: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [{"input": q, "expected": a, "scorer": "numeric"} for q, a in items]


BUILTIN: tuple[Dataset, ...] = (
    parse_dataset({
        "name": "math-basic", "version": "1",
        "description": "Aritmetica in italiano: 24 espressioni calcolabili + 2 problemi a parole (non calcolabili "
                       "dal motore locale: misurano i limiti).",
        "items": _num([
            ("2+2", 4), ("quanto fa 12*(3+4)?", 84), ("calcola 144/12", 12), ("7*8-5", 51), ("2^10", 1024),
            ("sqrt(81)+1", 10), ("(15+5)/4", 5), ("100-37*2", 26), ("3.5*4", 14), ("10/4", 2.5),
            ("quanto vale 9*9*9?", 729), ("17 % 5", 2), ("abs(-42)", 42), ("round(3.14159, 2)", 3.14),
            ("1000/8", 125), ("6 x 7", 42), ("(2+3)*(4+5)", 45), ("-5+12", 7), ("2^0.5*2^0.5", 2),
            ("250*4/10", 100), ("calcola 99+1", 100), ("15/3/5", 1), ("3^3-3^2", 18), ("log10(1000)", 3),
            ("Ho 3 mele e ne compro altre 4: quante mele ho?", 7),
            ("Un libro costa 12 euro: quanto costano 5 libri?", 60),
        ])}, builtin=True),
    parse_dataset({
        "name": "classify-it", "version": "1",
        "description": "30 richieste in italiano etichettate per intento (math, text.stats, code, reasoning, chat).",
        "items": [{"input": q, "expected": label, "scorer": "label"} for q, label in [
            ("quanto fa 45*3?", "math"), ("calcola 2^8", "math"), ("17+25", "math"), ("sqrt(144)", "math"),
            ("Ho 3 mele e ne compro 4: quante ne ho?", "math"),
            ("conta le parole: il gatto dorme sul divano", "text.stats"),
            ("statistiche testo: Oggi piove. Domani sole.", "text.stats"),
            ("Quante parole ci sono in questa frase?", "text.stats"),
            ("scrivi una funzione python che inverte una stringa", "code"),
            ("perché questo codice javascript dà errore?", "code"),
            ("come si fa una query SQL per contare le righe?", "code"),
            ("correggi questo bug: def f(x): return x +", "code"),
            ("spiegami cosa fa questa regex: ^a.*z$", "code"),
            ("come creo una classe in TypeScript?", "code"),
            ("perché il cielo è blu?", "reasoning"), ("dimostra che la radice di 2 è irrazionale", "reasoning"),
            ("confronta vantaggi e svantaggi del lavoro da remoto", "reasoning"),
            ("analizza i rischi di usare password deboli", "reasoning"),
            ("ragiona sul perché le foglie cambiano colore", "reasoning"),
            ("qual è la causa principale dell'inflazione?", "reasoning"),
            ("ciao, come stai?", "chat"), ("scrivi una poesia sul mare", "chat"),
            ("consigliami un film per stasera", "chat"), ("traduci in inglese: buongiorno a tutti", "chat"),
            ("raccontami una barzelletta", "chat"), ("che tempo fa a Roma?", "chat"),
            ("dammi tre idee per una cena veloce", "chat"), ("riassumi la trama di Pinocchio", "chat"),
            ("come si dice grazie in giapponese?", "chat"), ("suggerisci un nome per un gatto", "chat"),
        ]]}, builtin=True),
    parse_dataset({
        "name": "qa-facts", "version": "1",
        "description": "20 domande di cultura generale con risposte brevi verificabili (per motori online).",
        "items": [{"input": q, "expected": a, "scorer": "contains", "task_type": "chat"} for q, a in [
            ("Qual è la capitale d'Italia?", "Roma"), ("Quanti giorni ha una settimana?", ["7", "sette"]),
            ("Chi ha scritto la Divina Commedia?", "Dante"), ("Qual è il simbolo chimico dell'oro?", "Au"),
            ("In che anno è caduto il muro di Berlino?", "1989"),
            ("Qual è il pianeta più grande del sistema solare?", "Giove"),
            ("Quante zampe ha un ragno?", ["8", "otto"]), ("Qual è la lingua ufficiale del Brasile?", "portoghese"),
            ("Chi ha dipinto la Gioconda?", "Leonardo"), ("Qual è l'oceano più grande?", "Pacifico"),
            ("Quanti minuti ci sono in un'ora?", ["60", "sessanta"]), ("Qual è la capitale del Giappone?", "Tokyo"),
            ("Che colore si ottiene mescolando blu e giallo?", "verde"),
            ("A quanti gradi Celsius bolle l'acqua a livello del mare?", ["100", "cento"]),
            ("Quale gas respiriamo per vivere?", "ossigeno"), ("Chi ha formulato la teoria della relatività?", "Einstein"),
            ("Qual è la montagna più alta del mondo?", "Everest"), ("Qual è la capitale della Francia?", "Parigi"),
            ("Quanti lati ha un esagono?", ["6", "sei"]), ("Chi è l'autore de I Promessi Sposi?", "Manzoni"),
        ]]}, builtin=True),
    # Pre-registered on 2026-11-25, BEFORE writing classifier v2 and the word-problem solver (Phase 7),
    # to evaluate them on data they were not tuned on. Labels by intent, same protocol as classify-it@1.
    parse_dataset({
        "name": "classify-holdout", "version": "1",
        "description": "40 richieste nuove (8 per categoria) pre-registrate prima del classificatore v2.",
        "items": [{"input": q, "expected": label, "scorer": "label"} for q, label in [
            ("Quanto fa 15 per 4?", "math"), ("Se ho 20 euro e ne spendo 7, quanti me ne restano?", "math"),
            ("calcola la radice quadrata di 49", "math"),
            ("Un treno percorre 60 km all'ora: quanti km fa in 3 ore?", "math"), ("3/4 + 1/4", "math"),
            ("Quanto è il 20% di 150?", "math"), ("Dividi 84 caramelle tra 7 bambini: quante a testa?", "math"),
            ("(8-3)*2", "math"),
            ("Quante parole ha questo testo: la vita è bella", "text.stats"),
            ("conta i caratteri di: buongiorno", "text.stats"),
            ("Quante frasi ci sono qui? Ciao. Come va? Bene.", "text.stats"),
            ("conta le parole: uno due tre quattro", "text.stats"),
            ("Dimmi quante parole contiene: il sole sorge a est", "text.stats"),
            ("statistiche del testo: Il mare è calmo.", "text.stats"),
            ("Quanti caratteri ha la parola elefante?", "text.stats"),
            ("Conta quante righe ha questo testo:\nprima\nseconda", "text.stats"),
            ("scrivi un ciclo for in Python che stampa da 1 a 10", "code"),
            ("cosa significa questo errore: TypeError: 'NoneType' object is not subscriptable", "code"),
            ("come leggo un file CSV in Java?", "code"),
            ("ottimizza questa query: SELECT * FROM utenti WHERE nome LIKE '%a%'", "code"),
            ("come faccio il merge di due branch con git?", "code"),
            ("scrivi una funzione che calcola il fattoriale", "code"),
            ("spiega la differenza tra let e const in JavaScript", "code"),
            ("il mio script bash non trova il comando, perché?", "code"),
            ("Quali sono le cause della Rivoluzione francese?", "reasoning"),
            ("come mai d'inverno fa più freddo?", "reasoning"),
            ("Spiegami il motivo per cui i prezzi aumentano", "reasoning"),
            ("È meglio studiare la mattina o la sera? Valuta pro e contro", "reasoning"),
            ("perché le api sono importanti per l'ambiente?", "reasoning"),
            ("Quali conseguenze ha la deforestazione?", "reasoning"),
            ("dimostra che la somma degli angoli di un triangolo è 180 gradi", "reasoning"),
            ("Analizza il ruolo dei social network nella politica", "reasoning"),
            ("buonasera!", "chat"), ("scrivimi una lettera di auguri per un compleanno", "chat"),
            ("che ore sono a New York?", "chat"), ("consigliami un libro di fantascienza", "chat"),
            ("come si prepara il tiramisù?", "chat"), ("inventa una storia breve su un drago", "chat"),
            ("chi ha vinto i mondiali del 2006?", "chat"), ("traduci in francese: dove si trova la stazione?", "chat"),
        ]]}, builtin=True),
    parse_dataset({
        "name": "math-words", "version": "1",
        "description": "20 problemi a parole in italiano, pre-registrati prima del risolutore (alcuni volutamente difficili).",
        "items": _num([
            ("Ho 3 mele e ne compro altre 4: quante mele ho?", 7),
            ("Un libro costa 12 euro: quanto costano 5 libri?", 60),
            ("Se ho 20 euro e ne spendo 7, quanti me ne restano?", 13),
            ("Dividi 84 caramelle tra 7 bambini: quante caramelle a testa?", 12),
            ("Un treno percorre 60 km all'ora: quanti km percorre in 3 ore?", 180),
            ("Marco ha 15 figurine e ne regala 6 a Luca. Quante figurine gli rimangono?", 9),
            ("In una classe ci sono 12 maschi e 14 femmine. Quanti alunni ci sono in tutto?", 26),
            ("Una scatola contiene 6 uova. Quante uova ci sono in 8 scatole?", 48),
            ("Ho 50 euro e compro un maglione da 32 euro. Quanto mi resta?", 18),
            ("Quanto è il 20% di 150?", 30), ("Quanto fa 15 per 4?", 60), ("Calcola la radice quadrata di 49", 7),
            ("Un giardiniere pianta 9 file di 7 alberi ciascuna. Quanti alberi pianta?", 63),
            ("Luca legge 25 pagine al giorno. Quante pagine legge in 4 giorni?", 100),
            ("Un pacco di 36 biscotti viene diviso in parti uguali fra 4 amici. Quanti biscotti riceve ciascuno?", 9),
            ("Sul pullman ci sono 40 persone, ne scendono 12. Quante persone restano?", 28),
            ("Anna ha 8 anni, suo padre ne ha 30 in più. Quanti anni ha il padre?", 38),
            ("Quanto fa 100 diviso 4?", 25),
            ("Un biglietto costa 3 euro e 50 centesimi: quanto spendo per 2 biglietti?", 7),
            ("Ho 2 dozzine di uova: quante uova sono?", 24),
        ])}, builtin=True),
)


class DatasetStore:
    def __init__(self, db: Database, now: Now = utcnow) -> None:
        self.db, self._now = db, now
        self._synced = False  # built-ins are registered on first use, never by a read-only command

    def _save(self, ds: Dataset) -> str:
        row = self.db.conn.execute("SELECT id, hash FROM datasets WHERE name = ? AND version = ?",
                                   (ds.name, ds.version)).fetchone()
        if row:
            if row["hash"] != ds.hash:
                raise GenesisError(f"{ds.ref} esiste già con contenuto diverso: aumenta la versione")
            return row["id"]
        ds_id = uuid.uuid4().hex
        with self.db.transaction() as c:
            c.execute("INSERT INTO datasets (id, name, version, description, hash, items, builtin, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (ds_id, ds.name, ds.version, ds.description, ds.hash,
                                                          ds.items_json(), int(ds.builtin), self._now()))
        return ds_id

    def sync_builtin(self) -> None:
        if not self._synced:
            for ds in BUILTIN:
                self._save(ds)
            self._synced = True

    def import_file(self, path: Path) -> dict[str, Any]:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GenesisError(f"dataset illeggibile: {exc}") from exc
        ds = parse_dataset(raw)
        self._save(ds)
        return {"ref": ds.ref, "items": len(ds.items), "hash": ds.hash}

    def get(self, ref: str) -> tuple[str, Dataset]:
        self.sync_builtin()
        name, _, version = ref.partition("@")
        sql = "SELECT * FROM datasets WHERE name = ?" + (" AND version = ?" if version else "")
        row = self.db.conn.execute(sql + " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                                   (name, version) if version else (name,)).fetchone()
        if row is None:
            raise GenesisError(f"dataset inesistente: {ref}")
        ds = parse_dataset({"name": row["name"], "version": row["version"], "description": row["description"],
                            "items": json.loads(row["items"])}, bool(row["builtin"]))
        if ds.hash != row["hash"]:
            raise GenesisError(f"{ds.ref}: contenuto alterato (hash diverso da quello registrato)")
        return row["id"], ds

    def list(self) -> list[dict[str, Any]]:
        self.sync_builtin()
        rows = self.db.conn.execute("SELECT * FROM datasets ORDER BY name, created_at").fetchall()
        return [{"ref": f"{r['name']}@{r['version']}", "name": r["name"], "version": r["version"],
                 "description": r["description"], "items": len(json.loads(r["items"])), "hash": r["hash"],
                 "builtin": bool(r["builtin"])} for r in rows]
