from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeviceConfig:
    name: str
    device_ip: str
    device_sn: str
    device_port: int = 4370
    comm_password: int = 0
    timezone: str = "Asia/Dhaka"


@dataclass
class AgentConfig:
    server_url: str
    devices: list[DeviceConfig] = field(default_factory=list)
    poll_interval_seconds: int = 30
    command_poll_interval_seconds: int = 10
    heartbeat_interval_seconds: int = 60
    userinfo_sync_interval_seconds: int = 300
    state_dir: str = "/tmp/zkteco_lan_agent"


class ConfigError(ValueError):
    pass


def load_config(path: str | Path) -> AgentConfig:
    raw_path = Path(path)
    if not raw_path.exists():
        raise ConfigError(f"Config file not found: {raw_path}")

    data = yaml.safe_load(raw_path.read_text(encoding="utf-8")) or {}
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> AgentConfig:
    server_url = str(data.get("server_url") or "").rstrip("/")
    if not server_url:
        raise ConfigError("server_url is required")

    devices_raw = data.get("devices") or []
    if not isinstance(devices_raw, list) or not devices_raw:
        raise ConfigError("devices must be a non-empty list")

    devices: list[DeviceConfig] = []
    for idx, item in enumerate(devices_raw):
        if not isinstance(item, dict):
            raise ConfigError(f"devices[{idx}] must be a mapping")
        sn = str(item.get("device_sn") or "").strip()
        if not sn:
            raise ConfigError(f"devices[{idx}].device_sn is required")
        ip = str(item.get("device_ip") or "").strip()
        if not ip:
            raise ConfigError(f"devices[{idx}].device_ip is required")
        devices.append(
            DeviceConfig(
                name=str(item.get("name") or sn),
                device_ip=ip,
                device_sn=sn,
                device_port=int(item.get("device_port") or 4370),
                comm_password=int(item.get("comm_password") or 0),
                timezone=str(item.get("timezone") or "Asia/Dhaka"),
            )
        )

    return AgentConfig(
        server_url=server_url,
        devices=devices,
        poll_interval_seconds=int(data.get("poll_interval_seconds") or 30),
        command_poll_interval_seconds=int(data.get("command_poll_interval_seconds") or 10),
        heartbeat_interval_seconds=int(data.get("heartbeat_interval_seconds") or 60),
        userinfo_sync_interval_seconds=int(data.get("userinfo_sync_interval_seconds") or 300),
        state_dir=str(data.get("state_dir") or "/tmp/zkteco_lan_agent"),
    )
