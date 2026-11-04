"""Expose early events alongside, rather than instead of, official Matter."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .bridge import MatterEventBridge, SourceError, resolve_source
from .const import CONF_DEVICE_ID, CONF_SOURCE_ENTRY_ID, CONF_SOURCE_IDENTIFIER, DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.EVENT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Resolve the selected source and start only after entity setup."""
    try:
        source = resolve_source(
            hass,
            entry.data[CONF_DEVICE_ID],
            entry.data[CONF_SOURCE_ENTRY_ID],
            entry.data[CONF_SOURCE_IDENTIFIER],
        )
    except SourceError as err:
        raise ConfigEntryNotReady(f"Matter source unavailable: {err.code}") from err
    bridge = MatterEventBridge(hass, entry.data, source)
    entry.runtime_data = bridge
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        bridge.start()
    except Exception:
        bridge.stop()
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload our entities and callbacks without controlling the source."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.stop()
        return True
    return False
