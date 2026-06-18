"""icon-translations + entity-translations consistency (Gold).

Guards that every icon in icons.json is keyed by a real entity translation_key
(so a typo can't silently drop an icon), and that the per-metric Manage switch
relies on its translation_key rather than a hard-coded _attr_name.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.aeolus.const import MetricKind
from custom_components.aeolus.engine import AeolusEngine
from custom_components.aeolus.models import Space
from custom_components.aeolus.switch import AeolusMetricManageSwitch

_COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "aeolus"


def _load(name: str) -> dict:
    return json.loads((_COMPONENT / name).read_text(encoding="utf-8"))


def test_icons_json_keys_are_known_translation_keys() -> None:
    icons = _load("icons.json")["entity"]
    strings = _load("strings.json")["entity"]
    for platform, entities in icons.items():
        known = set(strings.get(platform, {}))
        for key, spec in entities.items():
            assert key in known, f"icons.json {platform}.{key} has no translation_key"
            assert "default" in spec and spec["default"].startswith("mdi:")


def test_no_entity_sets_attr_icon_in_code() -> None:
    # icon-translations: icons come from icons.json, never the entity object.
    modules = ("sensor.py", "number.py", "switch.py", "binary_sensor.py", "select.py")
    for module in modules:
        src = (_COMPONENT / module).read_text(encoding="utf-8")
        assert "_attr_icon" not in src, f"{module} still sets _attr_icon"


def test_manage_switch_uses_translation_not_name() -> None:
    space = Space(subentry_id="0123456789ABCDEFGHJKMNPQRS", name="Zone", co2_sensors=[])
    engine = AeolusEngine(hass=None, entry_id="e", spaces={}, actuators={})  # type: ignore[arg-type]
    sw = AeolusMetricManageSwitch(engine, space, 0, MetricKind.PM2_5)
    assert sw.translation_key == "manage_pm2_5"
    assert getattr(sw, "_attr_name", None) is None
