"""Config flow for the Time for School integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

from .const import CONF_BLINK_LIGHTS, CONF_OFF_ENTITIES, DOMAIN

DEFAULT_NAME = "Time for school"

OFF_DOMAINS = ["media_player", "switch", "light", "fan", "remote", "input_boolean"]


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Optional(CONF_OFF_ENTITIES, default=defaults.get(CONF_OFF_ENTITIES, [])): selector(
                {"entity": {"multiple": True, "domain": OFF_DOMAINS}}
            ),
            vol.Optional(CONF_BLINK_LIGHTS, default=defaults.get(CONF_BLINK_LIGHTS, [])): selector(
                {"entity": {"multiple": True, "domain": "light"}}
            ),
        }
    )


def _validate(user_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    errors: dict[str, str] = {}
    off_entities = list(user_input.get(CONF_OFF_ENTITIES) or [])
    blink_lights = list(user_input.get(CONF_BLINK_LIGHTS) or [])
    if not off_entities and not blink_lights:
        errors["base"] = "nothing_to_do"
    return errors, {CONF_OFF_ENTITIES: off_entities, CONF_BLINK_LIGHTS: blink_lights}


class TimeForSchoolConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, options = _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data={}, options=options
                )
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TimeForSchoolOptionsFlow:
        return TimeForSchoolOptionsFlow(config_entry)


class TimeForSchoolOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, options = _validate(user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self._entry, title=user_input[CONF_NAME]
                )
                return self.async_create_entry(title="", data=options)
        current = {**self._entry.options, CONF_NAME: self._entry.title}
        return self.async_show_form(step_id="init", data_schema=_schema(current), errors=errors)
