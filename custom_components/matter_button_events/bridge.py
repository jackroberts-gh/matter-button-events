"""Read selected-device events from the existing HA Matter client.

All dependence on the official integration's internal runtime lives here.
This module never opens, disconnects, or sends commands over that client.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chip.clusters import Objects as clusters
from homeassistant.components.matter.const import ID_TYPE_DEVICE_ID
from homeassistant.components.matter.helpers import get_device_id
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from matter_server.client.models.device_types import GenericSwitch
from matter_server.common.errors import NodeNotExists
from matter_server.common.models import EventType

from .const import CONF_DEVICE_ID, CONF_SOURCE_ENTRY_ID, CONF_SOURCE_IDENTIFIER

_LOGGER = logging.getLogger(__name__)
_FEATURE = clusters.Switch.Bitmaps.Feature
_EVENTS = {1: "initial_press", 3: "short_release"}


class SourceError(Exception):
    """A source cannot be used; the code also names its UI error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Button:
    """One endpoint owned by the selected HA device."""

    endpoint_id: int
    event_types: tuple[str, ...]
    available: bool


@dataclass
class Source:
    """A resolved source, deliberately bound to one config entry and identity."""

    entry: Any
    client: Any
    node_id: int
    identifier: str
    buttons: dict[int, Button]


def _button(endpoint: Any) -> Button | None:
    """Read feature-dependent early events; do not infer them from brand names."""
    if GenericSwitch not in endpoint.device_types:
        return None
    feature = endpoint.get_attribute_value(None, clusters.Switch.Attributes.FeatureMap)
    if not isinstance(feature, int) or not feature & _FEATURE.kMomentarySwitch:
        return None
    events = ["initial_press"]
    if feature & _FEATURE.kMomentarySwitchRelease:
        events.append("short_release")
    # The generated SDK does not expose EventList as a Switch attribute.
    # Read the optional global attribute (0xFFFA) from the existing node cache.
    event_list = endpoint.node.node_data.attributes.get(
        f"{endpoint.endpoint_id}/{clusters.Switch.id}/65530"
    )
    if isinstance(event_list, list):
        events = [
            name for event_id, name in _EVENTS.items() if event_id in event_list and name in events
        ]
    if not events:
        return None

    available = bool(endpoint.node.available)
    parent = endpoint.node.get_compose_parent(endpoint.endpoint_id)
    for target in (endpoint, parent):
        if (
            target is not None
            and target.get_attribute_value(
                None, clusters.BridgedDeviceBasicInformation.Attributes.Reachable
            )
            is False
        ):
            available = False
    return Button(endpoint.endpoint_id, tuple(events), available)


@callback
def resolve_source(
    hass: HomeAssistant,
    device_id: str,
    source_entry_id: str | None = None,
    expected_identifier: str | None = None,
    node_id: int | None = None,
) -> Source:
    """Resolve only endpoints represented by the selected HA device.

    Matching the official identifier also scopes composed and bridged devices:
    sharing a node alone is never enough to admit a sibling endpoint.
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise SourceError("device_not_found")
    entry = hass.config_entries.async_get_entry(device.config_entry_id)
    if (
        entry is None
        or entry.domain != "matter"
        or (source_entry_id is not None and entry.entry_id != source_entry_id)
    ):
        raise SourceError("not_matter_device")
    if entry.state is not ConfigEntryState.LOADED:
        raise SourceError("source_not_ready")
    try:
        client = entry.runtime_data.adapter.matter_client
        if client.server_info is None:
            raise SourceError("source_not_ready")
        matches: dict[tuple[int, str], dict[int, Button]] = {}
        nodes = client.get_nodes() if node_id is None else (client.get_node(node_id),)
        for node in nodes:
            for endpoint in node.endpoints.values():
                identifier = f"{ID_TYPE_DEVICE_ID}_{get_device_id(client.server_info, endpoint)}"
                if ("matter", identifier) not in device.identifiers:
                    continue
                if expected_identifier is not None and identifier != expected_identifier:
                    continue
                key = (node.node_id, identifier)
                buttons = matches.setdefault(key, {})
                if (button := _button(endpoint)) is not None:
                    buttons[button.endpoint_id] = button
    except NodeNotExists as err:
        raise SourceError("device_not_found") from err
    except (AttributeError, TypeError, ValueError) as err:
        raise SourceError("incompatible_source") from err
    if not matches:
        raise SourceError("device_not_found")
    if len(matches) != 1:
        raise SourceError("ambiguous_source")
    (node_id, identifier), buttons = next(iter(matches.items()))
    if not buttons:
        raise SourceError("no_supported_buttons")
    return Source(entry, client, node_id, identifier, buttons)


class MatterEventBridge:
    """Own subscriptions; notify listeners of early events or source changes."""

    def __init__(self, hass: HomeAssistant, data: dict[str, Any], source: Source) -> None:
        self.hass = hass
        self.data = data
        self.source = source
        self._faulted = False
        self._subscriptions: list[Callable[[], None]] = []
        self._state_unsubscribe: Callable[[], None] | None = None
        self._listeners: set[Callable[[int | None, str | None, dict], None]] = set()

    @property
    def buttons(self) -> dict[int, Button]:
        return self.source.buttons

    def listen(
        self, listener: Callable[[int | None, str | None, dict], None]
    ) -> Callable[[], None]:
        """Subscribe; endpoint=None means availability/discovery changed."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def available(self, endpoint: int) -> bool:
        button = self.buttons.get(endpoint)
        return self._state_unsubscribe is not None and button is not None and button.available

    def start(self) -> None:
        if self._state_unsubscribe is None:
            # Keep this listener across source unloads, until our own unload.
            self._state_unsubscribe = self.source.entry.async_on_state_change(
                self._source_state_changed
            )
            self._source_state_changed()

    def stop(self) -> None:
        """Remove only our callbacks; never disconnect the shared client."""
        if self._state_unsubscribe is not None:
            self._state_unsubscribe()
            self._state_unsubscribe = None
        self._detach()
        self._notify()

    def _detach(self) -> None:
        self.source.buttons = {}
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()

    @callback
    def _source_state_changed(self) -> None:
        if self._state_unsubscribe is None:
            return
        if self.source.entry.state is not ConfigEntryState.LOADED:
            self._detach()
            self._notify()
            return
        try:
            client = self.source.entry.runtime_data.adapter.matter_client
            if not self._subscriptions or client is not self.source.client:
                self._detach()
                self._faulted = False
                self.source.client = client
                for event_type in (
                    EventType.NODE_EVENT,
                    EventType.NODE_UPDATED,
                    EventType.ATTRIBUTE_UPDATED,
                    EventType.NODE_REMOVED,
                    EventType.NODE_ADDED,
                    EventType.ENDPOINT_ADDED,
                    EventType.ENDPOINT_REMOVED,
                ):
                    handler = (
                        self._on_event if event_type is EventType.NODE_EVENT else self._refresh
                    )
                    # ENDPOINT_ADDED lacks node_id in the pinned client's dispatch.
                    node_filter = (
                        None if event_type is EventType.ENDPOINT_ADDED else self.source.node_id
                    )
                    self._subscriptions.append(
                        client.subscribe_events(
                            handler,
                            event_filter=event_type,
                            node_filter=node_filter,
                        )
                    )
            self.source = resolve_source(
                self.hass,
                self.data[CONF_DEVICE_ID],
                self.data[CONF_SOURCE_ENTRY_ID],
                self.data[CONF_SOURCE_IDENTIFIER],
                self.source.node_id,
            )
        except SourceError:
            # Keep listeners: the same device/endpoint can return later.
            self.source.buttons = {}
        except Exception:  # Never propagate a callback failure into Matter.
            self._detach()
            self._log_failure()
        self._notify()

    @callback
    def _refresh(self, event: Any, _data: Any) -> None:
        if event in (EventType.NODE_REMOVED, EventType.ENDPOINT_REMOVED):
            # The client removes cached nodes/endpoints AFTER notifying us.
            self.hass.loop.call_soon(self._source_state_changed)
        else:
            self._source_state_changed()

    def _notify(
        self, endpoint: int | None = None, name: str | None = None, attributes: dict | None = None
    ) -> None:
        for listener in tuple(self._listeners):
            try:
                listener(endpoint, name, attributes or {})
            except Exception:
                self._log_failure()

    def _log_failure(self) -> None:
        if not self._faulted:
            self._faulted = True
            _LOGGER.exception(
                "Matter Button Events callback failed; reload this integration if it persists"
            )

    @callback
    def _on_event(self, _event: Any, event: Any) -> None:
        try:
            if event.node_id != self.source.node_id or event.cluster_id != clusters.Switch.id:
                return
            if not self.available(event.endpoint_id):
                return
            name = _EVENTS.get(event.event_id)
            if name not in self.buttons[event.endpoint_id].event_types:
                return
            payload = event.data if isinstance(event.data, dict) else {}
            attributes = {
                key: payload[key]
                for key in ("newPosition", "previousPosition")
                if type(payload.get(key)) is int
            }
            self._notify(event.endpoint_id, name, attributes)
        except Exception:
            self._log_failure()
