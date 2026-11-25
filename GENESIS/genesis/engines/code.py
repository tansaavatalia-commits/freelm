"""Genesis Code Engine: static analysis of Python and JSON with the standard library (never executes code)."""

from __future__ import annotations

import ast
import json
from typing import Any

from .. import __version__
from .base import Component, EngineOpError, GenesisEngine, Operation, text_arg

_DANGEROUS = {"eval", "exec", "compile", "__import__"}
_DANGEROUS_ATTR = {("os", "system"), ("os", "popen"), ("pickle", "load"), ("pickle", "loads"),
                   ("marshal", "loads"), ("shutil", "rmtree")}
_BRANCHES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert, ast.comprehension)


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCHES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.Match):
            score += len(child.cases)
    return score


def _call_name(call: ast.Call) -> tuple[str | None, str]:
    f = call.func
    if isinstance(f, ast.Name):
        return None, f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id, f.attr
    return None, ""


def analyze_python(source: str) -> dict[str, Any]:
    lines = source.count("\n") + 1
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"syntax_ok": False, "lines": lines,
                "error": {"line": exc.lineno, "column": exc.offset, "message": exc.msg}}
    functions, classes, imports, risks = [], [], {}, []
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "line": node.lineno, "args": len(node.args.args),
                              "complexity": _complexity(node), "docstring": ast.get_docstring(node) is not None})
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno})
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imports[a.asname or a.name] = node.lineno
        elif isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
        if isinstance(node, ast.Call):
            owner, name = _call_name(node)
            shell = any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True
                        for k in node.keywords)
            if (owner is None and name in _DANGEROUS) or (owner, name) in _DANGEROUS_ATTR or \
                    (owner == "subprocess" and shell) or (owner == "yaml" and name == "load"):
                risks.append({"line": node.lineno, "call": f"{owner + '.' if owner else ''}{name}",
                              "reason": "shell=True" if shell else "esecuzione o deserializzazione non sicura"})
    unused = sorted(n for n in imports if n not in used and n != "*")
    return {"syntax_ok": True, "lines": lines, "functions": functions, "classes": classes,
            "imports": sorted(imports), "unused_imports": unused, "risky_calls": risks,
            "max_complexity": max((f["complexity"] for f in functions), default=0),
            "functions_without_docstring": [f["name"] for f in functions if not f["docstring"]]}


def check_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"valid": False, "error": {"line": exc.lineno, "column": exc.colno, "message": exc.msg}}
    return {"valid": True, "type": type(value).__name__}


class CodeEngine(GenesisEngine):
    id, name, version = "code", "Genesis Code Engine", f"1.0@{__version__}"
    description = "Analisi statica del codice Python e dei file JSON. Non esegue mai il codice."
    components = (
        Component("analizzatore Python", "algoritmo", "albero sintattico (ast): funzioni, complessità, import inutili"),
        Component("rilevatore di chiamate rischiose", "algoritmo", "eval/exec, os.system, shell=True, pickle, yaml.load"),
        Component("validatore JSON", "algoritmo", "parser JSON con posizione dell'errore"),
    )
    operations = (
        Operation("analyze_python", 1, "analizza codice Python", '{"text": "..."} oppure {"path": "file.py"}'),
        Operation("check_json", 1, "valida un testo JSON", '{"text": "..."} oppure {"path": "file.json"}'),
    )

    def __init__(self, read_file: Any = None) -> None:
        self._read = read_file

    def _source(self, payload: dict[str, Any]) -> str:
        if "path" in payload:
            if self._read is None:
                raise EngineOpError("lettura di file non disponibile")
            return self._read(payload["path"])
        return text_arg(payload)

    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any:
        source = self._source(payload)
        if op == "analyze_python":
            return analyze_python(source)
        if op == "check_json":
            return check_json(source)
        raise EngineOpError(f"operazione sconosciuta: {op}")
