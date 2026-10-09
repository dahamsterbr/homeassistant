"""Future BLE / ESPresense adapter hook.

Wire room sensors with adapter: ble in add-on options when ESPresense
(or similar) entities exist. Distance/RSSI graded features can be added
here without changing the fusion engine.
"""

from __future__ import annotations

from typing import Any

from .base import FutureBleAdapter

# Re-export for explicit plugin imports / discovery later.
BleAdapter = FutureBleAdapter


def describe() -> dict[str, Any]:
    return {
        "name": "ble",
        "status": "stub",
        "notes": "Map ESPresense room devices with adapter 'ble' when ready.",
    }
