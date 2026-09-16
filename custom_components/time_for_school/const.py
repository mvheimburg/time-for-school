"""Constants for the Time for School integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "time_for_school"

# Config entry options (chosen in the config / options flow)
CONF_OFF_ENTITIES = "off_entities"
CONF_BLINK_LIGHTS = "blink_lights"

# Services
SERVICE_SET_CONFIG = "set_config"
SERVICE_SET_DAY = "set_day"
SERVICE_TRIGGER_NOW = "trigger_now"
SERVICE_STOP = "stop"

# Runtime settings (service fields / restored attributes)
ATTR_ENABLED = "enabled"
ATTR_SCHEDULE = "schedule"
ATTR_BLINK_COUNT = "blink_count"
ATTR_BLINK_INTERVAL = "blink_interval"
ATTR_SKIP_NEXT = "skip_next"
ATTR_DAY = "day"
ATTR_TIME = "time"

# Read-only attributes
ATTR_NEXT_FIRE = "next_fire"
ATTR_SKIPPED_FIRE = "skipped_fire"
ATTR_RUN_STARTED = "run_started"
ATTR_OFF_ENTITIES = "off_entities"
ATTR_BLINK_LIGHTS = "blink_lights"
ATTR_CAN_STOP = "can_stop"

# Entity states
STATE_DISARMED = "disarmed"
STATE_ARMED = "armed"
STATE_ALERTING = "alerting"

# Events: hass.bus event type is EVENT_TYPE, payload "type" is one of EVENT_*
EVENT_TYPE = f"{DOMAIN}_event"
EVENT_TRIGGERED = "triggered"
EVENT_FINISHED = "finished"
EVENT_STOPPED = "stopped"
EVENT_SKIPPED = "skipped"

# Defaults
DEFAULT_TIME = "07:45"
DEFAULT_SCHOOL_DAYS = ["mon", "tue", "wed", "thu", "fri"]
DEFAULT_BLINK_COUNT = 5
DEFAULT_BLINK_INTERVAL = 1.0  # seconds
DEFAULT_ENABLED = True

MIN_BLINK_COUNT = 1
MAX_BLINK_COUNT = 50
MIN_BLINK_INTERVAL = 0.2
MAX_BLINK_INTERVAL = 10.0

PLATFORMS: list[Platform] = [Platform.SENSOR]
