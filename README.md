# Matter Button Events

Experimental Home Assistant custom integration exposing early button events from **selected, already paired Matter devices** without replacing the official Matter integration.

**Status: experimental implementation; hardware acceptance is pending.** No latency reduction or production reliability is claimed yet. This is an early experimental version; hardware acceptance is pending.

## Installation and setup

Requires **Home Assistant 2026.10.4 or later**. Automated verification targets 2026.10.4; later releases need their own compatibility checks because internal Matter interfaces can change.

1. Copy `custom_components/matter_button_events` into your Home Assistant `config/custom_components/` directory. Use a reviewed commit and retain a backup. Do not create or replace `custom_components/matter`.
2. Restart Home Assistant.
3. Add **Matter Button Events** in Settings → Devices & services.
4. Select an existing device provided by the official Matter integration.
5. The integration discovers compatible Generic Switch endpoints and creates an additional event entity per endpoint, named **Early button 1**, etc.
6. Use `initial_press` or `short_release` in an automation.

Repeat setup for additional devices. No node IDs, endpoint IDs, credentials, re-pairing or brand-specific configuration are required. Only events supported and actually sent by the device can be exposed; an arbitrary Matter device does not become a button. Existing Matter entities remain available.

## Automation example

Replace the placeholder entity IDs with your entities:

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.example_remote_early_button_1
    options:
      event_type:
        - initial_press
actions:
  - action: light.turn_on
    target:
      entity_id: light.example
mode: queued
max: 10
```

Use `short_release` to react when a short press is released. Holding also starts with an initial press; short release is not long release. Multi-press and hold actions still use the original Matter entities.

Delayed single-press triggers can remain as fallback, but both paths may execute. Use explicit on/off rather than toggle. Repeated effect commands may restart an effect; a delayed on-command may override a newer off-command. Test your own automation behavior. This integration does not suppress duplicate actions across the early and regular paths.

## Scope and limits

- Domain: `matter_button_events`; one UI config entry per selected device. No YAML configuration of this integration.
- Reuses the selected Matter entry's client; no additional controller, cloud service or polling.
- Does not send device commands, alter attributes, replace callbacks or patch the official integration.
- Normal Matter entities and their multi-press/hold events are preserved.
- Runs in the HA process and depends on internal Matter interfaces. Device filtering is not a security sandbox.
- Exposes only `initial_press` and `short_release`, when supported. Devices without compatible buttons are rejected.
- Restored state and reconnect do not synthesize button presses. Actual server replay behavior and physical-device timing remain hardware acceptance work.

Automated tests use real HA fixtures and a deterministic Matter-client test double. They do not prove physical-device compatibility. See [the implementation and verification plan](docs/implementation-plan.md) for remaining acceptance work.

## Removal

First remove the additional early-event triggers from your automations and retain or restore the regular Matter triggers. Remove each **Matter Button Events** entry. Then delete only `custom_components/matter_button_events` and restart HA. This integration never removes or re-pairs a Matter node.

## Development

Use Python 3.14.2 or later in an isolated environment:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```

Tests never connect to a Matter server. Real use requires the official Matter integration and reuses its pinned client dependency. The test dependency pins match the inspected HA baseline rather than introducing runtime package overrides.

## Documentation and reuse

- [Architecture and behavior](docs/design.md)
- [Implementation and verification plan](docs/implementation-plan.md)

Code and documentation use the [MIT license](LICENSE). The config flow includes English and German. No HACS default-store inclusion or release validation is claimed. Household automations, network information, device identifiers and credentials do not belong in this repository.
