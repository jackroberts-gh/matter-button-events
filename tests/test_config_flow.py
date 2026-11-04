"""Validate selection and duplicate handling using Home Assistant flows."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.matter_button_events.const import DOMAIN


async def test_select_device_and_duplicate(hass, source):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.matter_button_events.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": source.device.id}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["source_entry_id"] == source.entry.entry_id
    assert result["title"] == "Example remote"
    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={"device_id": source.device.id}
    )
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "already_configured"


async def test_invalid_selection_stays_in_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={"device_id": "missing"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "device_not_found"}
