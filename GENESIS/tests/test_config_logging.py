from __future__ import annotations

import json

import pytest

from genesis.core.config import default_home, load_config
from genesis.core.logs import close_handler, setup_logging
from genesis.errors import ConfigError
from genesis.security.redact import REDACTED, mask, redact

from .conftest import write_config


def test_defaults_without_file(home):
    cfg = load_config(home)
    assert cfg.profile == "auto" and cfg.log_level == "INFO" and cfg.backup_keep is None
    assert dict(cfg.grants) == {"owner": 5, "system": 3}
    assert cfg.db_path == home / "data" / "genesis.db"


def test_file_values_and_grants(home):
    write_config(home, '[general]\nprofile = "lite-4gb"\n[logging]\nlevel = "debug"\n'
                       '[backup]\nkeep = 3\n[permissions.grants]\nresearcher = 1\n')
    cfg = load_config(home)
    assert (cfg.profile, cfg.log_level, cfg.backup_keep) == ("lite-4gb", "DEBUG", 3)
    assert cfg.grants["researcher"] == 1 and cfg.grants["owner"] == 5


@pytest.mark.parametrize("text", [
    "not = [valid",
    "[nope]\nx = 1\n",
    "[general]\ntypo = 1\n",
    '[general]\nprofile = "turbo"\n',
    '[logging]\nlevel = "LOUD"\n',
    "[backup]\nkeep = 0\n",
    "[permissions.grants]\nagent = 9\n",
    "[permissions.grants]\nBad-Name = 1\n",
    "[permissions.grants]\nagent = true\n",
])
def test_invalid_config_is_rejected(home, text):
    write_config(home, text)
    with pytest.raises(ConfigError):
        load_config(home)


def test_grants_are_read_only(home):
    with pytest.raises(TypeError):
        load_config(home).grants["owner"] = 0  # type: ignore[index]


def test_genesis_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "x"))
    assert default_home() == tmp_path / "x"


@pytest.mark.parametrize("secret", [
    "sk-or-v1-" + "a" * 40,
    "AIza" + "B" * 35,
    "gsk_" + "c" * 30,
    "nvapi-" + "d" * 30,
    "Bearer abcdefghijklmnop123",
])
def test_redact_known_formats(secret):
    out = redact(f"calling with {secret} now")
    assert secret not in out and REDACTED in out


def test_redact_key_value_but_not_lookalikes():
    assert redact('api_key=supersecret123') == f"api_key={REDACTED}"
    assert redact('{"password": "hunter2hunter2"}') == f'{{"password": "{REDACTED}"}}'
    assert redact("max_tokens=256 tokens used") == "max_tokens=256 tokens used"
    assert mask("sk-or-v1-abcdefghijklmnop") == "sk-o…mnop" and mask("short") == "****"


def test_log_lines_are_json_and_redacted(tmp_path):
    logger, handler = setup_logging(tmp_path, "INFO", 100_000, 2)
    try:
        key = "sk-or-v1-" + "z" * 40
        logger.info("using key %s", key, extra={"fields": {"token": "abcdef123456"}})
        try:
            raise ValueError(f"bad {key}")
        except ValueError:
            logger.exception("boom")
    finally:
        close_handler(handler)
    lines = (tmp_path / "genesis.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "z" * 40 not in "".join(lines)
    first = json.loads(lines[0])
    assert first["level"] == "INFO" and REDACTED in first["msg"] and first["fields"]["token"] == REDACTED
    assert "exc" in json.loads(lines[1])
