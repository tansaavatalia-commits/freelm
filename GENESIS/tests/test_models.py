from __future__ import annotations

import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from genesis.app import Genesis
from genesis.cli import main
from genesis.errors import ConfigError, GenesisError
from genesis.hardware.detect import GPU
from genesis.hardware.profiles import PROFILES
from genesis.intelligence.base import Request
from genesis.intelligence.local_model import LocalModelProvider, is_loopback
from genesis.models.catalog import BUILTIN, load_catalog
from genesis.models.feasibility import assess, best_option, estimate
from genesis.models.finetune import plan, plan_markdown

from .conftest import LITE_HW, write_config

BIG_HW = dataclasses.replace(LITE_HW, ram_total_mb=32768, gpus=(GPU("NVIDIA RTX", 12288),))


def test_catalog_entries_are_flagged_as_unverified():
    assert len(BUILTIN) >= 10 and all("NON VERIFICATO" in c.verification and c.source.startswith("https://") for c in BUILTIN)
    assert len({c.id for c in BUILTIN}) == len(BUILTIN)


def test_owner_catalog_additions(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "m.json").write_text(json.dumps({
        "id": "mio-modello", "family": "Test", "params_b": 0.8, "license": "MIT", "context": 4096,
        "source": "https://example.org"}), encoding="utf-8")
    assert load_catalog(tmp_path)["mio-modello"].verification == "aggiunto dal proprietario"
    (tmp_path / "models" / "bad.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(GenesisError):
        load_catalog(tmp_path)


def test_estimates_are_monotonic_and_documented():
    small, big = estimate(0.5), estimate(7.0)
    assert small["total_gb"] < big["total_gb"]
    assert estimate(7, "q8_0")["weights_gb"] > estimate(7, "q4_k_m")["weights_gb"]
    assert estimate(1, context=32768)["kv_cache_gb"] > estimate(1, context=2048)["kv_cache_gb"]
    with pytest.raises(ValueError):
        estimate(1, "q9")


def test_feasibility_on_the_owner_pc_and_on_a_bigger_one():
    lite = PROFILES["lite-4gb"]
    tiny = assess(0.36, LITE_HW, lite)
    seven = assess(7.6, LITE_HW, lite)
    assert tiny["verdict"] in ("eseguibile", "al limite") and seven["verdict"] == "non eseguibile"
    assert any("disattiva i modelli locali" in n for n in tiny["notes"])
    assert tiny["available_ram_gb"] == pytest.approx(4 - 2.5 - 0.15, abs=0.01)  # Windows reserve on a 4 GB PC
    on_gpu = best_option(7.6, BIG_HW, PROFILES["gpu"])
    assert on_gpu["verdict"] == "eseguibile" and on_gpu["where"] == "GPU" and on_gpu["quant"] == "q8_0"


def test_finetune_plans():
    q = plan(1.5, "qlora", 1000, 300, BIG_HW)
    full = plan(1.5, "full", 1000, 300, BIG_HW)
    assert q["estimate_gb"]["total"] < full["estimate_gb"]["total"] and q["feasible_here"]
    assert not plan(7.6, "qlora", 50, 300, LITE_HW)["feasible_here"]
    assert "200 esempi" in plan(7.6, "qlora", 50, 300, LITE_HW)["warnings"][0]
    md = plan_markdown(dataclasses.asdict(BUILTIN[1]), q)
    for step in ("Licenze", "Baseline", "Valutazione", "Promozione", "COST_POLICY"):
        assert step in md
    with pytest.raises(ValueError):
        plan(1, "magic", 1, 1, LITE_HW)


class _FakeLocalModel(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply = {"choices": [{"message": {"content": f"locale: {body['messages'][0]['content']}"}}]}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_model_server():
    srv = HTTPServer(("127.0.0.1", 0), _FakeLocalModel)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


def test_local_model_provider(fake_model_server):
    assert is_loopback("http://127.0.0.1:8080/v1") and is_loopback("http://localhost:11434/v1")
    assert not is_loopback("http://192.168.1.5:8080/v1") and not is_loopback("ftp://127.0.0.1")
    cfg = {"endpoint": fake_model_server, "model": "test"}
    assert "lite-4gb" in LocalModelProvider(cfg, profile_allows=False).status()[1]
    assert LocalModelProvider({"endpoint": "http://10.0.0.2/v1", "model": "x"}, True).status()[0] is False
    provider = LocalModelProvider(cfg, profile_allows=True)
    assert provider.run(Request("ciao"), "chat") == "locale: ciao"
    assert LocalModelProvider({**cfg, "allow_on_lite": True}, profile_allows=False).status()[0]


def test_router_uses_local_model_for_private_chat(home, fake_model_server):
    write_config(home, f'[models.local]\nendpoint = "{fake_model_server}"\nmodel = "test"\nallow_on_lite = true\n')
    g = Genesis(home, hardware=LITE_HW)
    try:
        result = g.router.route(Request("ciao", private=True))
        assert result["engine"] == "local-model" and result["output"] == "locale: ciao" and result["verified"] is False
        assert g.router.route(Request("2+2", private=True))["engine"] == "local"  # exact engine still first
    finally:
        g.close()


@pytest.mark.parametrize("bad", ['[models.local]\nmodel = "x"\n', '[models.local]\nendpoint = "http://127.0.0.1"\nmodel = "x"\ntimeout = 1\n',
                                 '[models.local]\nendpoint = "http://127.0.0.1"\nmodel = "x"\nextra = 1\n'])
def test_local_model_config_validation(home, bad):
    write_config(home, bad)
    with pytest.raises(ConfigError):
        Genesis(home, hardware=LITE_HW)


def test_models_cli(app, capsys):
    home = str(app.config.home)
    assert main(["--home", home, "models", "list"]) == 0
    assert "NON verificati" in capsys.readouterr().out
    assert main(["--home", home, "models", "check", "qwen2.5-0.5b-instruct", "--quant", "q4_k_m"]) == 0
    assert '"verdict"' in capsys.readouterr().out
    assert main(["--home", home, "models", "plan", "qwen2.5-1.5b-instruct", "--method", "qlora"]) == 0
    assert "Piano scritto" in capsys.readouterr().out
    assert list(app.config.reports_dir.glob("piano-*.md"))
    assert main(["--home", home, "models", "check", "inesistente"]) == 1
