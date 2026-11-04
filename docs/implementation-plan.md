# Implementation and verification plan

Status: experimental implementation and automated tests are included. Hardware acceptance and public-release validation remain open.

## 1. Capture a real early-event sequence

With an explicitly authorized experimental installation, observe initial press, short release, long press/release and completed multi-press events from a representative physical remote. Keep raw diagnostics private and create reduced fixtures without household identifiers. Measure early-to-complete timing within a common clock domain. Do not compare a device-relative timestamp directly to HA wall-clock time.

Hardware acceptance must prove that early events reach the existing client before the legacy event-entity filter. If they do not, revise the candidate before changing automations. A local candidate can be implemented and tested without installing it on a live instance.

## 2. Implement the device selector and event bridge

Build one UI config entry per selected existing Matter device and automatic endpoint discovery. Keep the integration domain independent from `matter`. Implement controlled retries, source reload, unload and availability.

## 3. Validate meaningful behavior

Local verification (2026-11-04): 16 tests passed against Home Assistant 2026.10.4 on Python 3.14.10. This includes actual HA config flows, event entities and registry behavior, with a non-networked client test double and an additional real MatterNode model fixture. Ruff lint/format checks and whitespace checks passed. No runtime or household behavior was tested on a live instance. The simplification removes duplicate bridge state and listener registries, scopes refresh to the selected node, and verifies deferred cache cleanup after removal notifications.

Automated checks should cover:
- Only official Matter devices can be configured; duplicates and devices without compatible switch endpoints fail clearly.
- One selected device cannot forward events from other devices or bridged/composed siblings.
- Correct endpoint, cluster and event mapping; malformed events are contained.
- Feature-dependent supported event types.
- Two rapid identical real events are delivered separately.
- Source not ready, device unavailable, source client replacement and endpoint changes.
- Repeated setup/reload/unload leaves exactly one listener and never disconnects the shared Matter client.
- State restoration and setup do not fabricate presses.
- Removing the custom entry never removes or controls the physical Matter node.

Run tests with actual Home Assistant integration fixtures before claiming HA compatibility. Pure mapping tests or syntax checks alone are not sufficient.

## 4. Hardware acceptance

After explicit deployment approval:
- Verify both buttons on several selected remotes.
- Check short tap, hold, double tap, rapid alternating buttons and two remotes used together.
- Check the regular delayed fallback with early events unavailable.
- Check duplicate calls to effects and delayed commands arriving after newer opposite commands.
- Reload Matter, restart HA and verify recovery without duplicate listeners.
- Verify unrelated Matter devices still work.
- Confirm that uninstalling this custom integration restores the original-only path without re-pairing.

## 5. Prepare reuse

Before a public release:
- MIT license included for the original implementation. Preserve attribution for any future reused upstream code.
- Document verified HA/device versions and known limitations.
- Add installation/removal instructions, example automations and release packaging.
- Validate any proposed HACS metadata; do not imply default-store inclusion.
- Describe the temporary relationship to official upstream support and the eventual removal path.

## Deployment boundary

Repository creation and design publication do not authorize installation in a running Home Assistant instance. The household's automation changes and live activation are separate reviewable work.
