from __future__ import annotations

from datetime import datetime
from pathlib import Path


class DeviceState:
    def __init__(self, state_dir: str | Path, device_sn: str):
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in device_sn)
        self._path = self._dir / f"{safe}_last_poll.txt"

    def load_last_poll(self) -> datetime | None:
        if not self._path.exists():
            return None
        raw = self._path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def save_last_poll(self, dt: datetime) -> None:
        self._path.write_text(dt.isoformat(), encoding="utf-8")
