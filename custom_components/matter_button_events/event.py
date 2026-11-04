"""Additional event entities attached to the existing selected device."""

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .bridge import MatterEventBridge
from .const import CONF_DEVICE_ID, CONF_SOURCE_ENTRY_ID


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add discovered endpoints, including endpoints discovered after reload."""
    bridge: MatterEventBridge = entry.runtime_data
    known: set[int] = set()

    @callback
    def discover(endpoint: int | None = None, *_args) -> None:
        if endpoint is not None:
            return
        entities = []
        for endpoint_id in bridge.buttons:
            if endpoint_id not in known:
                known.add(endpoint_id)
                entities.append(MatterButtonEvent(bridge, endpoint_id))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(bridge.listen(discover))
    discover()


class MatterButtonEvent(EventEntity):
    """A button event stream containing no device-control behavior."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = EventDeviceClass.BUTTON

    def __init__(self, bridge: MatterEventBridge, endpoint_id: int) -> None:
        self.bridge = bridge
        self.endpoint_id = endpoint_id
        self._attr_name = f"Early button {endpoint_id}"
        self._attr_unique_id = (
            f"{bridge.data[CONF_SOURCE_ENTRY_ID]}:{bridge.source.identifier}:{endpoint_id}"
        )
        # HA devices belong to one config entry. Passing the existing entry
        # directly attaches our entities without registering a duplicate device
        # or adding our config entry to the source device's ownership.
        self.device_entry = dr.async_get(bridge.hass).async_get(bridge.data[CONF_DEVICE_ID])

    @property
    def event_types(self) -> list[str]:
        button = self.bridge.buttons.get(self.endpoint_id)
        return list(button.event_types) if button is not None else []

    @property
    def available(self) -> bool:
        return self.bridge.available(self.endpoint_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.bridge.listen(self._receive))

    @callback
    def _receive(self, endpoint: int | None, name: str | None, attributes: dict) -> None:
        if endpoint is None:
            self.async_write_ha_state()
        elif endpoint == self.endpoint_id and name is not None:
            self._trigger_event(name, attributes)
            self.async_write_ha_state()
