"""Tests for the school alert entity."""

from __future__ import annotations

from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.core import State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.time_for_school.const import (
    STATE_ALERTING,
    STATE_ARMED,
    STATE_DISARMED,
)

from .conftest import (
    ENTITY_ID,
    LIGHT_OFF,
    LIGHT_ON,
    SPEAKER,
    START,
    TV,
    advance,
    attr,
    call,
    jump_to,
    settle,
    setup_entry,
    state,
)

pytestmark = pytest.mark.usefixtures("calls", "events")


@pytest.fixture(autouse=True)
def _freeze(freezer):
    freezer.move_to(START)


def local_next(hass) -> str:
    return dt_util.as_local(dt_util.parse_datetime(attr(hass, "next_fire"))).strftime("%a %H:%M")


async def test_setup_arms_next_school_day(hass, entry) -> None:
    await setup_entry(hass, entry)
    s = state(hass)
    assert s.state == STATE_ARMED
    assert local_next(hass) == "Tue 07:45"
    assert s.attributes["schedule"]["sat"] == {"enabled": False, "time": "07:45"}
    assert s.attributes["schedule"]["mon"] == {"enabled": True, "time": "07:45"}
    assert s.attributes["off_entities"] == [TV, SPEAKER]
    assert s.attributes["blink_lights"] == [LIGHT_ON, LIGHT_OFF]
    assert s.attributes["can_stop"] is False


async def test_update_targets_persists_and_changes_next_run(hass, entry, calls):
    await setup_entry(hass, entry)
    await call(hass, "set_config", off_entities=[SPEAKER], blink_lights=[LIGHT_OFF])
    assert entry.options["off_entities"] == [SPEAKER]
    assert entry.options["blink_lights"] == [LIGHT_OFF]
    assert attr(hass, "off_entities") == [SPEAKER]
    assert attr(hass, "blink_lights") == [LIGHT_OFF]

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await call(hass, "trigger_now")
    await settle(hass)
    assert calls["turn_off"][-1].data["entity_id"] == [SPEAKER]
    assert calls["light_on"][-1].data["entity_id"] == LIGHT_OFF
    assert not calls["light_off"]
    await call(hass, "stop")


async def test_clear_targets_preserves_other_options(hass, entry):
    await setup_entry(hass, entry)
    await call(hass, "set_config", off_entities=[])
    assert attr(hass, "off_entities") == []
    assert entry.options["blink_lights"] == [LIGHT_ON, LIGHT_OFF]
    await call(hass, "set_config", blink_lights=[])
    assert attr(hass, "blink_lights") == []


async def test_blink_targets_must_be_lights(hass, entry):
    await setup_entry(hass, entry)
    with pytest.raises(vol.Invalid):
        await call(hass, "set_config", blink_lights=[TV])
    assert entry.options["blink_lights"] == [LIGHT_ON, LIGHT_OFF]


async def test_change_targets_during_alert_restores_original_lights(hass, entry, calls):
    await setup_entry(hass, entry)
    await call(hass, "set_config", blink_interval=5)
    await call(hass, "trigger_now")
    await settle(hass)
    await call(hass, "set_config", blink_lights=[])
    assert state(hass).state == STATE_ARMED
    assert calls["light_on"][-1].data["entity_id"] == LIGHT_ON
    assert calls["light_off"][-1].data["entity_id"] == LIGHT_OFF
    assert entry.options["blink_lights"] == []


async def test_alert_turns_off_and_blinks_then_restores(hass, entry, freezer, calls, events):
    await setup_entry(hass, entry)
    await call(hass, "set_config", blink_count=3, blink_interval=1)
    first = dt_util.parse_datetime(attr(hass, "next_fire"))

    await jump_to(hass, freezer, first)
    await settle(hass)
    assert state(hass).state == STATE_ALERTING
    assert attr(hass, "can_stop") is True
    assert events[-1]["type"] == "triggered"
    assert len(calls["turn_off"]) == 1
    assert calls["turn_off"][0].data["entity_id"] == [TV, SPEAKER]

    for _ in range(8):
        await advance(hass, freezer, 1)
        await settle(hass)
        if state(hass).state == STATE_ARMED:
            break
    assert state(hass).state == STATE_ARMED
    assert events[-1]["type"] == "finished"

    # Light that was on: 3x off then on. Light that was off: 3x on then off.
    hall_off = [c for c in calls["light_off"] if c.data["entity_id"] == LIGHT_ON]
    hall_on = [c for c in calls["light_on"] if c.data["entity_id"] == LIGHT_ON]
    kitchen_on = [c for c in calls["light_on"] if c.data["entity_id"] == LIGHT_OFF]
    kitchen_off = [c for c in calls["light_off"] if c.data["entity_id"] == LIGHT_OFF]
    assert len(hall_off) == 3 and len(hall_on) == 3
    assert len(kitchen_on) == 3 and len(kitchen_off) == 3
    # last call per light leaves it in its original state
    assert (
        calls["light_on"][-1].data["entity_id"] == LIGHT_ON
        or calls["light_off"][-1].data["entity_id"] == LIGHT_OFF
    )

    assert local_next(hass) == "Wed 07:45"


async def test_stop_mid_blink_restores_lights(hass, entry, calls, events) -> None:
    await setup_entry(hass, entry)
    await call(hass, "set_config", blink_count=10, blink_interval=5)
    await call(hass, "trigger_now")
    await settle(hass)
    assert state(hass).state == STATE_ALERTING
    # First toggle step has been issued for both lights.
    assert any(c.data["entity_id"] == LIGHT_ON for c in calls["light_off"])
    assert any(c.data["entity_id"] == LIGHT_OFF for c in calls["light_on"])

    await call(hass, "stop")
    assert state(hass).state == STATE_ARMED
    assert events[-1]["type"] == "stopped"
    # Restore: hall back on, kitchen back off.
    assert calls["light_on"][-1].data["entity_id"] == LIGHT_ON
    assert calls["light_off"][-1].data["entity_id"] == LIGHT_OFF


async def test_set_day_and_schedule(hass, entry) -> None:
    await setup_entry(hass, entry)
    await call(hass, "set_day", day="tue", enabled=False)
    assert local_next(hass) == "Wed 07:45"
    await call(hass, "set_day", day="wed", time="08:10")
    assert local_next(hass) == "Wed 08:10"
    await call(
        hass,
        "set_config",
        schedule={"wed": {"enabled": False}, "sat": {"enabled": True, "time": "09:00"}},
    )
    assert local_next(hass) == "Thu 07:45"
    assert attr(hass, "schedule")["sat"] == {"enabled": True, "time": "09:00"}


async def test_all_days_disabled(hass, entry) -> None:
    await setup_entry(hass, entry)
    for day in ["mon", "tue", "wed", "thu", "fri"]:
        await call(hass, "set_day", day=day, enabled=False)
    assert state(hass).state == STATE_ARMED
    assert attr(hass, "next_fire") is None


async def test_master_disable_and_enable(hass, entry) -> None:
    await setup_entry(hass, entry)
    await call(hass, "set_config", enabled=False)
    assert state(hass).state == STATE_DISARMED
    assert attr(hass, "next_fire") is None
    await call(hass, "set_config", enabled=True)
    assert state(hass).state == STATE_ARMED
    assert local_next(hass) == "Tue 07:45"


async def test_skip_next(hass, entry, freezer, events, calls) -> None:
    await setup_entry(hass, entry)
    first = dt_util.parse_datetime(attr(hass, "next_fire"))
    await call(hass, "set_config", skip_next=True)
    assert attr(hass, "skipped_fire") == first.isoformat()
    assert local_next(hass) == "Wed 07:45"

    await jump_to(hass, freezer, first)
    await settle(hass)
    assert state(hass).state == STATE_ARMED
    assert attr(hass, "skip_next") is False
    assert events[-1]["type"] == "skipped"
    assert not calls["turn_off"]
    assert local_next(hass) == "Wed 07:45"


async def test_disable_during_alert_stops_it(hass, entry, calls, events) -> None:
    await setup_entry(hass, entry)
    await call(hass, "set_config", blink_interval=5)
    await call(hass, "trigger_now")
    await settle(hass)
    assert state(hass).state == STATE_ALERTING
    await call(hass, "set_config", enabled=False)
    assert state(hass).state == STATE_DISARMED
    assert events[-1] == {"entity_id": ENTITY_ID, "type": "stopped", "reason": "disabled"}


async def test_restore_settings(hass, entry) -> None:
    mock_restore_cache(
        hass,
        [
            State(
                ENTITY_ID,
                STATE_ALERTING,
                {
                    "blink_count": 7,
                    "blink_interval": 0.5,
                    "schedule": {"tue": {"enabled": False}, "fri": {"time": "08:30"}},
                    "skip_next": False,
                },
            )
        ],
    )
    await setup_entry(hass, entry)
    s = state(hass)
    assert s.state == STATE_ARMED
    assert s.attributes["blink_count"] == 7
    assert s.attributes["blink_interval"] == 0.5
    assert s.attributes["schedule"]["tue"]["enabled"] is False
    assert s.attributes["schedule"]["fri"]["time"] == "08:30"
    assert local_next(hass) == "Wed 07:45"


async def test_invalid_values_clamped(hass, entry) -> None:
    await setup_entry(hass, entry)
    with pytest.raises(vol.Invalid):
        await call(hass, "set_config", blink_count=0)
    with pytest.raises(vol.Invalid):
        await call(hass, "set_day", day="funday")
    assert attr(hass, "blink_count") == 5


async def test_timedelta_between_occurrences(hass, entry) -> None:
    await setup_entry(hass, entry)
    first = dt_util.parse_datetime(attr(hass, "next_fire"))
    await call(hass, "set_config", skip_next=True)
    second = dt_util.parse_datetime(attr(hass, "next_fire"))
    assert second - first == timedelta(days=1)


async def test_entity_id_is_name_and_school_in_any_language(hass, entry):
    from .conftest import setup_entry

    hass.config.language = "nb"
    await setup_entry(hass, entry)
    sensor = hass.states.get("sensor.barna_school")
    assert sensor is not None
    assert sensor.attributes["friendly_name"] == "Barna"


async def test_existing_entity_keeps_its_id(hass, entry):
    from homeassistant.helpers import entity_registry as er

    from .conftest import setup_entry

    er.async_get(hass).async_get_or_create(
        "sensor", "time_for_school", entry.entry_id, suggested_object_id="barna", config_entry=entry
    )
    await setup_entry(hass, entry)
    assert hass.states.get("sensor.barna") is not None
    assert hass.states.get("sensor.barna_school") is None
