"""School alert entity: weekly schedule, turn-off list and blinking lights."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    WEEKDAYS,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BLINK_COUNT,
    ATTR_BLINK_INTERVAL,
    ATTR_BLINK_LIGHTS,
    ATTR_CAN_STOP,
    ATTR_ENABLED,
    ATTR_NEXT_FIRE,
    ATTR_OFF_ENTITIES,
    ATTR_RUN_STARTED,
    ATTR_SCHEDULE,
    ATTR_SKIP_NEXT,
    ATTR_SKIPPED_FIRE,
    ATTR_TIME,
    CONF_BLINK_LIGHTS,
    CONF_OFF_ENTITIES,
    DEFAULT_BLINK_COUNT,
    DEFAULT_BLINK_INTERVAL,
    DEFAULT_ENABLED,
    DEFAULT_SCHOOL_DAYS,
    DEFAULT_TIME,
    DOMAIN,
    EVENT_FINISHED,
    EVENT_SKIPPED,
    EVENT_STOPPED,
    EVENT_TRIGGERED,
    EVENT_TYPE,
    MAX_BLINK_COUNT,
    MAX_BLINK_INTERVAL,
    MIN_BLINK_COUNT,
    MIN_BLINK_INTERVAL,
    STATE_ALERTING,
    STATE_ARMED,
    STATE_DISARMED,
)

_LOGGER = logging.getLogger(__name__)


def _parse_time(raw: Any) -> time | None:
    """Parse a time object or 'HH:MM[:SS]' string into a minute-precision time."""
    if isinstance(raw, time):
        return raw.replace(second=0, microsecond=0)
    parts = str(raw).strip().split(":")
    if len(parts) < 2:
        return None
    return time(hour=int(parts[0]), minute=int(parts[1]))


@dataclass
class DaySchedule:
    enabled: bool
    time: time

    def as_dict(self) -> dict[str, Any]:
        return {ATTR_ENABLED: self.enabled, ATTR_TIME: self.time.isoformat(timespec="minutes")}


def _default_schedule() -> dict[str, DaySchedule]:
    default_time = _parse_time(DEFAULT_TIME)
    return {
        day: DaySchedule(enabled=day in DEFAULT_SCHOOL_DAYS, time=default_time) for day in WEEKDAYS
    }


@dataclass
class AlertConfig:
    """User-adjustable runtime settings (persisted via restore state)."""

    enabled: bool = DEFAULT_ENABLED
    schedule: dict[str, DaySchedule] = field(default_factory=_default_schedule)
    blink_count: int = DEFAULT_BLINK_COUNT
    blink_interval: float = DEFAULT_BLINK_INTERVAL
    skip_next: bool = False


class SchoolAlertEntity(RestoreEntity, Entity):
    """One "time to leave for school" alert per config entry.

    States: disarmed -> armed -> alerting -> armed. While alerting the
    configured entities are turned off and the lights blink `blink_count`
    times, then return to the state they were in.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:school"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_name = entry.title or "Time for school"
        self._attr_unique_id = entry.entry_id

        self._config = AlertConfig()
        self._state: str = STATE_DISARMED
        self._next_fire: datetime | None = None
        self._skipped_fire: datetime | None = None
        self._run_started: datetime | None = None
        self._light_restore: dict[str, bool] = {}

        self._unsub_timer: CALLBACK_TYPE | None = None
        self._run_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Entity API
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cfg = self._config
        return {
            ATTR_ENABLED: cfg.enabled,
            ATTR_SCHEDULE: {day: cfg.schedule[day].as_dict() for day in WEEKDAYS},
            ATTR_BLINK_COUNT: cfg.blink_count,
            ATTR_BLINK_INTERVAL: cfg.blink_interval,
            ATTR_SKIP_NEXT: cfg.skip_next,
            ATTR_NEXT_FIRE: self._next_fire.isoformat() if self._next_fire else None,
            ATTR_SKIPPED_FIRE: self._skipped_fire.isoformat() if self._skipped_fire else None,
            ATTR_RUN_STARTED: self._run_started.isoformat() if self._run_started else None,
            ATTR_OFF_ENTITIES: self._off_entities,
            ATTR_BLINK_LIGHTS: self._blink_lights,
            ATTR_CAN_STOP: self._state == STATE_ALERTING,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._apply_runtime_settings(dict(last_state.attributes))
        await self._reschedule()
        self._write()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_timer()
        await self._cancel_run()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @property
    def _off_entities(self) -> list[str]:
        raw = self._entry.options.get(CONF_OFF_ENTITIES, [])
        return [str(e) for e in raw if e] if isinstance(raw, list) else []

    @property
    def _blink_lights(self) -> list[str]:
        raw = self._entry.options.get(CONF_BLINK_LIGHTS, [])
        return [str(e) for e in raw if e] if isinstance(raw, list) else []

    def _write(self) -> None:
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    def _set_state(self, new_state: str) -> None:
        if new_state != self._state:
            _LOGGER.debug("%s: %s -> %s", self.entity_id, self._state, new_state)
        self._state = new_state
        self._write()

    def _fire_event(self, event_type: str, **extra: Any) -> None:
        self.hass.bus.async_fire(
            EVENT_TYPE, {"entity_id": self.entity_id, "type": event_type, **extra}
        )

    def _apply_day(self, day: str, data: dict[str, Any]) -> None:
        day = str(day).strip().lower()[:3]
        if day not in WEEKDAYS:
            _LOGGER.error("Invalid weekday %r for %s", day, self.entity_id)
            return
        current = self._config.schedule[day]
        if ATTR_ENABLED in data:
            current.enabled = bool(data[ATTR_ENABLED])
        if ATTR_TIME in data:
            try:
                parsed = _parse_time(data[ATTR_TIME])
            except (TypeError, ValueError):
                parsed = None
            if parsed is None:
                _LOGGER.error("Invalid time %r for %s", data[ATTR_TIME], self.entity_id)
            else:
                current.time = parsed

    def _apply_runtime_settings(self, data: dict[str, Any]) -> None:
        """Apply runtime settings from service data or restored attributes."""
        cfg = self._config

        if ATTR_ENABLED in data:
            cfg.enabled = bool(data[ATTR_ENABLED])

        if ATTR_SCHEDULE in data and isinstance(data[ATTR_SCHEDULE], dict):
            for day, day_data in data[ATTR_SCHEDULE].items():
                if isinstance(day_data, dict):
                    self._apply_day(day, day_data)

        if ATTR_BLINK_COUNT in data:
            try:
                cfg.blink_count = max(
                    MIN_BLINK_COUNT, min(MAX_BLINK_COUNT, int(data[ATTR_BLINK_COUNT]))
                )
            except (TypeError, ValueError):
                _LOGGER.error(
                    "Invalid blink_count %r for %s", data[ATTR_BLINK_COUNT], self.entity_id
                )

        if ATTR_BLINK_INTERVAL in data:
            try:
                cfg.blink_interval = max(
                    MIN_BLINK_INTERVAL,
                    min(MAX_BLINK_INTERVAL, float(data[ATTR_BLINK_INTERVAL])),
                )
            except (TypeError, ValueError):
                _LOGGER.error(
                    "Invalid blink_interval %r for %s",
                    data[ATTR_BLINK_INTERVAL],
                    self.entity_id,
                )

        if ATTR_SKIP_NEXT in data:
            cfg.skip_next = bool(data[ATTR_SKIP_NEXT])

    # ------------------------------------------------------------------ #
    # Scheduling
    # ------------------------------------------------------------------ #

    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    def _next_occurrences(self, now_local: datetime, count: int) -> list[datetime]:
        """Return the next `count` enabled occurrences (UTC) from the weekly schedule."""
        found: list[datetime] = []
        for offset in range(0, 8 + count):
            day = now_local.date() + timedelta(days=offset)
            day_cfg = self._config.schedule[WEEKDAYS[day.weekday()]]
            if not day_cfg.enabled:
                continue
            candidate = datetime.combine(day, day_cfg.time, tzinfo=now_local.tzinfo)
            if candidate <= now_local:
                continue
            found.append(dt_util.as_utc(candidate))
            if len(found) >= count:
                break
        return found

    async def _reschedule(self) -> None:
        """Arm the next occurrence (or disarm). Does not touch a running alert."""
        self._cancel_timer()
        self._skipped_fire = None

        if not self._config.enabled:
            self._next_fire = None
            self._set_state(STATE_DISARMED)
            return

        occurrences = self._next_occurrences(dt_util.now(), 2)
        if not occurrences:
            self._next_fire = None
            self._set_state(STATE_ARMED)
            return

        if self._config.skip_next:
            self._skipped_fire = occurrences[0]
            self._next_fire = occurrences[1] if len(occurrences) > 1 else None
        else:
            self._next_fire = occurrences[0]

        _LOGGER.info(
            "%s armed: timer=%s next_fire=%s skipped=%s",
            self.entity_id,
            occurrences[0],
            self._next_fire,
            self._skipped_fire,
        )
        self._unsub_timer = async_track_point_in_utc_time(
            self.hass, self._on_alert_time, occurrences[0]
        )
        self._set_state(STATE_ARMED)

    @callback
    def _on_alert_time(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.hass.async_create_task(self._handle_alert_time())

    async def _handle_alert_time(self) -> None:
        if self._config.skip_next:
            skipped = self._skipped_fire
            self._config.skip_next = False
            _LOGGER.info("%s: skipping occurrence %s", self.entity_id, skipped)
            self._fire_event(EVENT_SKIPPED, fire_time=skipped.isoformat() if skipped else None)
            await self._reschedule()
            self._write()
            return
        await self._start_run()

    # ------------------------------------------------------------------ #
    # Run lifecycle
    # ------------------------------------------------------------------ #

    async def _start_run(self) -> None:
        self._cancel_timer()
        await self._cancel_run()
        self._run_started = dt_util.utcnow()
        self._run_task = self._entry.async_create_background_task(
            self.hass, self._run(), name=f"{DOMAIN} alert {self.entity_id}"
        )

    async def _cancel_run(self) -> None:
        task = self._run_task
        self._run_task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        try:
            self._set_state(STATE_ALERTING)
            self._fire_event(EVENT_TRIGGERED)
            self._light_restore = {}

            try:
                await asyncio.gather(
                    self._turn_off_entities(),
                    *(self._blink_light(light) for light in self._blink_lights),
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception("%s: error during alert", self.entity_id)

            self._light_restore = {}
            self._fire_event(EVENT_FINISHED)
            self._run_task = None
            self._run_started = None
            await self._reschedule()
            self._write()
        finally:
            if self._run_task is asyncio.current_task():
                self._run_task = None

    async def _turn_off_entities(self) -> None:
        entities = self._off_entities
        if not entities:
            return
        _LOGGER.info("%s: turning off %s", self.entity_id, entities)
        try:
            await self.hass.services.async_call(
                "homeassistant", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entities}, blocking=True
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("%s: error turning off %s: %s", self.entity_id, entities, exc)

    async def _light_call(self, light: str, turn_on: bool, blocking: bool = False) -> None:
        await self.hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: light},
            blocking=blocking,
        )

    async def _blink_light(self, light: str) -> None:
        """Toggle a light blink_count times and leave it as it was."""
        state = self.hass.states.get(light)
        was_on = state is not None and state.state == STATE_ON
        self._light_restore[light] = was_on
        count = self._config.blink_count
        interval = self._config.blink_interval
        _LOGGER.info("%s: blinking %s %s times (was_on=%s)", self.entity_id, light, count, was_on)

        for i in range(count):
            await self._light_call(light, turn_on=not was_on)
            await asyncio.sleep(interval)
            await self._light_call(light, turn_on=was_on)
            if i < count - 1:
                await asyncio.sleep(interval)

    async def _restore_lights(self) -> None:
        """Put lights back to their pre-alert state after a cancelled run."""
        restore, self._light_restore = self._light_restore, {}
        for light, was_on in restore.items():
            try:
                await self._light_call(light, turn_on=was_on, blocking=True)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("%s: error restoring %s: %s", self.entity_id, light, exc)

    # ------------------------------------------------------------------ #
    # Service entry points
    # ------------------------------------------------------------------ #

    async def async_set_config(self, **data: Any) -> None:
        was_enabled = self._config.enabled
        self._apply_runtime_settings(data)
        if was_enabled and not self._config.enabled:
            await self._disarm()
        elif self._state != STATE_ALERTING:
            await self._reschedule()
        self._write()

    async def async_set_day(self, day: str, **data: Any) -> None:
        self._apply_day(day, data)
        if self._state != STATE_ALERTING:
            await self._reschedule()
        self._write()

    async def _disarm(self) -> None:
        was_alerting = self._state == STATE_ALERTING
        self._cancel_timer()
        await self._cancel_run()
        if was_alerting:
            await self._restore_lights()
            self._fire_event(EVENT_STOPPED, reason="disabled")
        self._run_started = None
        await self._reschedule()

    async def async_trigger(self) -> None:
        _LOGGER.info("%s: manual trigger", self.entity_id)
        await self._start_run()

    async def async_stop(self) -> None:
        was_alerting = self._state == STATE_ALERTING
        await self._cancel_run()
        if was_alerting:
            await self._restore_lights()
            self._fire_event(EVENT_STOPPED, reason="user")
        self._run_started = None
        await self._reschedule()
        self._write()
