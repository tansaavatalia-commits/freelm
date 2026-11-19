"""Reparto qualità: fonti e verifica dei fatti su Wikipedia (gratuita, senza chiave).

- `research_notes`: prima di scrivere, scarica il testo delle voci pertinenti; lo sceneggiatore può usare SOLO quei fatti
  (i modelli deboli, se gli chiedi un colpo di scena, altrimenti lo inventano);
- `gather_sources`: dopo, verifica affermazione per affermazione.
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List

import httpx


class SourcesUnavailable(RuntimeError):
    """Wikipedia non raggiungibile (limiti di richieste): si rimanda, non si scrive senza fonti."""


_SEM: "asyncio.Semaphore | None" = None
_CACHE: Dict[str, Any] = {}


async def _get(http: httpx.AsyncClient, url: str, params: Any = None) -> httpx.Response:
    """GET verso Wikipedia: max 2 richieste in contemporanea, rispetto di 429/Retry-After, cache in memoria."""
    global _SEM
    key = url + repr(sorted((params or {}).items()))
    if key in _CACHE:
        return _CACHE[key]
    _SEM = _SEM or asyncio.Semaphore(2)
    delays = [5, 15, 30, 60]
    async with _SEM:
        for i in range(len(delays) + 1):
            r = await http.get(url, params=params, headers=UA)
            if r.status_code != 429 and r.status_code < 500:
                if r.status_code == 200:
                    _CACHE[key] = r
                await asyncio.sleep(0.3)
                return r
            if i == len(delays):
                raise SourcesUnavailable(f"Wikipedia non disponibile ({r.status_code})")
            wait = r.headers.get("retry-after", "")
            await asyncio.sleep(min(float(wait), 120) if wait.replace(".", "").isdigit() else delays[i])
    raise SourcesUnavailable("unreachable")


UA = {"User-Agent": "yt-factory/0.2 (fact-checking bot; https://github.com/shihabshahrier/freelm)"}


def clean_wikitext(src: str) -> str:
    """Wikitext -> testo leggibile (abbastanza per un LLM): via template, note, tabelle, link ridotti al testo."""
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", src, flags=re.S)
    for _ in range(4):  # template annidati
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)
    t = re.sub(r"\[\[(?:File|Image|Category|Immagine|Categoria|File):[^\]]*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"<[^>]+>|'{2,}", "", t)
    t = re.sub(r"^=+\s*(.*?)\s*=+$", r"\n\1:", t, flags=re.M)
    t = re.split(r"\n(?:See also|References|Notes|External links|Bibliography|Voci correlate|Note|Collegamenti esterni|Bibliografia):", t)[0]
    return re.sub(r"\n{3,}", "\n\n", t).strip()


async def page_text(http: httpx.AsyncClient, key: str, lang: str, limit: int) -> str:
    r = await _get(http, f"https://{lang}.wikipedia.org/w/rest.php/v1/page/{key}")
    if r.status_code != 200:
        return ""
    return clean_wikitext(r.json().get("source", ""))[:limit]


async def research_notes(http: httpx.AsyncClient, query: str, lang: str = "en", pages: int = 2,
                         limit: int = 3500) -> str:
    """Testo delle voci Wikipedia più pertinenti, nella lingua del canale con ripiego sull'inglese."""
    if os.environ.get("YTF_OFFLINE"):
        return ""
    failures = 0
    for lg in dict.fromkeys([lang, "en"]):
        try:
            r = await _get(http, f"https://{lg}.wikipedia.org/w/rest.php/v1/search/page",
                           {"q": _short_query(query), "limit": pages})
            r.raise_for_status()
            found = r.json().get("pages", [])
            texts = await asyncio.gather(*(page_text(http, p["key"], lg, limit) for p in found))
        except SourcesUnavailable:
            failures += 1
            continue
        except (httpx.HTTPError, ValueError, KeyError):
            continue
        notes = "\n\n".join(f"### {p['title']} (Wikipedia {lg})\n{t}" for p, t in zip(found, texts) if len(t) > 200)
        if notes:
            return notes
    if failures:
        raise SourcesUnavailable("Wikipedia non raggiungibile: riprovo al prossimo giro")
    return ""


def _short_query(q: str) -> str:
    """La ricerca di Wikipedia rende meglio con poche parole chiave che con una frase intera."""
    words = [w for w in re.findall(r"[\w'-]+", q) if w.lower() not in _STOP]
    return " ".join(words[:7])


_STOP = set("the a an of in on at to for and or with from by its it is was were that this which who whose how why "
            "what il lo la i gli le un una di da del della dei delle nel nella che e o per con su".split())


async def lookup(http: httpx.AsyncClient, query: str, lang: str = "en") -> str:
    """Estratto delle 2 pagine Wikipedia più pertinenti."""
    r = await _get(http, f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page", {"q": _short_query(query), "limit": 2})
    r.raise_for_status()
    texts = []
    for page in r.json().get("pages", []):
        body = await page_text(http, page["key"], lang, 1500)
        texts.append(f"[{page['title']}] " + (body or re.sub(r"<[^>]+>", "", page.get("excerpt", ""))))
    return "\n".join(texts)


async def gather_sources(http: httpx.AsyncClient, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if os.environ.get("YTF_OFFLINE"):
        return []

    async def one(c: Dict[str, Any]) -> Dict[str, Any]:
        try:
            src = await lookup(http, str(c.get("query") or c.get("claim", ""))[:120])
        except (httpx.HTTPError, ValueError, KeyError, SourcesUnavailable):
            src = ""
        return {"claim": c.get("claim", ""), "sources": src or "(no source found)"}

    return list(await asyncio.gather(*(one(c) for c in claims[:6])))


# --------------------------------------------------------------------------- controlli deterministici anti-invenzione
def _norm(t: str) -> str:
    t = t.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", re.sub(r"[^\w%' ]+", " ", t)).strip()


def quote_in_notes(quote: str, notes: str, window: int = 5) -> bool:
    """La citazione esiste davvero nelle fonti? Almeno metà delle sue finestre di 5 parole devono comparire alla lettera
    (tollera piccole parafrasi, non frasi inventate)."""
    q, n = _norm(quote).split(), _norm(notes)
    if len(q) < window:
        return bool(q) and " ".join(q) in n
    wins = [" ".join(q[i:i + window]) for i in range(len(q) - window + 1)]
    return sum(w in n for w in wins) / len(wins) >= 0.5


_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(%|percent|per cento)?", re.I)


def _canon(num: str) -> List[str]:
    """Forme equivalenti di un numero: 1,000 / 1.000 / 1000 ; 73,7 / 73.7."""
    raw = num.strip()
    out = {raw, raw.replace(" ", "")}
    if re.fullmatch(r"\d{1,3}(?:[.,\s]\d{3})+", raw):
        out.add(re.sub(r"[.,\s]", "", raw))
    if re.fullmatch(r"\d+[.,]\d+", raw):
        out |= {raw.replace(",", "."), raw.replace(".", ",")}
    return list(out)


def numbers_not_in_notes(spoken: str, notes: str) -> List[str]:
    """Numeri detti nel video che non compaiono nelle fonti (i modelli inventano soprattutto cifre e date).
    Si ignorano i numeri piccoli usati come espressioni ("3 secondi", "2 cose"), salvo le percentuali."""
    plain = notes + "\n" + re.sub(r"(?<=\d)[ ,.\u00a0](?=\d{3}\b)", "", notes)  # 1,234,567 -> anche 1234567
    missing = []
    for m in _NUM.finditer(spoken):
        num, pct = m.group(1), m.group(2)
        try:
            value = float(re.sub(r"[.,\s](?=\d{3}\b)", "", num).replace(",", "."))
        except ValueError:
            continue
        if (value <= 10 and not pct) or (pct and value in (0, 100)):  # "0% interessi", "100%" sono modi di dire
            continue
        if not any(re.search(rf"(?<![\d]){re.escape(c)}(?![\d])", plain) for c in _canon(num)):
            missing.append(num + ("%" if pct else ""))
    return list(dict.fromkeys(missing))


def source_titles(notes: str) -> List[str]:
    return re.findall(r"^### (.+)$", notes, flags=re.M)


def notes_on_topic(notes: str, query: str) -> bool:
    """Le fonti parlano davvero dell'argomento? Almeno una parola significativa della ricerca nei titoli delle voci
    (una ricerca su un'idea inventata restituisce comunque *qualche* voce: va riconosciuta e scartata)."""
    titles = " ".join(source_titles(notes)).lower()
    words = [w for w in _norm(query).split() if len(w) > 3 and w not in _STOP]
    if not words:
        return True
    hits = sum(1 for w in words if w in titles or w.rstrip("s") in titles)
    # metà delle parole chiave: "calcio stanca il corpo" -> "Mondiali 1970, Lucio Dalla" non basta più
    return hits >= max(1, (len(words) + 1) // 2)
