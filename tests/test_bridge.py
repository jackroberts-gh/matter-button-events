"""Exercise filtering, source identity and lifecycle through the real bridge."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from chip.clusters import Objects as clusters
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from matter_server.common.models import EventType

from custom_components.matter_button_events.bridge import (
    MatterEventBridge,
    SourceError,
    resolve_source,
)
from custom_components.matter_button_events.const import (
    CONF_DEVICE_ID,
    CONF_SOURCE_ENTRY_ID,
    CONF_SOURCE_IDENTIFIER,
)
from tests.conftest import Client, Endpoint


def bridge_for(hass, source):
    resolved = resolve_source(hass, source.device.id)
    data = {
        CONF_DEVICE_ID: source.device.id,
        CONF_SOURCE_ENTRY_ID: source.entry.entry_id,
        CONF_SOURCE_IDENTIFIER: source.identifier,
    }
    return MatterEventBridge(hass, data, resolved)


def listen_button(bridge, endpoint, listener):
    return bridge.listen(
        lambda received_endpoint, name, attrs: (
            listener(name, attrs) if received_endpoint == endpoint else None
        )
    )


def event(**changes):
    values = dict(node_id=1, endpoint_id=1, cluster_id=59, event_id=1, data={"newPosition": 1})
    return SimpleNamespace(**(values | changes))


async def test_forward_only_selected_early_events(hass, source):
    bridge = bridge_for(hass, source)
    received = Mock()
    listen_button(bridge, 1, received)
    bridge.start()
    for ignored in (
        event(node_id=2),
        event(endpoint_id=3),
        event(cluster_id=257),
        event(event_id=2),
        event(event_id=6),
    ):
        source.client.emit(EventType.NODE_EVENT, ignored)
    received.assert_not_called()
    source.client.emit(EventType.NODE_EVENT, event())
    source.client.emit(EventType.NODE_EVENT, event())
    source.client.emit(
        EventType.NODE_EVENT, event(event_id=3, data={"previousPosition": 1, "secret": "ignored"})
    )
    assert received.call_count == 3
    assert received.call_args.args == ("short_release", {"previousPosition": 1})
    bridge.stop()


async def test_unsubscribe_reload_and_recovery(hass, source):
    bridge = bridge_for(hass, source)
    received = Mock()
    listen_button(bridge, 1, received)
    bridge.start()
    count = len(source.client.listeners)
    bridge.start()
    assert len(source.client.listeners) == count
    assert bridge.available(1)
    old = source.client
    source.state(ConfigEntryState.UNLOAD_IN_PROGRESS)
    assert old.listeners == []
    assert not bridge.available(1)
    new = Client([source.node])
    source.entry.runtime_data.adapter.matter_client = new
    source.state(ConfigEntryState.LOADED)
    assert len(new.listeners) == count
    new.emit(EventType.NODE_EVENT, event())
    received.assert_called_once()
    bridge.stop()
    bridge.stop()
    assert not new.listeners
    source.state(ConfigEntryState.LOADED)
    assert not new.listeners
    old.disconnect.assert_not_called()
    new.disconnect.assert_not_called()


async def test_availability_and_endpoint_return(hass, source):
    bridge = bridge_for(hass, source)
    bridge.start()
    source.node.available = False
    source.client.emit(EventType.NODE_UPDATED, source.node)
    assert not bridge.available(1)
    source.node.available = True
    original = source.node.endpoints.copy()
    source.node.endpoints.clear()
    source.client.emit(EventType.ENDPOINT_REMOVED, {"node_id": 1, "endpoint_id": 1})
    await hass.async_block_till_done()
    assert not bridge.available(1)
    source.node.endpoints.update(original)
    source.client.emit(EventType.ENDPOINT_ADDED, {"node_id": 1, "endpoint_id": 1})
    assert bridge.available(1)
    assert len(bridge.buttons) == 2
    bridge.stop()


async def test_refresh_reads_only_selected_node(hass, source):
    bridge = bridge_for(hass, source)
    source.client.get_nodes = Mock(side_effect=AssertionError("must not scan all devices"))
    bridge.start()
    source.client.emit(EventType.NODE_UPDATED, source.node)
    assert bridge.available(1)
    source.client.get_nodes.assert_not_called()
    bridge.stop()


async def test_removal_notification_precedes_cache_cleanup(hass, source):
    bridge = bridge_for(hass, source)
    bridge.start()
    # Match the actual client's order: notify first, then remove cached data.
    source.client.emit(EventType.NODE_REMOVED, source.node.node_id)
    source.client.nodes.clear()
    await hass.async_block_till_done()
    assert not bridge.available(1)
    source.client.nodes.append(source.node)
    source.client.emit(EventType.NODE_ADDED, source.node)
    assert bridge.available(1)
    # A queued update must not subscribe again after our own unload.
    source.client.emit(EventType.ENDPOINT_REMOVED, {"node_id": 1, "endpoint_id": 1})
    bridge.stop()
    await hass.async_block_till_done()
    assert not source.client.listeners


@pytest.mark.parametrize(
    "feature,event_list,expected",
    [
        (2, None, ("initial_press",)),
        (6, None, ("initial_press", "short_release")),
        (30, [3], ("short_release",)),
    ],
)
async def test_features_and_event_list(hass, source, feature, event_list, expected):
    for endpoint in source.node.endpoints.values():
        endpoint.values[clusters.Switch.Attributes.FeatureMap] = feature
        source.node.node_data.attributes[f"{endpoint.endpoint_id}/59/65530"] = event_list
    resolved = resolve_source(hass, source.device.id)
    assert resolved.buttons[1].event_types == expected


async def test_no_supported_buttons(hass, source):
    for endpoint in source.node.endpoints.values():
        endpoint.values[clusters.Switch.Attributes.FeatureMap] = 1
    with pytest.raises(SourceError, match="no_supported_buttons"):
        resolve_source(hass, source.device.id)


async def test_bridged_and_composed_siblings_excluded(hass, source):
    source.node.endpoints.clear()
    parent = Endpoint(source.node, 3, bridged=True)
    Endpoint(source.node, 4, bridged=True)
    Endpoint(source.node, 5, bridged=True)
    source.node.parents[4] = parent
    identifier = "deviceid_0000000000000064-0000000000000001-3"
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry.entry_id, identifiers={("matter", identifier)}, name="Child"
    )
    resolved = resolve_source(hass, device.id)
    assert set(resolved.buttons) == {3, 4}
    parent.values[clusters.BridgedDeviceBasicInformation.Attributes.Reachable] = False
    assert not resolve_source(hass, device.id).buttons[4].available
    # The node-level device must not capture any of these bridged endpoints.
    with pytest.raises(SourceError, match="device_not_found"):
        resolve_source(hass, source.device.id)


async def test_missing_not_ready_and_identity_change(hass, source):
    with pytest.raises(SourceError, match="device_not_found"):
        resolve_source(hass, "missing")
    source.state(ConfigEntryState.NOT_LOADED)
    with pytest.raises(SourceError, match="source_not_ready"):
        resolve_source(hass, source.device.id)
    source.state(ConfigEntryState.LOADED)
    with pytest.raises(SourceError, match="device_not_found"):
        resolve_source(hass, source.device.id, source.entry.entry_id, "old-identity")


async def test_bad_callback_does_not_block_other_listener(hass, source, caplog):
    bridge = bridge_for(hass, source)
    broken = Mock(side_effect=ValueError("bad subscriber"))
    healthy = Mock()
    listen_button(bridge, 1, broken)
    listen_button(bridge, 1, healthy)
    bridge.start()
    source.client.emit(EventType.NODE_EVENT, event())
    source.client.emit(EventType.NODE_EVENT, event())
    assert healthy.call_count == 2
    assert caplog.text.count("Matter Button Events callback failed") == 1
    source.client.emit(EventType.NODE_EVENT, object())
    assert healthy.call_count == 2
    bridge.stop()
