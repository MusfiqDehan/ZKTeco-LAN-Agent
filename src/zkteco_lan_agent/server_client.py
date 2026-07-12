from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from zkteco_lan_agent import __version__

log = logging.getLogger("zkteco_lan_agent.server")


@dataclass
class PendingCommand:
    id: int
    cmd: str


class ServerClient:
    def __init__(self, server_url: str, timeout: float = 15.0):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": f"zkteco-lan-agent/{__version__}"})

    def heartbeat(self, device_sn: str) -> bool:
        try:
            resp = self.session.get(
                f"{self.server_url}/iclock/cdata/",
                params={"SN": device_sn, "agent": __version__},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except requests.RequestException as exc:
            log.warning("Heartbeat failed SN=%s: %s", device_sn, exc)
            return False

    def push_cdata(self, device_sn: str, body: str, *, table: str) -> bool:
        try:
            resp = self.session.post(
                f"{self.server_url}/iclock/cdata/",
                params={"SN": device_sn, "table": table},
                data=body.encode("utf-8"),
                timeout=self.timeout,
            )
            log.info(
                "Push SN=%s table=%s status=%s body=%s",
                device_sn,
                table,
                resp.status_code,
                resp.text.strip()[:200],
            )
            return resp.status_code == 200
        except requests.RequestException as exc:
            log.error("Push failed SN=%s: %s", device_sn, exc)
            return False

    def get_request(self, device_sn: str) -> PendingCommand | None:
        try:
            resp = self.session.get(
                f"{self.server_url}/iclock/getrequest/",
                params={"SN": device_sn},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("getrequest failed SN=%s: %s", device_sn, exc)
            return None

        text = (resp.text or "").strip()
        if not text or text.upper().startswith("OK"):
            return None

        match = re.match(r"^C:(\d+):(.+)$", text, re.DOTALL)
        if not match:
            log.warning("Unrecognized getrequest response SN=%s: %s", device_sn, text[:200])
            return None
        return PendingCommand(id=int(match.group(1)), cmd=match.group(2).strip())

    def ack_command(self, device_sn: str, cmd_id: int, return_code: int = 0) -> bool:
        try:
            resp = self.session.post(
                f"{self.server_url}/iclock/devicecmd/",
                params={"SN": device_sn},
                data=f"ID={cmd_id}&Return={return_code}&CMD=DATA".encode("utf-8"),
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except requests.RequestException as exc:
            log.error("devicecmd ack failed SN=%s id=%s: %s", device_sn, cmd_id, exc)
            return False
