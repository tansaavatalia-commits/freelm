"""Il "cervello" condiviso da tutti gli agenti: freelm (LLM gratuiti con failover) + output JSON robusto."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional

from freelm import AsyncFreeLLM


def extract_json(text: str) -> Any:
    """Estrae il primo oggetto/array JSON da una risposta (anche dentro ```json ... ```)."""
    if not text:
        raise ValueError("risposta vuota")
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("nessun JSON nella risposta")
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("JSON troncato")


class Brain:
    """Un solo client freelm per tutto il sistema (sicuro su un unico event loop)."""

    def __init__(self, model: str = "chat", concurrency: int = 4, log: Optional[Any] = None):
        self.model = model
        self.llm = AsyncFreeLLM.from_env(keyless="auto")
        self.sem = asyncio.Semaphore(concurrency)  # non saturare i tier gratuiti
        self.log = log or (lambda *a: None)
        self.calls = 0

    async def ask(self, system: str, user: str, *, max_tokens: int = 6000, temperature: float = 0.8,
                  model: Optional[str] = None) -> str:
        """I modelli gratuiti "reasoning" spendono token a pensare: se la risposta esce vuota o troncata,
        si riprova con un budget doppio."""
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        budget = max_tokens
        async with self.sem:
            for attempt in range(3):
                self.calls += 1
                r = await self.llm.chat(msgs, model=model or self.model, max_tokens=budget, temperature=temperature)
                choice = r.choices[0]
                out = (choice.message.content or "").strip()
                if out and choice.finish_reason != "length":
                    return out
                self.log(f"risposta {'troncata' if out else 'vuota'} ({r.model}), riprovo con piu' token")
                budget = min(budget * 2, 16000)
        if out:
            return out
        raise RuntimeError("nessuna risposta dai provider gratuiti")

    async def ask_json(self, system: str, user: str, *, schema: str, max_tokens: int = 6000,
                       model: Optional[str] = None, temperature: float = 0.8) -> Dict[str, Any]:
        """Chiede JSON; se non è valido, rimanda l'errore al modello e riprova."""
        sys_prompt = f"{system}\n\nAnswer ONLY with valid JSON (no text outside the JSON) shaped like this:\n{schema}"
        prompt, last_err = user, None
        for _ in range(3):
            raw = await self.ask(sys_prompt, prompt, max_tokens=max_tokens, model=model, temperature=temperature)
            try:
                data = extract_json(raw)
                if isinstance(data, dict):
                    return data
                return {"items": data}
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
                prompt = f"{user}\n\nYour previous answer was not valid JSON ({e}). Reply with the JSON only, shorter."
        raise RuntimeError(f"JSON non valido dopo 3 tentativi: {last_err}")

    async def aclose(self) -> None:
        await self.llm.aclose()
