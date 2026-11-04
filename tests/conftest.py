"""Real HA fixtures with a deterministic, non-networked Matter event source."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from chip.clusters import Objects as clusters
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from matter_server.client.models.device_types import GenericSwitch
from matter_server.common.errors import NodeNotExists
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytest_plugins = "pytest_homeassistant_custom_component"


class Client:
    """Only the existing client's local subscription interface is needed."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.server_info = SimpleNamespace(compressed_fabric_id=100)
        self.listeners = []
        self.disconnect = Mock(side_effect=AssertionError("must not disconnect Matter"))

    def get_nodes(self):
        return self.nodes

    def get_node(self, node_id):
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise NodeNotExists("Node missing")

    def subscribe_events(self, callback, event_filter=None, node_filter=None):
        record = (callback, event_filter, node_filter)
        self.listeners.append(record)
        return lambda: self.listeners.remove(record)

    def emit(self, event_type, data):
        for listener, event_filter, node_filter in tuple(self.listeners):
            if event_filter != event_type:
                continue
            node_id = (
                data.get("node_id")
                if isinstance(data, dict)
                else (data if isinstance(data, int) else getattr(data, "node_id", None))
            )
            if node_filter is not None and node_filter != node_id:
                continue
            listener(event_type, data)


@dataclass
class Node:
    node_id: int = 1
    available: bool = True
    endpoints: dict = field(default_factory=dict)
    parents: dict = field(default_factory=dict)
    node_data: object = field(default_factory=lambda: SimpleNamespace(attributes={}))

    def get_compose_parent(self, endpoint_id):
        return self.parents.get(endpoint_id)


class Endpoint:
    def __init__(self, node, endpoint_id, *, feature=30, bridged=False, events=None):
        self.node = node
        self.endpoint_id = endpoint_id
        self.is_bridged_device = bridged
        self.device_types = [GenericSwitch]
        self.values = {
            clusters.Switch.Attributes.FeatureMap: feature,
        }
        if events is not None:
            node.node_data.attributes[f"{endpoint_id}/59/65530"] = events
        node.endpoints[endpoint_id] = self

    def get_attribute_value(self, cluster, attribute):
        return self.values.get(attribute)


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """Allow loading this checkout rather than installed custom components."""


@pytest.fixture
def source(hass):
    """Create a real source config entry and device registry association."""
    entry = MockConfigEntry(domain="matter", title="Matter", data={"url": "ws://example/ws"})
    entry.add_to_hass(hass)
    node = Node()
    Endpoint(node, 1)
    Endpoint(node, 2)
    client = Client([node])
    entry.runtime_data = SimpleNamespace(adapter=SimpleNamespace(matter_client=client))
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    identifier = "deviceid_0000000000000064-0000000000000001-MatterNodeDevice"
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("matter", identifier)},
        name="Example remote",
    )

    @callback
    def state(value):
        entry._async_set_state(hass, value, None)

    yield SimpleNamespace(
        entry=entry, node=node, client=client, device=device, identifier=identifier, state=state
    )
    entry._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
