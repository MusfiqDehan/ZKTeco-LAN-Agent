from __future__ import annotations

import logging
import re
from typing import Any, Callable

from zkteco_lan_agent.attendance import (
    build_attlog_body,
    build_fp_enrolled_body,
    build_userinfo_body,
    format_attlog_line,
    normalize_card_number,
    resolve_pyzk_attendance_fields,
)

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


def _template_occupied(conn: Any, *, uid: int, fid: int) -> bool:
    for template in conn.get_templates() or []:
        if getattr(template, "uid", None) == uid and getattr(template, "fid", None) == fid:
            return True
    return False


def _clear_fingerprint_slot(conn: Any, *, uid: int, fid: int) -> bool:
    """Delete template for uid+fid. Use uid-only API — pyzk TCP user_id path is broken on Py3."""
    try:
        return bool(conn.delete_user_template(uid=uid, temp_id=fid))
    except Exception as exc:
        log.warning("ENROLL_FP: delete template uid=%s fid=%s failed: %s", uid, fid, exc)
        return False


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

    def _with_conn(self, fn: Callable[[Any], int], *, lock_device: bool = True) -> int:
        conn = None
        try:
            conn = self._connect()
            if lock_device:
                conn.disable_device()
            return fn(conn)
        finally:
            if conn is not None:
                if lock_device:
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
            user_id = str(pin)
            users = conn.get_users() or []
            if not any(
                str(getattr(u, "user_id", "")) == user_id or getattr(u, "uid", None) == uid
                for u in users
            ):
                log.error("ENROLL_FP: user PIN=%s not found on device; run USERINFO first", pin)
                return 1
            if _template_occupied(conn, uid=uid, fid=fid):
                log.info(
                    "ENROLL_FP: clearing existing template PIN=%s FID=%s before re-enroll",
                    pin,
                    fid,
                )
                if not _clear_fingerprint_slot(conn, uid=uid, fid=fid):
                    log.error(
                        "ENROLL_FP: fingerprint slot %s already used for PIN=%s and could not be cleared",
                        fid,
                        pin,
                    )
                    return 1
                if _template_occupied(conn, uid=uid, fid=fid):
                    log.error(
                        "ENROLL_FP: fingerprint slot %s still occupied for PIN=%s after delete",
                        fid,
                        pin,
                    )
                    return 1
            log.info("ENROLL_FP: starting enrollment PIN=%s FID=%s — scan finger on device", pin, fid)
            enrolled = False
            if hasattr(conn, "enroll_user"):
                try:
                    enrolled = bool(conn.enroll_user(uid=uid, temp_id=fid, user_id=user_id))
                except Exception as exc:
                    log.warning(
                        "ENROLL_FP: enroll_user raised for PIN=%s FID=%s: %s",
                        pin,
                        fid,
                        exc,
                    )
            elif hasattr(conn, "enroll_fingerprint"):
                enrolled = bool(conn.enroll_fingerprint(uid, fid))
            else:
                log.warning("Device connection has no enroll API; command not executed")
                return 1

            # pyzk often returns False on F18 even when the device saved the template.
            if not enrolled:
                enrolled = _template_occupied(conn, uid=uid, fid=fid)
                if enrolled:
                    log.info(
                        "ENROLL_FP: template detected on device for PIN=%s FID=%s after enroll",
                        pin,
                        fid,
                    )

            if not enrolled:
                log.error(
                    "ENROLL_FP: no fingerprint captured for PIN=%s FID=%s (timeout or cancelled)",
                    pin,
                    fid,
                )
                return 1

            if not self._push_cdata(build_fp_enrolled_body(pin), "FP"):
                log.warning(
                    "ENROLL_FP: FP push failed for PIN=%s; Fitssort may still complete via devicecmd ack",
                    pin,
                )

            log.info("ENROLL_FP: enrollment finished PIN=%s FID=%s", pin, fid)
            return 0

        # Device must stay enabled so the fingerprint reader accepts scans.
        return self._with_conn(_run, lock_device=False)

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
                status, verify, in_out = resolve_pyzk_attendance_fields(att)
                lines.append(
                    format_attlog_line(
                        att.user_id,
                        ts,
                        status=status,
                        verify=verify,
                        in_out=in_out,
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
                        "card": normalize_card_number(getattr(user, "card", None)),
                    }
                )
            if rows:
                self._push_cdata(build_userinfo_body(rows), "USERINFO")
            return 0

        return self._with_conn(_run)
