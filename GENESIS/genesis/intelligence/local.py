"""Local Engine: capabilities implemented by GÉNESIS itself, deterministic, no model, no network.

* ``math``: arithmetic through a whitelist AST evaluator (never ``eval``).
* ``text.stats``: word/character/line/sentence counts.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Callable

from .. import __version__
from .base import EngineError, Provider, ProviderSpec, Request

MAX_EXPRESSION = 200
MAX_NODES = 100
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "log": math.log, "log10": math.log10,
          "exp": math.exp, "sin": math.sin, "cos": math.cos, "tan": math.tan}
_CONSTS = {"pi": math.pi, "e": math.e}
_LEAD = re.compile(r"^\s*(quanto\s+fa|quanto\s+vale|calcola|risolvi|what\s+is|compute)\s*:?\s*", re.I)
_STATS = re.compile(r"^\s*(conta\s+(le\s+)?parole|statistiche(\s+del)?\s+testo)\s*:?\s*", re.I)
_CODE = re.compile(r"```|\b(def|class|function|import|python|javascript|typescript|codice|bug|sql|regex)\b", re.I)
_REASON = re.compile(r"\b(perch[eé]|dimostra|ragiona|analizza|confronta|why|prove)\b", re.I)


def extract_expression(prompt: str) -> str:
    text = _LEAD.sub("", prompt.strip()).rstrip(" ?=.!")
    text = text.replace("^", "**").replace("×", "*").replace("÷", "/")
    return re.sub(r"(\d)\s*x\s*(\d)", r"\1*\2", text)


def evaluate(expression: str) -> int | float:
    if len(expression) > MAX_EXPRESSION:
        raise EngineError("espressione troppo lunga")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise EngineError("non è un'espressione matematica") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise EngineError("espressione troppo complessa")
    value = _eval(tree.body)
    if isinstance(value, float) and not math.isfinite(value):
        raise EngineError("risultato non finito")
    return value


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e12):
            raise EngineError("potenza troppo grande")
        try:
            return _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise EngineError("divisione per zero") from exc
        except OverflowError as exc:
            raise EngineError("risultato troppo grande") from exc
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords and 1 <= len(node.args) <= 2):
        try:
            return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
        except (ValueError, TypeError, OverflowError) as exc:
            raise EngineError(f"argomento non valido per {node.func.id}") from exc
    raise EngineError("elemento non ammesso nell'espressione")


def format_number(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    if isinstance(value, int):
        if abs(value) < 10**30:
            return str(value)
        return f"un numero di {int(math.log10(abs(value))) + 1} cifre"
    return f"{value:.12g}"


def text_stats(text: str) -> str:
    body = _STATS.sub("", text, count=1).strip()
    words = len(body.split())
    sentences = len([s for s in re.split(r"[.!?]+", body) if s.strip()])
    lines = len(body.splitlines()) if body else 0
    return f"parole: {words} · caratteri: {len(body)} · righe: {lines} · frasi: {sentences}"


def classify(prompt: str) -> str:
    """Rule-based task classification (transparent and deterministic)."""
    if _STATS.match(prompt):
        return "text.stats"
    try:
        evaluate(extract_expression(prompt))
        return "math"
    except EngineError:
        pass
    if _CODE.search(prompt):
        return "code"
    if _REASON.search(prompt):
        return "reasoning"
    return "chat"


class LocalEngine(Provider):
    def __init__(self, math: Callable[[], Callable[[str], str]] | None = None) -> None:
        self._math = math  # active math version, read at call time

    spec = ProviderSpec(
        id="local", name="Motore locale GÉNESIS", version=__version__, kind="local",
        capabilities=frozenset({"math", "text.stats"}), cost="free", quality=5, method="deterministico",
        requirements="nessuno",
    )

    def run(self, request: Request, task_type: str) -> str:
        if task_type == "math":
            if self._math is not None:
                return self._math()(request.prompt)
            return format_number(evaluate(extract_expression(request.prompt)))
        if task_type == "text.stats":
            return text_stats(request.prompt)
        raise EngineError(f"il motore locale non gestisce '{task_type}'")
