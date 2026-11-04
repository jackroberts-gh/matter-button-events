"""Verify discovery with the pinned Matter library's real endpoint model."""

from datetime import UTC, datetime

from matter_server.client.models.device_types import GenericSwitch
from matter_server.client.models.node import MatterNode
from matter_server.common.models import MatterNodeData

from custom_components.matter_button_events.bridge import resolve_source


async def test_real_matter_node_and_global_event_list(hass, source):
    now = datetime.now(UTC)
    attributes = {
        "0/29/0": [{"deviceType": 22, "revision": 1}],
        "0/29/3": [1, 2],
        "1/29/0": [{"deviceType": GenericSwitch.device_type, "revision": 1}],
        "1/59/1": 0,
        "1/59/65532": 30,
        "1/59/65530": [1, 2, 3, 4, 5, 6],
        "2/29/0": [{"deviceType": GenericSwitch.device_type, "revision": 1}],
        "2/59/1": 0,
        "2/59/65532": 2,
    }
    node = MatterNode(
        MatterNodeData(
            node_id=1,
            date_commissioned=now,
            last_interview=now,
            interview_version=6,
            available=True,
            attributes=attributes,
        )
    )
    source.client.nodes = [node]
    resolved = resolve_source(hass, source.device.id)
    assert resolved.buttons[1].event_types == ("initial_press", "short_release")
    assert resolved.buttons[2].event_types == ("initial_press",)
