from __future__ import annotations

import logging
import re
from typing import Any, Callable

from zkteco_lan_agent.attendance import build_attlog_body, build_userinfo_body, format_attlog_line

log = logging.getLogger("zkteco_lan_agent.commands")


def parse_userinfo_fields(cmd: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    # Normalize "DATA UPDATE USERINFO PIN=..." so PIN is its own token
    normalized = re.sub(r"(USERINFO)\s+", r"\1\t", cmd, count=1, flags=re.IGNORECASE)
    for part in re.split(r"[\t\n]", normalized):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        # Drop leading command words glued to the key
        if " " in key:
            key = key.split()[-1]
        fields[key] = value.strip()
    return fields


class CommandExecutor:
    """Map ADMS command strings to pyzk device operations."""

    def __init__(self, connect_fn: Callable[[], Any], push_cdata: Callable[[str, str], bool]):
        self._connect = connect_fn
        self._push_cdata = push_cdata

    def execute(self, cmd: str) -> int:
        """Return ADMS Return code (0 = success)."""
        upper = cmd.upper()
        try:
            if "UPDATE USERINFO" in upper or upper.startswith("DATA UPDATE USERINFO"):
                return self._exec_userinfo(cmd)
            if upper.startswith("ENROLL_FP"):
                return self._exec_enroll_fp(cmd)
            if "QUERY ATTLOG" in upper:
                return self._exec_query_attlog(cmd)
            if "QUERY USERINFO" in upper:
                return self._exec_query_userinfo()
            log.warning("Unsupported command: %s", cmd[:120])
            return 1
        except Exception as exc:
            log.exception("Command execution failed: %s", exc)
            return 1

    def _with_conn(self, fn: Callable[[Any], int]) -> int:
        conn = None
        try:
            conn = self._connect()
            conn.disable_device()
            return fn(conn)
        finally:
            if conn is not None:
                try:
                    conn.enable_device()
                except Exception:
                    pass
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def _exec_userinfo(self, cmd: str) -> int:
        fields = parse_userinfo_fields(cmd)
        pin = fields.get("PIN") or fields.get("Pin") or ""
        if not pin:
            return 1
        name = fields.get("Name") or ""
        card_raw = fields.get("Card") or ""

        def _run(conn: Any) -> int:
            uid = int(pin)
            kwargs: dict[str, Any] = {
                "uid": uid,
                "name": name,
                "privilege": 0,
                "password": "",
                "group_id": "",
                "user_id": str(pin),
            }
            # pyzk set_user does int(card); empty Card= from ADMS must become 0
            card: int | str = 0
            if card_raw.strip():
                card = int(card_raw) if card_raw.strip().isdigit() else card_raw
            try:
                conn.set_user(card=card, **kwargs)
            except TypeError:
                conn.set_user(**kwargs)
                if card and hasattr(conn, "set_user"):
                    # Best-effort second call with positional card if available
                    try:
                        conn.set_user(uid, name, 0, "", card, "", str(pin))
                    except Exception:
                        log.warning("Could not set card=%s for pin=%s", card, pin)
            return 0

        return self._with_conn(_run)

    def _exec_enroll_fp(self, cmd: str) -> int:
        fields = parse_userinfo_fields(cmd)
        pin = fields.get("PIN") or ""
        fid = int(fields.get("FID") or 0)
        if not pin:
            return 1

        def _run(conn: Any) -> int:
            uid = int(pin)
            # pyzk enroll_user / enroll fingerprint APIs differ by firmware
            if hasattr(conn, "enroll_user"):
                conn.enroll_user(uid)
                return 0
            if hasattr(conn, "enroll_fingerprint"):
                conn.enroll_fingerprint(uid, fid)
                return 0
            log.warning("Device connection has no enroll API; command not executed")
            return 1

        return self._with_conn(_run)

    def _exec_query_attlog(self, cmd: str) -> int:
        fields = parse_userinfo_fields(cmd)
        start = fields.get("StartTime")

        def _run(conn: Any) -> int:
            logs = conn.get_attendance() or []
            lines: list[str] = []
            for att in logs:
                ts = att.timestamp
                if start and ts.strftime("%Y-%m-%d %H:%M:%S") < start:
                    continue
                verify = getattr(att, "punch", None)
                if verify is None:
                    verify = getattr(att, "status", None)
                lines.append(
                    format_attlog_line(
                        att.user_id,
                        ts,
                        status=int(getattr(att, "status", 0) or 0),
                        verify=int(verify) if verify is not None else None,
                        in_out=int(getattr(att, "punch", 0) or 0),
                    )
                )
            if lines:
                self._push_cdata(build_attlog_body(lines), "ATTLOG")
            return 0

        return self._with_conn(_run)

    def _exec_query_userinfo(self) -> int:
        def _run(conn: Any) -> int:
            users = conn.get_users() or []
            rows = []
            for user in users:
                rows.append(
                    {
                        "pin": getattr(user, "user_id", None) or getattr(user, "uid", ""),
                        "name": getattr(user, "name", "") or "",
                        "card": getattr(user, "card", "") or "",
                    }
                )
            if rows:
                self._push_cdata(build_userinfo_body(rows), "USERINFO")
            return 0

        return self._with_conn(_run)
