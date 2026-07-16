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


VERIFY_FINGERPRINT = 1
VERIFY_CARD = 2
VERIFY_PASSWORD = 0
VERIFY_PIN = 3
VERIFY_FACE = 4


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
