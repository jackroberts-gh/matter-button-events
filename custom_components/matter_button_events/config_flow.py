"""Select an existing Matter device; discover its buttons automatically."""

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .bridge import SourceError, resolve_source
from .const import CONF_DEVICE_ID, CONF_SOURCE_ENTRY_ID, CONF_SOURCE_IDENTIFIER, DOMAIN


class MatterButtonEventsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per selected device, without numeric IDs in the UI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                device_id = user_input[CONF_DEVICE_ID]
                source = resolve_source(self.hass, device_id)
            except SourceError as err:
                errors["base"] = err.code
            else:
                await self.async_set_unique_id(f"{source.entry.entry_id}:{source.identifier}")
                self._abort_if_unique_id_configured()
                device = dr.async_get(self.hass).async_get(device_id)
                return self.async_create_entry(
                    title=device.name_by_user or device.name or "Matter buttons",
                    data={
                        CONF_DEVICE_ID: device_id,
                        CONF_SOURCE_ENTRY_ID: source.entry.entry_id,
                        CONF_SOURCE_IDENTIFIER: source.identifier,
                    },
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_DEVICE_ID): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(filter=[{"integration": "matter"}])
                    ),
                }
            ),
        )
