"""Testes da expansao de ${VAR} no loader de config."""

from vera.config import _expand_env_vars


def test_expands_simple_string(monkeypatch):
    monkeypatch.setenv("MY_DB", "abc123")
    assert _expand_env_vars("${MY_DB}") == "abc123"


def test_expands_in_dict(monkeypatch):
    monkeypatch.setenv("TOKEN", "xyz")
    out = _expand_env_vars({"key": "${TOKEN}", "nested": {"db": "${TOKEN}"}})
    assert out == {"key": "xyz", "nested": {"db": "xyz"}}


def test_expands_in_list(monkeypatch):
    monkeypatch.setenv("A", "a1")
    assert _expand_env_vars(["${A}", "plain"]) == ["a1", "plain"]


def test_missing_var_becomes_empty(monkeypatch):
    monkeypatch.delenv("NOT_SET", raising=False)
    assert _expand_env_vars("${NOT_SET}") == ""


def test_non_string_values_pass_through():
    assert _expand_env_vars(True) is True
    assert _expand_env_vars(42) == 42
    assert _expand_env_vars(None) is None


def test_literal_dollar_not_expanded():
    assert _expand_env_vars("$MY_DB no braces") == "$MY_DB no braces"


def test_load_config_expands(monkeypatch, tmp_path):
    from vera.config import load_config

    monkeypatch.setenv("NOTION_DB_ACOES", "db-abc")
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        "domains:\n"
        "  tasks:\n"
        "    enabled: true\n"
        "    collection: \"${NOTION_DB_ACOES}\"\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.domains["tasks"].collection == "db-abc"
