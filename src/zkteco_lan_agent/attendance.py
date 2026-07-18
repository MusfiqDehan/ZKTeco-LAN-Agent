from __future__ import annotations

from datetime import datetime, timezone


def format_attlog_line(
    user_id: str | int,
    ts: datetime,
    *,
    status: int = 0,
    verify: int | None = None,
    in_out: int = 0,
    work_code: int = 0,
) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    verify_val = 1 if verify is None else int(verify)
    return f"{user_id}\t{time_str}\t{status}\t{verify_val}\t{in_out}\t{work_code}"


def build_attlog_body(lines: list[str]) -> str:
    return "TABLE=ATTLOG\n" + "\n".join(lines)


def normalize_card_number(value) -> str:
    """Coerce pyzk card values (int/str) into a USERINFO-safe card string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return "" if value == 0 else str(value)
    text = str(value).strip()
    if text in {"", "0", "None", "none"}:
        return ""
    return text


def build_userinfo_body(rows: list[dict]) -> str:
    """Build USERINFO push body from dicts with pin, name, card keys."""
    lines = ["TABLE=USERINFO"]
    for row in rows:
        pin = row.get("pin") or row.get("uid") or ""
        name = str(row.get("name") or "").replace("\t", " ").strip()[:40]
        card = normalize_card_number(row.get("card"))
        lines.append(f"PIN={pin}\tName={name}\tCard={card}")
    return "\n".join(lines)


def build_fp_enrolled_body(pin: str) -> str:
    """Notify Fitssort that a fingerprint template exists for this PIN."""
    return f"TABLE=FP\nPIN={pin}"


VERIFY_PASSWORD = 0
VERIFY_FINGERPRINT = 1
VERIFY_CARD = 2
VERIFY_PIN = 3
VERIFY_FACE = 4

# ZKTeco verify-type codes commonly returned in attendance.status (pyzk).
_KNOWN_VERIFY_TYPES = frozenset(range(0, 16))


def entry_method_for_verify(verify: int | None) -> str:
    mapping = {
        VERIFY_PASSWORD: "password",
        VERIFY_FINGERPRINT: "fingerprint",
        VERIFY_CARD: "card",
        VERIFY_PIN: "pin",
        VERIFY_FACE: "face",
    }
    if verify is None:
        return "fingerprint"
    return mapping.get(int(verify), "fingerprint")


def resolve_pyzk_attendance_fields(att: object) -> tuple[int, int | None, int]:
    """Map a pyzk Attendance object to (status, verify, in_out) for ATTLOG.

    On most ZKTeco firmwares (including F18 via pyzk):
    - ``status`` = verification method (0 password, 1 fingerprint, 2 card, …)
    - ``punch`` = check-in / check-out style flag

    Older agent code used ``punch`` as verify, so card punches were pushed as
    verify=0/1 and always stored as Fingerprint. Prefer an explicit ``verify``
    attribute when present; otherwise use status as verify and punch as in/out.
    """
    explicit_verify = getattr(att, "verify", None)
    status_raw = getattr(att, "status", None)
    punch_raw = getattr(att, "punch", None)

    status_i = int(status_raw) if status_raw is not None else 0
    punch_i = int(punch_raw) if punch_raw is not None else 0

    if explicit_verify is not None:
        return status_i, int(explicit_verify), punch_i

    # Standard pyzk convention: status is the verification method.
    if status_i in _KNOWN_VERIFY_TYPES:
        return status_i, status_i, punch_i

    return status_i, None, punch_i
