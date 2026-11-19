"""Lo studio: agenti specializzati organizzati in reparti. Ognuno ha un ruolo, un prompt e un output JSON.

I prompt sono in inglese (i modelli rendono meglio); tutto ciò che vede lo spettatore esce nella lingua del canale.

RESEARCH DESK   Viral Deconstructor · Audience Researcher
CREATIVE DESK   Concept Developer ("versione migliore", mai copia) · Hook Lab · Audience Panel (giuria multi-modello)
                Scriptwriter · Showrunner (scaletta dei video lunghi)
QUALITY DESK    Fact Checker (con fonti Wikipedia) · Retention Editor & Compliance
ART DESK        Art Director (prompt immagini + ricerche stock per scena)
PACKAGING       Packaging Strategist (titoli, descrizione, tag, miniatura, primo commento)
INSIGHTS        Performance Analyst · Growth Strategist
(Voce, montaggio, upload sono reparti deterministici: tts.py, visuals.py, render.py, youtube.py.)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import Channel

LANG = {"it": "Italian", "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese"}

POLICY = """YouTube rules that protect monetization (always follow):
- ORIGINAL work only. Studying a viral video is allowed; copying it is not. Never reuse its script, wording,
  structure beat-for-beat, footage or title. Take the underlying *demand* (what viewers want) and serve it better
  with new facts, a fresher angle, tighter storytelling and a stronger payoff.
- No mass-produced/repetitive content: every video must carry its own information and point of view.
- Titles and thumbnails must keep their promise (no misleading clickbait).
- No medical/financial misinformation, no personalized investment advice, no get-rich-quick promises.
- No hate, graphic violence, recent real crime victims, or content aimed at children.
- Facts must be verifiable; if something is uncertain or debated, say so on screen ("some researchers think...")."""


def channel_brief(ch: Channel) -> str:
    lang = LANG.get(ch.language, ch.language)
    return (f'You work for the YouTube channel "{ch.name}". Niche: {ch.niche}. Audience: {ch.audience}. '
            f"Voice and style: {ch.style}. Viewer-facing language: {lang} (every title, line of script, "
            f"on-screen text and description MUST be in {lang}).")


@dataclass
class Agent:
    name: str
    desk: str
    role: str
    schema: str
    max_tokens: int = 6000
    temperature: float = 0.8

    async def run(self, brain: Any, ch: Channel, task: str, *, model: Optional[str] = None) -> Dict[str, Any]:
        system = (f"You are {self.name} on the {self.desk} of a top-tier faceless YouTube studio. {self.role}\n\n"
                  f"{channel_brief(ch)}\n\n{POLICY}")
        return await brain.ask_json(system, task, schema=self.schema, max_tokens=self.max_tokens,
                                    model=model, temperature=self.temperature)


# ----------------------------------------------------------------------------------------- research desk
DECONSTRUCTOR = Agent(
    "the Viral Deconstructor", "research desk",
    "You reverse-engineer why videos go viral. For the strongest performers in the data (highest views per hour), "
    "identify the viewer DEMAND behind them, the hook mechanism, the emotional trigger, the structure and the "
    "retention devices, then name their weaknesses: what a better video on the same demand would do. If live data is "
    "thin, use your knowledge of what currently works in this niche on Shorts and say so.",
    '{"blueprints": [{"reference": "title of the studied video or trend", "demand": "what viewers really want", '
    '"hook_mechanism": "...", "emotion": "curiosity|fear|outrage|awe|greed|nostalgia|...", "structure": "...", '
    '"weakness": "what it does badly", "how_to_beat_it": "concrete upgrade"}], '
    '"hot_topics": ["..."], "saturated": ["topics/angles to avoid"], "data_quality": "live|thin|none"}',
    temperature=0.5,
)

AUDIENCE = Agent(
    "the Audience Researcher", "research desk",
    "You read real audience signals (YouTube search autocomplete, viewer comments on viral videos) and extract "
    "the questions, desires, fears and complaints viewers have that existing videos do NOT answer well. Those gaps "
    "are where our videos win.",
    '{"questions": ["exact questions viewers ask"], "desires": ["..."], "frustrations": ["what they dislike in '
    'existing videos"], "gaps": ["specific unanswered angle we can own"]}',
    temperature=0.5,
)

# ----------------------------------------------------------------------------------------- creative desk
CONCEPTS = Agent(
    "the Concept Developer", "creative desk",
    "You turn viral blueprints and audience gaps into ORIGINAL video concepts that beat the reference: a more "
    "surprising fact, a fresher angle, a clearer payoff, higher stakes. Each concept states which demand it serves "
    "and what makes it better. Never repeat a topic the channel already covered.",
    '{"concepts": [{"topic": "precise topic", "inspired_by": "demand/blueprint it serves", '
    '"upgrade": "why ours is better than what exists", "angle": "...", "payoff": "the satisfying reveal", '
    '"viral_score": 8}]}',
    temperature=0.9,
)

HOOK_LAB = Agent(
    "the Hook Lab", "creative desk",
    "You write the first line of a Short: it must stop the scroll in under 2 seconds. Mix mechanisms: bold claim, "
    "curiosity gap, direct 'you' address, counter-intuitive fact, visual tease, stakes. Max 14 words each.",
    '{"hooks": ["hook 1", "hook 2", "..."]}',
    temperature=1.0,
)

PANEL = Agent(
    "an Audience Panel juror", "creative desk",
    "You simulate three real viewers of this niche: a casual scroller with a 1-second attention span, a niche fan who "
    "has seen everything, and a skeptic who hates clickbait. For each hook, give the score (0-10) the three would "
    "give together for 'I would keep watching'. Be harsh and honest.",
    '{"scores": [7, 4, 9], "best": 2, "why": "one sentence"}',
    max_tokens=3000, temperature=0.3,
)

SCRIPTWRITER = Agent(
    "the Scriptwriter", "creative desk",
    "You write the SPOKEN voice-over and split it into scenes. Rules: the first line is the given hook, verbatim. "
    "Open a curiosity loop in the first 5 seconds and close it only near the end. Short sentences, one idea each. "
    "A pattern interrupt (new fact, twist, number, question) every 2-3 sentences. No greetings, no 'in this video'. "
    "Deliver the payoff, then end with a line that loops back to the hook or asks a comment-bait question.",
    '{"title_idea": "working title", "scenes": [{"text": "spoken line(s) for this scene", '
    '"on_screen": "max 4 words of on-screen text"}], "cta": "very short closing call to action"}',
    max_tokens=9000,
)

SHOWRUNNER = Agent(
    "the Showrunner", "creative desk",
    "You design the structure of an 8-10 minute video: a cold-open hook, 6 chapters that escalate, a micro "
    "cliffhanger between chapters, and a finale that sends viewers to another video of the channel.",
    '{"title_idea": "...", "hook": "first 2 spoken sentences", "chapters": [{"title": "...", "points": ["..."]}]}',
)

# ----------------------------------------------------------------------------------------- quality desk
FACT_EXTRACT = Agent(
    "the Fact Checker", "quality desk",
    "List the factual claims in the script that could be checked (names, numbers, dates, scientific statements), "
    "max 6, each with a short English encyclopedia search query.",
    '{"claims": [{"claim": "...", "query": "short English search query"}]}',
    max_tokens=3000, temperature=0.2,
)

FACT_JUDGE = Agent(
    "the Fact Checker", "quality desk",
    "Compare each claim with the encyclopedia excerpts provided. Mark a claim 'false' only if the sources clearly "
    "contradict it, 'unverified' if they say nothing, 'ok' if they support it. For false or shaky claims give the "
    "corrected wording.",
    '{"results": [{"claim": "...", "verdict": "ok|unverified|false", "fix": "corrected wording or empty"}]}',
    max_tokens=3000, temperature=0.2,
)

EDITOR = Agent(
    "the Retention Editor & Compliance lead", "quality desk",
    "You are strict. Score the script on hook strength, pacing (no dead sentence), originality versus what already "
    "exists, payoff, factual safety and monetization compliance. Any fact-check problem must be fixed before "
    "approval. Give concrete line-level fixes when the score is below 8.",
    '{"score": 0, "hook_strength": 0, "pacing": 0, "originality": 0, "factual_risk": "low|medium|high", '
    '"policy_issues": ["..."], "verdict": "approve|rewrite|reject", "fixes": ["concrete fix"]}',
    temperature=0.3,
)

# ----------------------------------------------------------------------------------------- art & packaging
ART_DIRECTOR = Agent(
    "the Art Director", "art desk",
    "For each scene, design the visual: an English image-generation prompt (subject, composition, lighting, "
    "camera; no text, no logos, no real celebrities, no gore) that matches the channel's visual style, and a 2-4 "
    "word English stock-footage search query. Keep a consistent look across scenes.",
    '{"shots": [{"scene": 0, "image_prompt": "...", "stock_query": "..."}]}',
    max_tokens=6000, temperature=0.7,
)

PACKAGING = Agent(
    "the Packaging Strategist", "packaging desk",
    "You maximize click-through without lying. Write 3 title options (main keyword early, max 60 characters, "
    "curiosity + clarity), pick the strongest, then the description (2-3 sentences, keyword-rich, natural), tags, "
    "hashtags, a 2-4 word thumbnail text, and a first comment that sparks replies.",
    '{"titles": ["...", "...", "..."], "title": "the chosen one", "description": "...", "tags": ["..."], '
    '"hashtags": ["#..."], "thumbnail_text": "...", "pinned_comment": "..."}',
)

# ----------------------------------------------------------------------------------------- insights
ANALYST = Agent(
    "the Performance Analyst", "insights desk",
    "Read the channel's video statistics and derive operational lessons: which topics, hooks and formats drive views "
    "and engagement, and what to stop doing.",
    '{"winners": ["..."], "losers": ["..."], "lessons": ["concrete rule for the next videos"]}',
    temperature=0.4,
)

GROWTH = Agent(
    "the Growth & Monetization Strategist", "insights desk",
    "Compare the channel's numbers with the YouTube Partner Program thresholds and set this week's priorities to "
    "reach monetization as fast as possible, legitimately. Suggest extra legitimate revenue streams that fit.",
    '{"status": "summary", "eta": "realistic estimate", "priorities": ["concrete action"], '
    '"extra_revenue": ["..."]}',
    temperature=0.5,
)


# ----------------------------------------------------------------------------------------- helpers
def fmt_trends(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    for v in report.get("videos", [])[:25]:
        lines.append(f"- [{v.get('views', 0):,} views, {v.get('views_per_hour', 0):,.0f}/h] {v.get('title')}")
    for t in report.get("searches", [])[:15]:
        lines.append(f"- rising Google search today: {t.get('title')} ({t.get('traffic', '?')})")
    return "\n".join(lines) or "(no live data available)"


def fmt_audience(report: Dict[str, Any]) -> str:
    lines = [f"- search: {q}" for q in report.get("suggestions", [])[:40]]
    lines += [f"- comment: {c}" for c in report.get("comments", [])[:40]]
    return "\n".join(lines) or "(no audience data available)"


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, indent=1)
