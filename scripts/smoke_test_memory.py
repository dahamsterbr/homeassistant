"""Offline smoke test for SQLite memory + adapter features (no HA required)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "local_home_ai" / "rootfs"
sys.path.insert(0, str(ROOT))

from app.memory import MemoryStore  # noqa: E402
from app.plugins import get_adapter  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "t.db")
        w = store.nudge_weight("keuken", "mmwave:binary_sensor.x", 1.0, active=True, occupied=True)
        assert w > 1.0
        store.add_episode(
            room="keuken",
            occupied=True,
            confidence=0.8,
            person="person.bjorn_reints",
            features={"mmwave:binary_sensor.x": 1.0},
            summary="keuken occupied by bjorn",
        )
        assert store.recent_summaries("keuken")
        assert store.stats()["episodes"] == 1
        store.close()

    adapter = get_adapter("mmwave")
    feats = adapter.features("binary_sensor.mmwave_keuken_presence", {"state": "on"})
    assert feats["mmwave:binary_sensor.mmwave_keuken_presence"] == 1.0
    print("smoke_test_memory: OK")


if __name__ == "__main__":
    main()
