"""Tests for settings loading (environment overrides the .env file)."""

import pytest

from emporio.config import DEFAULT_MODEL, ConfigError, load_settings


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "")
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "")
    return monkeypatch


def test_defaults(env):
    settings = load_settings()
    assert settings.gemini_model == DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert settings.gemini_thinking_level == "low"


def test_model_and_thinking_level_are_configurable(env):
    env.setenv("GEMINI_MODEL", "gemini-other")
    env.setenv("GEMINI_THINKING_LEVEL", "HIGH")
    settings = load_settings()
    assert settings.gemini_model == "gemini-other"
    assert settings.gemini_thinking_level == "high"


def test_invalid_thinking_level_raises(env):
    env.setenv("GEMINI_THINKING_LEVEL", "turbo")
    with pytest.raises(ConfigError):
        load_settings()


def test_missing_api_key_raises(env):
    env.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        load_settings()
