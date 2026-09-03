from pathlib import Path

from angrist.config import Config, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("ANGRIST_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_BASE_URL", raising=False)
    cfg = load_config(dotenv_path=Path("nonexistent.env"))
    assert isinstance(cfg, Config)
    assert cfg.model == "gpt-oss"
    assert cfg.base_url == "https://api.groq.com/openai/v1"
    assert cfg.api_key == ""


def test_load_config_env_vars(monkeypatch):
    monkeypatch.setenv("ANGRIST_LLM_MODEL", "qwen2.5-coder")
    monkeypatch.setenv("ANGRIST_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ANGRIST_LLM_API_KEY", "secret-key")
    cfg = load_config(dotenv_path=Path("nonexistent.env"))
    assert cfg.model == "qwen2.5-coder"
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.api_key == "secret-key"


def test_load_config_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("ANGRIST_LLM_MODEL", "env-model")
    monkeypatch.setenv("ANGRIST_LLM_BASE_URL", "http://env-url/v1")
    monkeypatch.setenv("ANGRIST_LLM_API_KEY", "env-key")
    cfg = load_config(
        model="cli-model",
        base_url="http://cli-url/v1",
        api_key="cli-key",
        dotenv_path=Path("nonexistent.env"),
    )
    assert cfg.model == "cli-model"
    assert cfg.base_url == "http://cli-url/v1"
    assert cfg.api_key == "cli-key"


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("ANGRIST_LLM_MODEL=dotenv-model\nANGRIST_LLM_API_KEY=dotenv-key\n")
    monkeypatch.delenv("ANGRIST_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_API_KEY", raising=False)
    cfg = load_config(dotenv_path=dotenv_file)
    assert cfg.model == "dotenv-model"
    assert cfg.api_key == "dotenv-key"


def test_cli_fix_help_shows_config_options():
    import re

    from typer.testing import CliRunner

    from angrist.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["fix", "--help"])
    assert result.exit_code == 0

    clean_stdout = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.stdout)
    assert "--model" in clean_stdout
    assert "--api-key" in clean_stdout
    assert "--base-url" in clean_stdout

