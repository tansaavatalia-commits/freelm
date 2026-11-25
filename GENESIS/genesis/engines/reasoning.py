"""Genesis Reasoning Engine: deterministic language rules, no model.

* classifier v2: v1 plus implicit counting requests, arithmetic written in words, word problems,
  more programming vocabulary and causal/evaluative questions (weaknesses found in R-001).
* math v2: arithmetic in words ("15 per 4", "radice quadrata di 49", "20% di 150") and simple
  one-step word problems, with the operation chosen from Italian cue words and explained.

These are heuristics: their accuracy is measured in the Research Lab, never assumed.
"""

from __future__ import annotations

import re
from typing import Any

from .. import __version__
from ..intelligence.base import EngineError
from ..intelligence.local import classify as classify_v1
from ..intelligence.local import evaluate, extract_expression, format_number
from .base import Component, EngineOpError, GenesisEngine, Operation, text_arg

NUM = r"\d+(?:[.,]\d+)?"
_STATS_V2 = re.compile(
    r"^\s*(conta\s+(le\s+)?parole|statistiche(\s+del)?\s+testo)"
    r"|\b(quant[ie]|conta\w*|dimmi\s+quant[ie])\b[^?]*?\b(parol\w*|caratter\w*|letter\w*|frasi|frase|righe|riga)\b",
    re.I)
_CODE_V2 = re.compile(
    r"```|\b(def|class|function|funzion[ei]|import|python|javascript|typescript|java|kotlin|swift|php|ruby|rust|"
    r"golang|html|css|sql|query|select|regex|codice|bug|script|bash|shell|powershell|git|branch|commit|merge|"
    r"compilat\w*|compilazion\w*|traceback|eccezion\w*|exception|variabil\w*|ciclo\s+(for|while)|api|json)\b"
    r"|\b\w+Error\b|c\+\+|c#", re.I)
_REASON_V2 = re.compile(
    r"\b(perch[eé]|dimostra|ragiona\w*|analizza|confronta|why|prove|caus[ae]|motiv[oi]|come\s+mai|"
    r"conseguenz[ae]|valuta|pro\s+e\s+contro|vantaggi|svantaggi|ragion[ei]|cosa\s+succederebbe|è\s+meglio)\b", re.I)
_QUANTITY_Q = re.compile(r"\bquant[oaie]\b", re.I)

# word-problem cues (checked in this order)
_DIV = re.compile(r"\b(divid\w*|divis\w*|in\s+parti\s+uguali|a\s+testa)\b|\b(tra|fra)\s+\d", re.I)
_SUB = re.compile(r"\bne\s+(spend|regal|perd|mangi|vend|tolg|tog)\w*|\b(rest\w*|riman\w*|scend\w*|di\s+meno|meno)\b", re.I)
_MUL = re.compile(r"\b(ciascun[ao]?|ognun[oa]|ogni|volte|al\s+giorno|all'ora|cost[ao]|contiene|contengono|per\s+\d)\b", re.I)
_ADD = re.compile(r"\b(compr\w*|aggiung\w*|in\s+più|altr[ie]|ricev\w*|trov\w*|in\s+tutto|totale|arriv\w*|sal\w*)\b", re.I)


def normalize_math_text(prompt: str) -> str:
    """Arithmetic written in words -> expression the safe evaluator understands."""
    text = extract_expression(prompt)
    text = re.sub(r"\bla\s+radice\s+quadrata\s+di\s+(" + NUM + ")", r"sqrt(\1)", text, flags=re.I)
    text = re.sub(r"\bradice\s+quadrata\s+di\s+(" + NUM + ")", r"sqrt(\1)", text, flags=re.I)
    text = re.sub(r"\b(il\s+)?(" + NUM + r")\s*(%|per\s*cento)\s+d[ie]\w*\s+(" + NUM + ")", r"(\2/100*\4)", text, flags=re.I)
    words = {"per": "*", "x": "*", "diviso": "/", "più": "+", "meno": "-", "elevato a": "**"}
    for word, op in words.items():
        text = re.sub(rf"(?<=[\d)])\s+{word}\s+(?=[\d(])", op, text, flags=re.I)
    text = re.sub(r"^\s*(quanto\s+è|quant'è)\s+", "", text, flags=re.I)
    return text.replace(",", ".") if re.fullmatch(r"[\d\s.,+\-*/()%]+", text) else text


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in re.findall(NUM, text)]


def solve_word_problem(prompt: str) -> tuple[float, str]:
    """One-step Italian word problems. Returns (value, explanation) or raises EngineError."""
    text = prompt.lower()
    text = re.sub(r"(\d+)\s+euro\s+e\s+(\d{1,2})\s+centesimi", lambda m: f"{int(m[1]) + int(m[2]) / 100} euro", text)
    converted = False

    def dozen(m: re.Match[str]) -> str:
        nonlocal converted
        converted = True
        return f"{float(m[1].replace(',', '.')) * 12:g} "
    text = re.sub(r"(" + NUM + r")\s+dozzin[ae]\s*", dozen, text)
    percent = re.search(r"(" + NUM + r")\s*(%|per\s*cento)\s+d[ie]\w*\s+(" + NUM + ")", text)
    if percent:
        a, b = float(percent[1].replace(",", ".")), float(percent[3].replace(",", "."))
        return a / 100 * b, f"{a:g}% di {b:g} = {a / 100 * b:g}"
    numbers = _numbers(text)
    if len(numbers) == 1 and converted:
        return numbers[0], f"conversione: {numbers[0]:g}"
    if len(numbers) != 2:
        raise EngineError("problema non riconosciuto: servono esattamente due numeri")
    a, b = numbers
    if _DIV.search(text):
        if b == 0:
            raise EngineError("divisione per zero")
        return a / b, f"{a:g} ÷ {b:g} = {a / b:g}"
    if _SUB.search(text):
        return a - b, f"{a:g} − {b:g} = {a - b:g}"
    if _MUL.search(text):
        return a * b, f"{a:g} × {b:g} = {a * b:g}"
    if _ADD.search(text):
        return a + b, f"{a:g} + {b:g} = {a + b:g}"
    raise EngineError("operazione non riconosciuta nel testo")


def math_v2(prompt: str) -> tuple[str, str]:
    """(answer, method): exact arithmetic first, word problem second."""
    try:
        return format_number(evaluate(normalize_math_text(prompt))), "calcolo esatto"
    except EngineError:
        value, explanation = solve_word_problem(prompt)
        return format_number(round(value, 10)), f"problema a parole: {explanation}"


def classify_v2(prompt: str) -> str:
    if _STATS_V2.search(prompt):
        return "text.stats"
    try:
        evaluate(normalize_math_text(prompt))
        return "math"
    except EngineError:
        pass
    try:
        solve_word_problem(prompt)
        return "math"
    except EngineError:
        pass
    if _QUANTITY_Q.search(prompt) and len(_numbers(prompt)) >= 2 and not _CODE_V2.search(prompt):
        return "math"
    if _CODE_V2.search(prompt):
        return "code"
    if _REASON_V2.search(prompt):
        return "reasoning"
    return "chat"


CLASSIFIERS = {"v1": classify_v1, "v2": classify_v2}


def decompose_goal(goal: str, limit: int = 6) -> list[str]:
    lines = [re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", ln).strip() for ln in goal.splitlines()]
    parts = [ln for ln in lines if ln]
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r";|\bpoi\b", goal) if p.strip()]
    return parts[:limit] or [goal.strip()]


class ReasoningEngine(GenesisEngine):
    id, name, version = "reasoning", "Genesis Reasoning Engine", f"2.0@{__version__}"
    description = "Classificazione delle richieste, calcolo in linguaggio naturale, scomposizione di obiettivi."
    components = (
        Component("classificatore a regole v1/v2", "algoritmo", "espressioni regolari su parole chiave italiane"),
        Component("valutatore aritmetico sicuro", "algoritmo", "albero sintattico con sola aritmetica ammessa"),
        Component("risolutore di problemi a parole", "algoritmo", "estrae due numeri e sceglie l'operazione da parole indizio"),
        Component("scomposizione di obiettivi", "algoritmo", "elenchi numerati, punto e virgola, 'poi'"),
    )
    operations = (
        Operation("classify", 1, "classifica una richiesta", '{"text": "...", "version": "v1|v2"}'),
        Operation("solve", 1, "risolve un calcolo o un problema a parole", '{"text": "..."}'),
        Operation("decompose", 1, "scompone un obiettivo in sotto-compiti", '{"text": "..."}'),
    )

    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any:
        text = text_arg(payload)
        if op == "classify":
            version = payload.get("version", "v2")
            if version not in CLASSIFIERS:
                raise EngineOpError("version deve essere v1 o v2")
            return {"task_type": CLASSIFIERS[version](text), "version": version}
        if op == "solve":
            try:
                answer, method = math_v2(text)
            except EngineError as exc:
                raise EngineOpError(str(exc)) from exc
            return {"answer": answer, "method": method}
        if op == "decompose":
            return {"subtasks": decompose_goal(text)}
        raise EngineOpError(f"operazione sconosciuta: {op}")
