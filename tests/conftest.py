"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def store_open_today(monkeypatch):
    """Pin "today" to a Wednesday morning (store open), so tests don't depend on the
    real clock (e.g. the closed-store notice). Tests that need another date set
    EMPORIO_TODAY themselves or pass `now`/`today` explicitly."""
    monkeypatch.setenv("EMPORIO_TODAY", "2026-03-18T10:00")
