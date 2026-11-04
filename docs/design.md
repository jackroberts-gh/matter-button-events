# Design: selected-device Matter button events

Status: experimental implementation; hardware acceptance pending. Date: 2026-11-03.
Baseline inspected: Home Assistant 2026.10.4.

## User-facing interface

Use the Home Assistant integration UI to select one existing Matter device per config entry.
Adding another device creates another entry; selecting the same source device twice is rejected.
The device selector filters for the official Matter integration. Validate the selected device on submit rather than trusting the selector alone.

Store the source Home Assistant device registry ID and source Matter config-entry ID. Resolve the operational node and endpoints from the source at runtime. Do not ask users to enter numeric node or endpoint IDs, parse display names, or silently select the first loaded Matter connection.

Create one additional event entity for every compatible Generic Switch endpoint belonging to the selected HA device. A composed/bridged device must not accidentally select siblings on the same Matter node. Scope endpoints according to the official Matter device-to-endpoint mapping. The initial implementation uses endpoint-number labels, such as Early button 1. Device-specific labels are deferred.

The stable unique ID combines the source Matter entry identity, operational device identity and endpoint ID. Display-name changes do not create new entities. A removed/re-paired device requires an explicit user selection again; never retarget a stale entry to a different device by name.

Only expose supported early event types:
- InitialPress → `initial_press`
- ShortRelease → `short_release`

Determine supported events from the Switch feature map and, where available, event-list information, with the exact baseline behavior covered by fixtures. A matching endpoint with no supported early events is not eligible. Show a clear `no_supported_buttons` error when no eligible endpoints are found.

## Internal design

Implemented files:

```text
custom_components/matter_button_events/
  manifest.json
  __init__.py
  config_flow.py
  const.py
  bridge.py
  event.py
  strings.json
  translations/en.json
  translations/de.json
tests/
  test_config_flow.py
  test_bridge.py
  test_event.py
```

- Manifest declares dependency on the official `matter` integration. No independent or conflicting Matter-client package pin.
- Config flow owns source selection, uniqueness checks and useful validation errors.
- Bridge owns resolving the source, endpoint discovery, lifecycle and subscriptions.
- Event platform owns entity availability and publishing HA event states.
- No device actions or light services in any module.

The bridge retrieves the existing client from the selected Matter entry runtime data and subscribes to NODE_EVENT with a node filter. It additionally checks the selected endpoint allowlist, Switch cluster ID and exact event ID before forwarding. All nonmatching events are ignored.

Use Home Assistant EventEntity, `_trigger_event` and a state write, so existing `event.received` triggers can be used. Two rapid identical event types must remain two separate events. Forward only whitelisted, non-sensitive event attributes; do not dump raw diagnostics.

Attach additional entities using the existing device entry; do not register its identifiers again under the custom config entry. HA devices have one owning config entry. Do not create a second physical device or rename existing entities. Removing the custom entry must not remove a Matter node or invoke the official integration's device-removal operations.

## Lifecycle and failure behavior

Wait/retry if the source Matter entry is not ready. An integration dependency alone does not prove that the source config entry has finished loading.

Observe source config-entry state and relevant node/endpoint changes. On source unload, remove only this bridge's callbacks and make its entities unavailable. On a newly loaded source client, resolve the source again and subscribe once. Never disconnect the shared client, stop the Matter server, alter platform handlers, write attributes or replace callbacks.

Availability reflects a loaded source, a valid selected device/endpoint and node availability. Missing devices do not trigger automatic selection of another device.

Callbacks do minimal synchronous work, never block, and contain their own errors so they cannot propagate into the shared event dispatcher. Log bounded, actionable errors rather than every packet. Every registered lifecycle or node listener has an explicit unsubscribe owned by this integration.

Startup, state restoration, reconnect and endpoint discovery must not synthesize button presses. Whether a server replays earlier raw events must be checked in the hardware experiment; replay handling is a separate correctness concern from intentionally accepting duplicate actions across early/legacy automation paths.

## Automation contract

The custom integration emits only early events. The official event entities continue providing multi-press and long-press events.

Users may retain delayed single-press triggers as fallback. The custom integration does not suppress duplicate actions and cannot guarantee ordering between separate automation runs. Use explicit on/off and desired-state actions rather than toggles when both paths are enabled.

Repeated effect or scene commands can restart effects. A delayed command can also override a more recent opposite command. The documentation and sample automations must explain these consequences rather than advertise the fallback as automatically safe.

A short release is not a replacement for long release. Holding begins with an initial press; automations using initial press therefore also run when a user starts holding. Device-specific repeated presses and the timing of multi-press sequences must be verified.

## Compatibility and distribution

Keep use of private Matter interfaces in bridge.py. This limits the code that needs inspection after HA changes; it does not provide process isolation or limit the permissions of Python code.

Use an HA config flow for community convenience. The previous six-entity YAML proposal is superseded for this reusable project; household automations remain a separate deployment.

Do not claim support for every brand or Matter device, stable production use, a measured latency reduction, or HACS approval before those claims are verified. Publish a compatibility table distinguishing source review, automated tests and hardware tests.

## Primary sources inspected

- [HA 2026.10.4 Matter events](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/matter/event.py)
- [HA 2026.10.4 Matter helpers](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/matter/helpers.py)
- [HA 2026.10.4 Matter lifecycle](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/matter/__init__.py)
- [HA 2026.10.4 event entities](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/event/__init__.py)
- [Upstream work on standardized Matter remote events](https://github.com/home-assistant/core/pull/177101)

These sources support the architecture; they do not substitute for running the custom integration.
