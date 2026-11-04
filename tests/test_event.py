"""Publish early events through real Home Assistant event entities."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from matter_server.common.models import EventType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.matter_button_events.const import DOMAIN
from tests.conftest import Endpoint
from tests.test_bridge import event


async def test_setup_real_entities_and_unload(hass, source):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Example remote",
        data={
            "device_id": source.device.id,
            "source_entry_id": source.entry.entry_id,
            "source_identifier": source.identifier,
        },
    )
    entry.add_to_hass(hass)
    # The fake source entry is already loaded. Avoid setting up a second,
    # networked official integration; use the real event platform and loader.
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=None):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entries) == 2
    assert all(item.device_id == source.device.id for item in entries)
    entity_id = next(item.entity_id for item in entries if item.unique_id.endswith(":1"))
    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes["event_types"] == ["initial_press", "short_release"]
    source.client.emit(EventType.NODE_EVENT, event())
    await hass.async_block_till_done()
    first = hass.states.get(entity_id)
    assert first.attributes["event_type"] == "initial_press"
    source.client.emit(EventType.NODE_EVENT, event())
    await hass.async_block_till_done()
    second = hass.states.get(entity_id)
    assert second.state != first.state
    source.state(ConfigEntryState.UNLOAD_IN_PROGRESS)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    source.state(ConfigEntryState.LOADED)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == second.state
    Endpoint(source.node, 3)
    source.client.emit(EventType.ENDPOINT_ADDED, {"node_id": 1, "endpoint_id": 3})
    await hass.async_block_till_done()
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not source.client.listeners
    source.client.disconnect.assert_not_called()
    assert dr.async_get(hass).async_get(source.device.id).config_entry_id == source.entry.entry_id
    assert await hass.config_entries.async_remove(entry.entry_id)
    assert dr.async_get(hass).async_get(source.device.id) is not None
