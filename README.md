# Time for School (Home Assistant integration)

A "time to leave for school" house alert: at a set time on each school day it
turns off any number of entities (TVs, speakers, ...) and blinks any number of
lights a configurable number of times, then puts the lights back as they were.

Pair it with the [Lovelace Time for School card](https://github.com/mvheimburg/lovelace-time-for-school)
for a weekly schedule editor and a Stop button.

## How it works

```
disarmed ─enable─▶ armed ─alert time─▶ alerting ─done / stop─▶ armed
```

- **armed**: waiting for the next enabled weekday time (`next_fire`).
- **alerting**: `off_entities` receive `homeassistant.turn_off`; every light in
  `blink_lights` toggles `blink_count` times with `blink_interval` seconds
  between steps. A light that was on blinks off/on and ends on; a light that
  was off blinks on/off and ends off.
- **stop** cancels the blinking and restores each light to its pre-alert state.

Each weekday has its own on/off switch and time. A master `enabled` switch
disarms everything, and `skip_next` skips exactly one occurrence.

## Installation (HACS)

1. Add this repository as a custom repository in HACS (category *Integration*).
2. Install **Time for School** and restart Home Assistant.
3. Add the integration from **Settings → Devices & services**, pick the
   entities to turn off and the lights to blink.

One `sensor.<name>` entity is created per config entry with state
`disarmed`, `armed` or `alerting`. All schedule settings are changed from the
card or the services below and survive restarts.

## Services

All services target the sensor entity.

| Service | Fields | What it does |
| --- | --- | --- |
| `time_for_school.set_config` | `enabled`, `schedule`, `blink_count`, `blink_interval`, `skip_next`, `off_entities`, `blink_lights` | Update settings. `schedule` is a partial map like `{mon: {enabled: true, time: "07:45"}, sat: {enabled: false}}`. Device lists replace the previous selection; use `[]` to clear a list. |
| `time_for_school.set_day` | `day` (`mon`..`sun`), `enabled`, `time` | Change one weekday. |
| `time_for_school.trigger_now` | | Run the alert now. |
| `time_for_school.stop` | | Stop a running alert and restore the lights. |

Device selections are saved in the integration options and survive restarts.
Changing a device list during an alert stops it and restores the original lights
before reloading the entry with the new selection.

## Attributes

`enabled`, `schedule` (per weekday `{enabled, time}`), `blink_count`,
`blink_interval`, `skip_next`, `next_fire`, `skipped_fire`, `run_started`,
`off_entities`, `blink_lights`, `can_stop`.

## Events

`time_for_school_event` with `entity_id` and `type`:

| `type` | Extra | When |
| --- | --- | --- |
| `triggered` | | The alert starts |
| `finished` | | Blinking completed |
| `stopped` | `reason`: `user` or `disabled` | Stopped early |
| `skipped` | `fire_time` | An occurrence was skipped via `skip_next` |

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check custom_components tests
```

Releases are automatic: bump `version` in both `pyproject.toml` and
`custom_components/time_for_school/manifest.json`, merge to `main`, and the
release workflow tags `v<version>` and publishes a GitHub release.
