from __future__ import annotations

from pathlib import Path

from src.config import Config, Secrets, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_config_merges_real_preferences_and_config_files():
    """Guards against schema drift between preferences.yaml/config.yaml and the
    Config accessors that read them."""
    cfg = load_config()

    assert cfg.candidate.get("home_base_code")
    assert cfg.search.get("titles")
    assert cfg.geo.get("welcome_regions")
    assert isinstance(cfg.geo.get("country_hints"), dict) and cfg.geo["country_hints"]
    assert cfg.salary.get("min_usd") is not None
    assert cfg.llm.get("provider")
    assert cfg.rollover.get("archive_new_after_days") is not None


def test_config_yaml_wins_on_key_collision_with_preferences(tmp_path):
    """Documents actual precedence: config.yaml is spread over preferences.yaml,
    so a section present in both is decided by config.yaml."""
    prefs_path = tmp_path / "preferences.yaml"
    prefs_path.write_text("notify:\n  ntfy_topic: from-prefs\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("notify:\n  ntfy_topic: from-config\n")

    cfg = load_config(config_path, prefs_path)

    assert cfg.section("notify")["ntfy_topic"] == "from-config"


def test_load_config_custom_paths_merge_distinct_sections(tmp_path):
    prefs_path = tmp_path / "preferences.yaml"
    prefs_path.write_text("search:\n  titles: [Engineer]\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  provider: deepseek\n")

    cfg = load_config(config_path, prefs_path)

    assert cfg.search.get("titles") == ["Engineer"]
    assert cfg.llm.get("provider") == "deepseek"


def test_ntfy_topic_env_overrides_config_yaml_value(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "from-env")
    cfg = Config(raw={"notify": {"ntfy_topic": "from-yaml"}}, secrets=Secrets.from_env())

    assert cfg.ntfy_topic == "from-env"


def test_ntfy_topic_falls_back_to_yaml_when_env_unset(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    cfg = Config(raw={"notify": {"ntfy_topic": "from-yaml"}}, secrets=Secrets.from_env())

    assert cfg.ntfy_topic == "from-yaml"


def test_missing_sections_default_to_empty_dict():
    cfg = Config(raw={})

    assert cfg.candidate == {}
    assert cfg.search == {}
    assert cfg.geo == {}
    assert cfg.ntfy_topic == ""


def test_secrets_from_env_reads_all_four(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-1")
    monkeypatch.setenv("NOTION_TOKEN", "ntn-1")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    monkeypatch.setenv("NTFY_TOPIC", "topic-1")

    secrets = Secrets.from_env()

    assert secrets.deepseek_api_key == "sk-1"
    assert secrets.notion_token == "ntn-1"
    assert secrets.notion_database_id == "db-1"
    assert secrets.ntfy_topic == "topic-1"
