"""Every subentry form field has a label (otherwise the UI shows the raw key)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.aeolus.config_flow import _actuator_schema, _space_schema

_STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/aeolus/strings.json").read_text()
)


def _fields(schema) -> set[str]:
    return {str(key.schema) for key in schema.schema}


@pytest.mark.parametrize("step", ["user", "reconfigure"])
@pytest.mark.parametrize(
    ("subentry", "schema"),
    [
        ("actuator", _actuator_schema([])),
        ("space", _space_schema()),
    ],
)
def test_every_subentry_field_has_a_label(subentry, schema, step) -> None:
    labels = _STRINGS["config_subentries"][subentry]["step"][step]["data"]
    assert _fields(schema) - labels.keys() == set()
