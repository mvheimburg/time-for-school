"""Sensor platform: one status entity per config entry plus entity services."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import WEEKDAYS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alert import SchoolAlertEntity
from .const import (
    ATTR_BLINK_COUNT,
    ATTR_BLINK_INTERVAL,
    ATTR_BLINK_LIGHTS,
    ATTR_DAY,
    ATTR_ENABLED,
    ATTR_OFF_ENTITIES,
    ATTR_SCHEDULE,
    ATTR_SKIP_NEXT,
    ATTR_TIME,
    MAX_BLINK_COUNT,
    MAX_BLINK_INTERVAL,
    MIN_BLINK_COUNT,
    MIN_BLINK_INTERVAL,
    SERVICE_SET_CONFIG,
    SERVICE_SET_DAY,
    SERVICE_STOP,
    SERVICE_TRIGGER_NOW,
)

DAY_FIELDS = {
    vol.Optional(ATTR_ENABLED): cv.boolean,
    vol.Optional(ATTR_TIME): vol.Any(cv.time, cv.string),
}

SET_CONFIG_FIELDS = {
    vol.Optional(ATTR_OFF_ENTITIES): cv.entity_ids,
    vol.Optional(ATTR_BLINK_LIGHTS): vol.All(cv.entity_ids, [cv.entity_domain("light")]),
    vol.Optional(ATTR_ENABLED): cv.boolean,
    vol.Optional(ATTR_SCHEDULE): vol.Schema({vol.In(WEEKDAYS): DAY_FIELDS}),
    vol.Optional(ATTR_BLINK_COUNT): vol.All(
        vol.Coerce(int), vol.Range(min=MIN_BLINK_COUNT, max=MAX_BLINK_COUNT)
    ),
    vol.Optional(ATTR_BLINK_INTERVAL): vol.All(
        vol.Coerce(float), vol.Range(min=MIN_BLINK_INTERVAL, max=MAX_BLINK_INTERVAL)
    ),
    vol.Optional(ATTR_SKIP_NEXT): cv.boolean,
}

SET_DAY_FIELDS = {vol.Required(ATTR_DAY): vol.In(WEEKDAYS), **DAY_FIELDS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Time for School entity from a config entry."""
    async_add_entities([SchoolAlertEntity(hass, entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_CONFIG, SET_CONFIG_FIELDS, "async_set_config"
    )
    platform.async_register_entity_service(SERVICE_SET_DAY, SET_DAY_FIELDS, "async_set_day")
    platform.async_register_entity_service(SERVICE_TRIGGER_NOW, None, "async_trigger")
    platform.async_register_entity_service(SERVICE_STOP, None, "async_stop")
