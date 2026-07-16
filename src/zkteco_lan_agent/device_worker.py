from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from zk import ZK

from zkteco_lan_agent.attendance import build_attlog_body, build_userinfo_body, format_attlog_line, normalize_card_number
from zkteco_lan_agent.command_executor import CommandExecutor
from zkteco_lan_agent.config import AgentConfig, DeviceConfig
from zkteco_lan_agent.server_client import ServerClient
from zkteco_lan_agent.state import DeviceState

log = logging.getLogger("zkteco_lan_agent.worker")


class DeviceWorker:
    def __init__(self, agent: AgentConfig, device: DeviceConfig, server: ServerClient):
        self.agent = agent
        self.device = device
        self.server = server
        self.state = DeviceState(agent.state_dir, device.device_sn)
        self._last_heartbeat = 0.0
        self._last_command_poll = 0.0
        self._last_userinfo_sync = 0.0

    def _connect(self) -> Any:
        zk = ZK(
            self.device.device_ip,
            port=self.device.device_port,
            timeout=10,
            password=self.device.comm_password,
            force_udp=False,
        )
        return zk.connect()

    def poll_attendance(self) -> None:
        conn = None
        try:
            conn = self._connect()
            log.info(
                "Connected to %s (%s:%d)",
                self.device.device_sn,
                self.device.device_ip,
                self.device.device_port,
            )
            conn.disable_device()
            last_poll = self.state.load_last_poll()
            logs = conn.get_attendance() or []
            log.info("SN=%s has %d attendance records", self.device.device_sn, len(logs))

            new_logs = []
            for att in logs:
                ts: datetime = att.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if last_poll and ts <= last_poll:
                    continue
                new_logs.append(att)

            if new_logs:
                lines: list[str] = []
                newest: datetime | None = None
                for att in new_logs:
                    ts = att.timestamp
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    # pyzk: status often holds punch type; punch may hold verify on some firmwares
                    verify = getattr(att, "punch", None)
                    status = int(getattr(att, "status", 0) or 0)
                    # Prefer explicit verify attribute if present
                    if hasattr(att, "verify") and getattr(att, "verify") is not None:
                        verify = getattr(att, "verify")
                    lines.append(
                        format_attlog_line(
                            att.user_id,
                            ts,
                            status=status,
                            verify=int(verify) if verify is not None else None,
                            in_out=int(getattr(att, "punch", 0) or 0) if verify is None else 0,
                        )
                    )
                    if newest is None or ts > newest:
                        newest = ts
                body = build_attlog_body(lines)
                if self.server.push_cdata(self.device.device_sn, body, table="ATTLOG") and newest:
                    self.state.save_last_poll(newest)
            else:
                log.info("SN=%s no new records", self.device.device_sn)
                self._maybe_heartbeat(force=True)

            conn.enable_device()
        except Exception as exc:
            log.error("Device poll error SN=%s: %s", self.device.device_sn, exc)
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def poll_commands(self) -> None:
        pending = self.server.get_request(self.device.device_sn)
        if not pending:
            return

        def push(body: str, table: str) -> bool:
            return self.server.push_cdata(self.device.device_sn, body, table=table)

        executor = CommandExecutor(self._connect, push)
        return_code = executor.execute(pending.cmd)
        self.server.ack_command(self.device.device_sn, pending.id, return_code)

    def sync_userinfo(self) -> None:
        """Pull device users (including card numbers) and push USERINFO to Fitssort."""
        conn = None
        try:
            conn = self._connect()
            users = conn.get_users() or []
            rows = []
            for user in users:
                rows.append(
                    {
                        "pin": getattr(user, "user_id", None) or getattr(user, "uid", ""),
                        "name": getattr(user, "name", "") or "",
                        "card": normalize_card_number(getattr(user, "card", None)),
                    }
                )
            if not rows:
                log.info("SN=%s userinfo sync: no users on device", self.device.device_sn)
                return
            body = build_userinfo_body(rows)
            if self.server.push_cdata(self.device.device_sn, body, table="USERINFO"):
                with_cards = sum(1 for row in rows if row["card"])
                log.info(
                    "SN=%s userinfo sync pushed %d users (%d with card)",
                    self.device.device_sn,
                    len(rows),
                    with_cards,
                )
        except Exception as exc:
            log.error("Userinfo sync error SN=%s: %s", self.device.device_sn, exc)
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def _maybe_heartbeat(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_heartbeat >= self.agent.heartbeat_interval_seconds:
            if self.server.heartbeat(self.device.device_sn):
                self._last_heartbeat = now

    def tick(self) -> None:
        self.poll_attendance()
        now = time.monotonic()
        if now - self._last_command_poll >= self.agent.command_poll_interval_seconds:
            self.poll_commands()
            self._last_command_poll = now
        interval = max(0, int(self.agent.userinfo_sync_interval_seconds))
        if interval == 0 or now - self._last_userinfo_sync >= interval:
            self.sync_userinfo()
            self._last_userinfo_sync = now
        self._maybe_heartbeat()
