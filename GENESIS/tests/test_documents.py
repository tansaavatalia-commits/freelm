from __future__ import annotations

import io
import json

import pytest

from genesis.documents import DocumentError
from genesis.tools import web, wiki

from .test_api import call, server  # noqa: F401 - pytest fixture
from .test_chat import _online

RICETTA = "Ricetta della nonna\nIngredienti: farina, uova, zucchero.\nCuocere il ciambellone a 180 gradi per 40 minuti.\n"


def test_documents_save_list_remove(app):
    app.documents.save("ricetta.txt", RICETTA)
    assert [d["name"] for d in app.documents.list()] == ["ricetta.txt"]
    with pytest.raises(Exception, match="esiste già"):
        app.documents.save("ricetta.txt", "altro")
    app.documents.save("ricetta.txt", RICETTA + "Servire freddo.\n", overwrite=True)
    for bad in ("../fuori.txt", "a/b.txt", ".nascosto.txt", "foto.jpg", "contratto.pdf", ""):
        with pytest.raises(DocumentError):
            app.documents.save(bad, "x")
    with pytest.raises(DocumentError, match="troppo grande"):
        app.documents.save("enorme.txt", "x" * 1_000_001)
    moved = app.documents.remove("ricetta.txt")
    assert app.documents.list() == [] and moved["moved_to"].startswith(".cestino/")
    assert (app.config.workspace_dir / moved["moved_to"]).is_file()  # never a permanent deletion
    with pytest.raises(DocumentError, match="inesistente"):
        app.documents.remove("ricetta.txt")
    assert any(r["action"] == "documents.remove" for r in app.audit.tail(5))


def test_passages_find_the_relevant_lines_and_skip_the_trash(app):
    app.documents.save("ricetta.txt", RICETTA)
    app.documents.save("note.md", "# Note\nIl gatto dorme.\n")
    found = app.tools.index.passages("a quanti gradi cuocere il ciambellone?")
    assert found[0]["file"] == "documenti/ricetta.txt" and "180 gradi" in found[0]["text"]
    app.documents.remove("ricetta.txt")
    assert all(not p["file"].startswith(".cestino/") for p in app.tools.index.passages("ciambellone gradi"))


def test_chat_with_documents_cites_sources(app):
    fake = _online(app)
    app.documents.save("ricetta.txt", RICETTA)
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "a quanti gradi cuocio il ciambellone?", docs=True)
    system = plan["messages"][0]["content"]
    assert plan["mode"] == "stream" and "[1] documenti/ricetta.txt" in system and "<<<DATI NON FIDATI>>>" in system
    text = "".join(fake.stream(plan["messages"]))
    msg = app.chat.finish(cid, fake, text, ok=True, ms=1, chars=1, task_type="chat", sources=plan["sources"],
                          notes=plan["notes"])
    assert "**Fonti**\n1. documenti/ricetta.txt (riga 3)" in msg["content"]


def test_documents_without_engine_shows_passages(app):
    app.documents.save("ricetta.txt", RICETTA)
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "ciambellone gradi", docs=True)
    assert plan["mode"] == "done" and "180 gradi" in plan["message"]["content"]
    assert plan["message"]["engine"] == "text.find"


def test_private_conversation_never_searches_the_web(app):
    _online(app)
    cid = app.chat.create(private=True)["id"]
    plan = app.chat.prepare(cid, "chi era Galileo?", web=True)
    assert plan["mode"] == "done"  # private: no remote engine, no web


class _Resp(io.BytesIO):
    status = 200
    headers = type("H", (), {"get": lambda self, k, d="": "application/json",
                             "get_content_charset": lambda self: "utf-8"})()

    def geturl(self):
        return "https://it.wikipedia.org/w/api.php"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


def test_wikipedia_search_with_fake_network(monkeypatch):
    monkeypatch.setattr(web, "check_url", lambda url: None)
    answers = [
        {"query": {"search": [{"title": "Galileo Galilei"}, {"title": "Pisa"}]}},
        {"query": {"pages": {"1": {"title": "Galileo Galilei", "extract": "Galileo Galilei fu un fisico <b>italiano</b>."},
                             "2": {"title": "Pisa", "extract": ""}}}},
    ]
    urls = []

    class Opener:
        def open(self, req, timeout):
            urls.append(req.full_url)
            return _Resp(json.dumps(answers.pop(0)).encode())

    out = wiki.search("chi era Galileo", opener=Opener())
    assert out == [{"title": "Galileo Galilei", "url": "https://it.wikipedia.org/wiki/Galileo_Galilei",
                    "text": "Galileo Galilei fu un fisico <b>italiano</b>."}]  # empty extracts are dropped
    assert all(u.startswith("https://it.wikipedia.org/w/api.php?") for u in urls) and "srsearch=Galileo&" in urls[0]


def test_search_keywords_drop_instruction_words():
    assert wiki.keywords("Chi era Galileo Galilei? Rispondi in due frasi.") == "Galileo Galilei"
    assert wiki.keywords("spiegami cos'è la fotosintesi clorofilliana") == "fotosintesi clorofilliana"
    assert wiki.keywords("chi è?") == "chi è?"  # nothing left: the original words are searched


def test_footer_lists_only_cited_sources():
    from genesis.chat import sources_footer
    srcs = [{"label": "A", "url": "u1"}, {"label": "B", "url": None}, {"label": "C", "url": "u3"}]
    assert sources_footer(srcs, "vero [3]") == "\n\n**Fonti**\n3. C — u3\n_Altre fonti lette ma non citate: 2._"
    assert sources_footer(srcs, "nessuna citazione") == "\n\n**Fonti**\n1. A — u1\n2. B\n3. C — u3"  # all listed


def test_api_documents_and_web_sources(server, monkeypatch):  # noqa: F811 - pytest fixture
    status, saved, _ = call(server, "POST", "/api/documents", {"name": "ricetta.txt", "content": RICETTA})
    assert status == 201 and saved["name"] == "ricetta.txt"
    assert call(server, "GET", "/api/documents")[1][0]["name"] == "ricetta.txt"
    assert call(server, "POST", "/api/documents", {"name": "x.exe", "content": "MZ"})[0] == 400

    _, conv, _ = call(server, "POST", "/api/chat", {})
    assert call(server, "POST", f"/api/chat/{conv['id']}/send", {"text": "Galileo?", "web": True})[0] == 400  # web off

    server.core.run(lambda g: _online(g))
    server.core.run(lambda g: setattr(g, "config", type(g.config)(**{**g.config.__dict__, "internet_enabled": True})))
    monkeypatch.setattr(wiki, "search", lambda q: [{"title": "Galileo Galilei", "url": "https://it.wikipedia.org/wiki/G",
                                                     "text": "Fisico italiano."}])
    events = _events_with(server, conv["id"], {"text": "chi era Galileo e come cuocio il ciambellone?",
                                                "web": True, "docs": True})
    types = [e["type"] for e in events]
    assert types[:3] == ["user", "status", "start"] and types[-1] == "done"
    labels = [s["label"] for s in events[2]["sources"]]
    assert labels == ["documenti/ricetta.txt (riga 3)", "Wikipedia: Galileo Galilei"]
    final = events[-1]["message"]["content"]
    assert "**Fonti**" in final and "2. Wikipedia: Galileo Galilei — https://it.wikipedia.org/wiki/G" in final
    assert call(server, "POST", "/api/documents/remove", {"name": "ricetta.txt"})[1]["moved_to"].startswith(".cestino/")


def _events_with(srv, cid, body):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request("POST", f"/api/chat/{cid}/send", body=json.dumps(body).encode(),
                 headers={"Host": f"127.0.0.1:{srv.port}", "X-Genesis-Token": srv.token,
                          "Content-Type": "application/json"})
    raw = conn.getresponse().read().decode("utf-8")
    conn.close()
    return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]


def test_internet_command(home):
    from genesis.cli import main
    from genesis.core.config import load_config
    assert main(["--home", str(home), "internet", "enable"]) == 2  # needs --confirm
    assert main(["--home", str(home), "internet", "enable", "--confirm"]) == 0
    assert load_config(home).internet_enabled is True
    assert main(["--home", str(home), "internet", "disable", "--confirm"]) == 0
    assert load_config(home).internet_enabled is False
