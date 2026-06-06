"""Pytest fixtures for the Aeolus custom integration."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading the `aeolus` custom integration in every test."""
    yield
