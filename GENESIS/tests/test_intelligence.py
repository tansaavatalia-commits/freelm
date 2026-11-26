from __future__ import annotations

import sys
import types

import pytest

from genesis.app import Genesis
from genesis.cli import main
from genesis.core.config import load_config
from genesis.errors import ConfigError
from genesis.intelligence.base import EngineError, Provider, ProviderSpec, Request
from genesis.intelligence.local import LocalEngine, classify, evaluate, extract_expression
from genesis.intelligence.online import FreelmProvider
from genesis.intelligence.router import Router, RouterError
from genesis.memory.db import Database
from genesis.security.audit import AuditLog

from .conftest import LITE_HW, write_config


class Fake(Provider):
    def __init__(self, pid, *, kind="remote", cost="free", quality=3, fail=False, caps=("chat",)):
        self.spec = ProviderSpec(pid, pid, "1", kind, frozenset(caps), cost, quality, "modello esterno")
        self.fail, self.calls = fail, 0

    def run(self, request, task_type):
        self.calls += 1
        if self.fail:
            raise EngineError(f"{self.spec.id} down")
        return f"risposta da {self.spec.id}"


@pytest.mark.parametrize("text,value", [("2+3*4", 14), ("quanto fa (1+2)/4?", 0.75), ("sqrt(16) + 2^3", 12),
                                        ("calcola 6 x 7", 42), ("-2**2", -4)])
def test_math_evaluator(text, value):
    assert evaluate(extract_expression(text)) == value


@pytest.mark.parametrize("bad", ["__import__('os').system('x')", "(1).__class__", "a+1", "2**10000", "1/0",
                                 "9" * 201, "sqrt(-1)", "open('f')", "lambda: 1"])
def test_math_evaluator_rejects_unsafe_or_invalid(bad):
    with pytest.raises(EngineError):
        evaluate(bad)


@pytest.mark.parametrize("prompt,kind", [("12*(3+4)", "math"), ("conta le parole: uno due tre", "text.stats"),
                                         ("correggi questo codice python", "code"),
                                         ("perché il cielo è blu?", "reasoning"), ("ciao, come stai?", "chat")])
def test_classifier(prompt, kind):
    assert classify(prompt) == kind


def test_local_engine_answers():
    local = LocalEngine()
    assert local.run(Request("12*(3+4)"), "math") == "84"
    assert local.run(Request("conta le parole: Ciao mondo. Tutto bene?"), "text.stats").startswith("parole: 4")
    assert "cifre" in local.run(Request("999**999"), "math")


def test_zero_external_providers():
    router = Router([LocalEngine(), FreelmProvider()])  # defaults: remote disabled
    result = router.route(Request("2+2"))
    assert result["output"] == "4" and result["engine"] == "local" and result["verified"] is True
    with pytest.raises(RouterError, match="motori online disattivati"):
        router.route(Request("scrivi una poesia"))


def test_paid_and_unverified_engines_are_never_used():
    paid = Fake("paid", cost="paid", quality=5)
    free = Fake("free")
    Router([paid, free], remote_enabled=True, remote_free_verified=True).route(Request("ciao"))
    assert paid.calls == 0 and free.calls == 1
    with pytest.raises(RouterError, match="a pagamento"):
        Router([paid], remote_enabled=True, remote_free_verified=True).route(Request("ciao"))
    with pytest.raises(RouterError, match="gratuità non confermata"):
        Router([free], remote_enabled=True).route(Request("ciao"))


def test_private_requests_stay_local():
    remote = Fake("remote", caps=("chat", "math"))
    router = Router([LocalEngine(), remote], remote_enabled=True, remote_free_verified=True)
    assert router.route(Request("2*21", private=True))["engine"] == "local"
    with pytest.raises(RouterError, match="privata"):
        router.route(Request("ciao", private=True))
    assert remote.calls == 0


def test_fallback_and_audit_of_remote_calls(tmp_path):
    db = Database(tmp_path / "g.db")
    db.migrate()
    audit = AuditLog(db)
    broken, good = Fake("a", quality=4, fail=True), Fake("b", quality=3)
    result = Router([broken, good], remote_enabled=True, remote_free_verified=True, audit=audit).route(Request("ciao"))
    assert result["engine"] == "b" and [a["ok"] for a in result["attempts"]] == [False, True]
    assert result["verified"] is False
    rows = audit.tail(5)
    assert [r["outcome"] for r in rows] == ["failed", "ok"] and "ciao" not in rows[0]["details"]  # prompt not logged
    db.close()


def test_freelm_adapter_with_fake_library(monkeypatch):
    fake = types.ModuleType("freelm")
    fake.__version__ = "9.9"
    fake.providers_from_env = lambda keyless=None: (
        [types.SimpleNamespace(name="openrouter", free_only=True), types.SimpleNamespace(name="groq", free_only=False)]
        if keyless is False else pytest.fail("keyless must be off"))

    class Client:
        def text(self, prompt):
            if "boom" in prompt:
                raise RuntimeError("bad key sk-or-v1-" + "k" * 40)
            return "  ciao!  "

    used = []
    fake.FreeLLM = lambda providers: used.append([p.name for p in providers]) or Client()
    monkeypatch.setitem(sys.modules, "freelm", fake)
    provider = FreelmProvider()
    assert provider.status() == (True, "OpenRouter pronto (solo modelli gratuiti)") and provider.spec.version == "9.9"
    assert provider.run(Request("ciao"), "chat") == "ciao!" and used == [["openrouter"]]  # groq never used
    with pytest.raises(EngineError) as info:
        provider.run(Request("boom"), "chat")
    assert "k" * 40 not in str(info.value)


def test_keyless_services_only_when_the_owner_allows_them(monkeypatch):
    fake = types.ModuleType("freelm")
    seen = []

    def from_env(keyless=None):
        seen.append(keyless)
        return [types.SimpleNamespace(name="kilo", free_only=True, keyless=True),
                types.SimpleNamespace(name="ovh", free_only=False, keyless=True),
                types.SimpleNamespace(name="groq", free_only=False, keyless=False)] if keyless else []

    fake.providers_from_env = from_env
    monkeypatch.setitem(sys.modules, "freelm", fake)
    assert FreelmProvider().status()[0] is False and seen[-1] is False  # default: never keyless
    ok, reason = FreelmProvider(keyless=True).status()
    assert ok and seen[-1] is True and reason == "pronto (solo modelli gratuiti): kilo, ovh"  # groq is not keyless
    assert "Kilo" in FreelmProvider(keyless=True).spec.name


def test_online_enable_keyless_command(home):
    write_config(home, "")
    assert main(["--home", str(home), "online", "enable", "--keyless", "--confirm"]) == 0
    assert load_config(home).keyless_allowed is True
    assert main(["--home", str(home), "online", "enable", "--confirm"]) == 0  # keeps the earlier choice
    assert load_config(home).keyless_allowed is True
    assert main(["--home", str(home), "online", "disable", "--confirm"]) == 0  # off means off
    cfg = load_config(home)
    assert not cfg.keyless_allowed and not cfg.remote_enabled
    write_config(home, '[intelligence]\nkeyless_allowed = "si"\n')
    with pytest.raises(ConfigError):
        load_config(home)


def test_freelm_missing_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "freelm", None)  # import fails
    assert FreelmProvider().status() == (False, "libreria freelm non installata")


def test_task_cli_and_config(home, capsys):
    g = Genesis(home, hardware=LITE_HW)
    try:
        g.tasks.submit("intelligence.ask", {"prompt": "quanto fa 7*6?"})
        done = g.tasks.run_next()
        assert done["status"] == "succeeded" and done["result"]["output"] == "42"
        g.tasks.submit("intelligence.ask", {"prompt": 5})
        assert g.tasks.run_next()["status"] == "failed"
    finally:
        g.close()
    assert main(["--home", str(home), "ask", "10/4"]) == 0
    assert "2.5" in capsys.readouterr().out
    assert main(["--home", str(home), "ask", "ciao"]) == 1
    assert main(["--home", str(home), "providers"]) == 0
    write_config(home, "[intelligence]\nremote_enabled = 'yes'\n")
    with pytest.raises(ConfigError):
        Genesis(home, hardware=LITE_HW)


def test_online_enable_command(home, capsys):
    assert main(["--home", str(home), "online", "enable"]) == 2  # needs --confirm
    write_config(home, '[general]\nprofile = "auto"\n')
    assert main(["--home", str(home), "online", "enable", "--confirm"]) == 0
    g = Genesis(home, hardware=LITE_HW)
    try:
        assert g.config.remote_enabled and g.config.remote_free_verified and g.config.profile == "auto"
        assert any(r["action"] == "intelligence.online_enable" for r in g.audit.tail(10))
    finally:
        g.close()
    assert main(["--home", str(home), "online", "disable", "--confirm"]) == 0
    text = (home / "genesis.toml").read_text(encoding="utf-8")
    assert text.count("[intelligence]") == 1 and "remote_enabled = false" in text


def test_real_freelm_library_restricted_to_openrouter(monkeypatch):
    pytest.importorskip("freelm")  # installed in CI from this repository
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "FREELM_KEYLESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 40)
    assert FreelmProvider().status()[0] is False  # a Groq key alone is not enough
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "y" * 40)
    assert FreelmProvider().status() == (True, "OpenRouter pronto (solo modelli gratuiti)")
