from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from zkteco_lan_agent.attendance import (
    build_attlog_body,
    entry_method_for_verify,
    format_attlog_line,
)
from zkteco_lan_agent.config import ConfigError, parse_config
from zkteco_lan_agent.command_executor import parse_userinfo_fields


class ConfigTests(unittest.TestCase):
    def test_parse_multi_device(self):
        cfg = parse_config(
            {
                "server_url": "http://gym.fitssort.com",
                "devices": [
                    {"name": "A", "device_ip": "192.168.1.1", "device_sn": "SN1"},
                    {"device_ip": "192.168.1.2", "device_sn": "SN2"},
                ],
            }
        )
        self.assertEqual(len(cfg.devices), 2)
        self.assertEqual(cfg.devices[1].name, "SN2")

    def test_missing_sn_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "server_url": "http://x",
                    "devices": [{"device_ip": "1.2.3.4"}],
                }
            )

    def test_empty_devices_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"server_url": "http://x", "devices": []})


class AttlogFormatTests(unittest.TestCase):
    def test_full_line_includes_verify(self):
        ts = datetime(2026, 1, 11, 10, 12, 30, tzinfo=timezone.utc)
        line = format_attlog_line("1001", ts, status=0, verify=2, in_out=0, work_code=0)
        self.assertEqual(line, "1001\t2026-01-11 10:12:30\t0\t2\t0\t0")

    def test_default_verify_fingerprint(self):
        ts = datetime(2026, 1, 11, 10, 12, 30, tzinfo=timezone.utc)
        line = format_attlog_line("1001", ts)
        parts = line.split("\t")
        self.assertEqual(parts[3], "1")

    def test_body_prefix(self):
        body = build_attlog_body(["1001\t2026-01-11 10:12:30\t0\t1\t0\t0"])
        self.assertTrue(body.startswith("TABLE=ATTLOG\n"))

    def test_entry_method_mapping(self):
        self.assertEqual(entry_method_for_verify(2), "card")
        self.assertEqual(entry_method_for_verify(1), "fingerprint")
        self.assertEqual(entry_method_for_verify(None), "fingerprint")


class CommandParseTests(unittest.TestCase):
    def test_parse_userinfo(self):
        fields = parse_userinfo_fields(
            "DATA UPDATE USERINFO PIN=42\tName=Jane\tCard=RFID-9\tPri=0"
        )
        self.assertEqual(fields["PIN"], "42")
        self.assertEqual(fields["Card"], "RFID-9")
        self.assertEqual(fields["Name"], "Jane")

    def test_parse_userinfo_empty_card(self):
        fields = parse_userinfo_fields(
            "DATA UPDATE USERINFO PIN=2\tName=Bob\tCard=\tPri=0"
        )
        self.assertEqual(fields["PIN"], "2")
        self.assertEqual(fields["Card"], "")


if __name__ == "__main__":
    unittest.main()
