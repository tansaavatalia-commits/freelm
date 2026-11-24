"""Versioned agent definitions: 8 built-in agents plus owner-defined JSON files in <home>/agents/.

An agent acts as principal ``agent.<id>``. Its permission level comes only from the
owner's grants (genesis.toml); a definition cannot raise it. New agents start with
no grant at all, so they cannot act until the owner allows them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..errors import GenesisError
from ..intelligence.base import TASK_TYPES

ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


@dataclass(frozen=True)
class AgentConfig:
    id: str
    name: str
    version: str
    role: str
    objective: str
    instructions: str
    task_types: tuple[str, ...]
    success_criteria: str
    max_steps: int = 1
    builtin: bool = False

    @property
    def principal(self) -> str:
        return f"agent.{self.id}"


def _a(id_: str, name: str, role: str, objective: str, instructions: str, types: tuple[str, ...], criteria: str) -> AgentConfig:
    return AgentConfig(id_, name, "1.0", role, objective, instructions, types, criteria, builtin=True)


BUILTIN: tuple[AgentConfig, ...] = (
    _a("director", "Director", "coordinamento", "Scomporre un obiettivo e assegnare i sotto-compiti agli specialisti.",
       "Coordina: non risponde direttamente, scompone e delega.", ("chat", "reasoning"),
       "ogni sotto-compito ha un responsabile e un esito"),
    _a("researcher", "Researcher", "ricerca", "Raccogliere e riassumere informazioni.",
       "Rispondi in modo fattuale e conciso. Se non sei sicuro, dillo esplicitamente.", ("chat", "reasoning"),
       "risposta pertinente, con le incertezze dichiarate"),
    _a("developer", "Developer", "sviluppo", "Scrivere e spiegare codice.",
       "Rispondi con codice corretto e minimo, poi una spiegazione breve.", ("code",),
       "codice sintatticamente valido e spiegato"),
    _a("analyst", "Analyst", "analisi", "Calcoli, numeri e analisi strutturate.",
       "Mostra il ragionamento in passi numerati e dai il risultato finale su una riga.",
       ("math", "text.stats", "reasoning"), "risultato verificabile"),
    _a("creator", "Creator", "creazione", "Testi creativi e proposte.",
       "Scrivi in italiano chiaro, originale, senza copiare opere esistenti.", ("chat",),
       "testo originale e coerente con la richiesta"),
    _a("manager", "Manager", "gestione", "Organizzare attività e priorità.",
       "Rispondi con un elenco di azioni concrete ordinate per priorità.", ("chat", "reasoning"),
       "azioni concrete e ordinate"),
    _a("verifier", "Verifier", "verifica", "Controllare i risultati con regole deterministiche.",
       "Verifica senza fidarti del modello che ha prodotto il risultato.", ("math", "text.stats"),
       "ogni controllo ha esito e motivazione"),
    _a("security", "Security", "sicurezza", "Valutare i rischi di una richiesta o di un risultato.",
       "Elenca i rischi concreti e le mitigazioni; non eseguire azioni.", ("chat", "reasoning"),
       "rischi concreti con mitigazione"),
)


def load_agents(home: Path) -> dict[str, AgentConfig]:
    agents = {a.id: a for a in BUILTIN}
    folder = Path(home) / "agents"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        agent = parse_agent(path)
        if agent.id in agents:
            raise GenesisError(f"{path}: l'agente '{agent.id}' esiste già")
        agents[agent.id] = agent
    return agents


def parse_agent(path: Path) -> AgentConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenesisError(f"{path}: definizione di agente illeggibile ({exc})") from exc
    required = {"id", "name", "version", "role", "objective", "instructions", "task_types", "success_criteria"}
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - {"max_steps"}:
        raise GenesisError(f"{path}: campi richiesti {sorted(required)} (facoltativo: max_steps)")
    if not isinstance(raw["id"], str) or not ID_RE.match(raw["id"]):
        raise GenesisError(f"{path}: id non valido")
    types = raw["task_types"]
    if not isinstance(types, list) or not types or not set(types) <= set(TASK_TYPES):
        raise GenesisError(f"{path}: task_types deve essere un sottoinsieme di {list(TASK_TYPES)}")
    steps = raw.get("max_steps", 1)
    if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 5:
        raise GenesisError(f"{path}: max_steps deve essere tra 1 e 5")
    text = {k: raw[k] for k in required - {"task_types"}}
    if not all(isinstance(v, str) and v.strip() for v in text.values()):
        raise GenesisError(f"{path}: i campi di testo non possono essere vuoti")
    return AgentConfig(**text, task_types=tuple(types), max_steps=steps)
