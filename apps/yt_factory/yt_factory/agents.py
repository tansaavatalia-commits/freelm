"""Gli agenti, organizzati in team. Ognuno ha un ruolo, un prompt di sistema e un output JSON.

Team ricerca     -> TrendAnalyst
Team creativo    -> Ideator, Scriptwriter
Team qualità     -> Reviewer (originalità, policy YouTube/monetizzazione, rischio fattuale)
Team SEO         -> SEOSpecialist
Team analytics   -> PerformanceAnalyst
Team crescita    -> GrowthStrategist (avanzamento verso la monetizzazione)
(Produzione e pubblicazione sono "agenti" deterministici: tts/render/youtube.)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from .config import Channel
from .llm import Brain

LANG = {"it": "italiano", "en": "English", "es": "español", "fr": "français", "de": "Deutsch", "pt": "português"}

POLICY = """Regole YouTube che proteggono la monetizzazione (rispettale sempre):
- contenuto ORIGINALE: mai copiare/riassumere video altrui parola per parola, mai ripubblicare materiale altrui;
  ispirarsi a un trend (argomento, formato, struttura dell'hook) è lecito, copiarlo no;
- niente contenuti "di massa" ripetitivi: ogni video deve avere un'informazione o un punto di vista proprio;
- titoli e miniature devono mantenere la promessa (niente clickbait ingannevole);
- niente disinformazione medica/finanziaria, niente consigli di investimento personalizzati, niente promesse di guadagno;
- niente odio, violenza esplicita, vittime reali di cronaca recente, contenuti per bambini (made for kids = no);
- fatti verificabili: se un dato è incerto, dillo ("secondo alcuni studi...")."""


def channel_brief(ch: Channel) -> str:
    return (
        f"Canale YouTube \"{ch.name}\". Nicchia: {ch.niche}. Pubblico: {ch.audience}. "
        f"Stile: {ch.style}. Lingua dei contenuti: {LANG.get(ch.language, ch.language)}."
    )


@dataclass
class Agent:
    name: str
    team: str
    role: str
    schema: str
    max_tokens: int = 6000

    async def run(self, brain: Brain, ch: Channel, task: str) -> Dict[str, Any]:
        system = f"Sei {self.name}, del team {self.team}. {self.role}\n\n{channel_brief(ch)}\n\n{POLICY}"
        return await brain.ask_json(system, task, schema=self.schema, max_tokens=self.max_tokens)


TREND_ANALYST = Agent(
    "il Trend Analyst", "ricerca",
    "Analizzi i dati di tendenza (video più visti, velocità di visualizzazioni, ricerche Google del momento) "
    "e capisci PERCHÉ funzionano: argomenti, formati, schemi di hook. Adatti tutto alla nicchia del canale. "
    "Se i dati sono scarsi, usa la tua conoscenza dei formati Shorts virali attuali e dillo.",
    '{"hot_topics": ["argomento caldo adatto alla nicchia", "..."], '
    '"viral_patterns": ["schema che funziona, es. \'3 cose che...\'", "..."], '
    '"hook_formulas": ["formula di hook", "..."], "avoid": ["cosa è saturo o rischioso"], '
    '"data_quality": "live|scarsa|nessuna"}',
)

IDEATOR = Agent(
    "l'Ideatore", "creativo",
    "Generi idee di video ad alto potenziale virale, ognuna con un angolo ORIGINALE e un hook forte. "
    "Mai ripetere argomenti già fatti dal canale.",
    '{"ideas": [{"topic": "argomento preciso", "angle": "angolo originale", '
    '"hook": "prima frase (max 12 parole)", "why_viral": "perché funzionerà", "viral_score": 8}]}',
)

SCRIPTWRITER = Agent(
    "lo Sceneggiatore", "creativo",
    "Scrivi il testo PARLATO del video (voce fuori campo) e lo dividi in scene con indicazioni visive. "
    "Prima frase = hook che blocca lo scroll in 2 secondi. Frasi corte, ritmo alto, niente saluti iniziali. "
    "Finale che si ricollega all'inizio (loop) o fa una domanda per i commenti.",
    '{"title_idea": "titolo provvisorio", "scenes": [{"text": "frase/i parlate della scena", '
    '"visual": "2-4 parole chiave in inglese per immagini stock", "on_screen": "max 4 parole a schermo"}], '
    '"cta": "invito finale breve"}',
    max_tokens=9000,
)

OUTLINER = Agent(
    "il Capo Autore", "creativo",
    "Progetti la struttura di un video lungo (8-10 minuti): hook iniziale forte, 6 capitoli con progressione e "
    "micro-cliffhanger tra un capitolo e l'altro, finale che rimanda a un altro video del canale.",
    '{"title_idea": "...", "hook": "prime 2 frasi parlate", "chapters": [{"title": "...", "points": ["..."]}]}',
)

REVIEWER = Agent(
    "il Revisore Qualità & Policy", "qualità",
    "Sei severo. Valuti lo script: forza dell'hook, ritmo, originalità, correttezza dei fatti, rispetto delle "
    "regole di monetizzazione. Se il voto è basso, dai correzioni concrete.",
    '{"score": 0, "hook_strength": 0, "originality": 0, "factual_risk": "basso|medio|alto", '
    '"policy_issues": ["..."], "verdict": "approve|rewrite|reject", "fixes": ["correzione concreta", "..."]}',
)

SEO = Agent(
    "lo Specialista SEO YouTube", "SEO",
    "Scrivi titolo, descrizione, tag e testo miniatura per massimizzare click e scoperta senza ingannare. "
    "Titolo max 70 caratteri, parola chiave principale all'inizio. Descrizione: 2-3 frasi + hashtag.",
    '{"title": "...", "description": "...", "tags": ["..."], "hashtags": ["#..."], '
    '"thumbnail_text": "max 4 parole", "pinned_comment": "domanda che stimola commenti"}',
)

ANALYST = Agent(
    "l'Analista Performance", "analytics",
    "Leggi le statistiche dei video pubblicati e ricavi lezioni operative: quali argomenti, hook e "
    "formati portano più visualizzazioni e interazioni, e cosa smettere di fare.",
    '{"winners": ["..."], "losers": ["..."], "lessons": ["regola concreta per i prossimi video", "..."]}',
)

GROWTH = Agent(
    "lo Stratega Crescita & Monetizzazione", "crescita",
    "Guardi i numeri del canale rispetto alle soglie del Programma Partner YouTube e decidi le priorità "
    "della settimana per raggiungere la monetizzazione il prima possibile, in modo lecito.",
    '{"status": "sintesi", "eta": "stima realistica", "priorities": ["azione concreta", "..."], '
    '"extra_revenue": ["fonte di guadagno lecita aggiuntiva", "..."]}',
)


def fmt_trends(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    for v in report.get("videos", [])[:25]:
        lines.append(f"- [{v.get('views', 0):,} views, {v.get('views_per_hour', 0):,.0f}/h] {v.get('title')}")
    for t in report.get("searches", [])[:15]:
        lines.append(f"- ricerca Google in crescita: {t.get('title')} ({t.get('traffic', '?')})")
    return "\n".join(lines) or "(nessun dato live disponibile)"


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, indent=1)
