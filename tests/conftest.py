"""Shared fixtures for Time for School tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.time_for_school.const import (
    CONF_BLINK_LIGHTS,
    CONF_OFF_ENTITIES,
    DOMAIN,
)

ENTITY_ID = "sensor.barna_school"
TV = "media_player.tv"
SPEAKER = "media_player.kitchen"
LIGHT_ON = "light.hall"
LIGHT_OFF = "light.kitchen"

# A fixed "now": Monday 2026-09-14 22:00 UTC (Tuesday 00:00 in Europe/Copenhagen)
START = datetime(2026, 9, 14, 22, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def calls(hass: HomeAssistant):
    return {
        "turn_off": async_mock_service(hass, "homeassistant", "turn_off"),
        "light_on": async_mock_service(hass, "light", "turn_on"),
        "light_off": async_mock_service(hass, "light", "turn_off"),
    }


@pytest.fixture
def events(hass: HomeAssistant):
    captured = []
    hass.bus.async_listen(f"{DOMAIN}_event", lambda e: captured.append(e.data))
    return captured


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Barna",
        data={},
        options={CONF_OFF_ENTITIES: [TV, SPEAKER], CONF_BLINK_LIGHTS: [LIGHT_ON, LIGHT_OFF]},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.states.async_set(LIGHT_ON, "on")
    hass.states.async_set(LIGHT_OFF, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(DOMAIN, service, {"entity_id": ENTITY_ID, **data}, blocking=True)
    await hass.async_block_till_done()


def state(hass: HomeAssistant):
    return hass.states.get(ENTITY_ID)


def attr(hass: HomeAssistant, name: str):
    return state(hass).attributes.get(name)


async def advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def jump_to(hass: HomeAssistant, freezer, when: datetime) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def settle(hass: HomeAssistant) -> None:
    for _ in range(10):
        await hass.async_block_till_done()
