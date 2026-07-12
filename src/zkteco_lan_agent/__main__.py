from __future__ import annotations

import argparse
import logging
import sys
import time

from zkteco_lan_agent import __version__
from zkteco_lan_agent.config import ConfigError, load_config
from zkteco_lan_agent.device_worker import DeviceWorker
from zkteco_lan_agent.server_client import ServerClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("zkteco_lan_agent")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ZKTeco LAN Agent — bridge non-ADMS devices to Fitssort")
    parser.add_argument(
        "--config",
        "-c",
        default="devices.yaml",
        help="Path to devices.yaml",
    )
    parser.add_argument("--version", action="version", version=f"zkteco-lan-agent {__version__}")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    server = ServerClient(config.server_url)
    workers = [DeviceWorker(config, device, server) for device in config.devices]
    log.info(
        "Started zkteco-lan-agent %s server=%s devices=%d",
        __version__,
        config.server_url,
        len(workers),
    )
    for w in workers:
        log.info(
            "  device name=%s sn=%s ip=%s:%d",
            w.device.name,
            w.device.device_sn,
            w.device.device_ip,
            w.device.device_port,
        )

    try:
        while True:
            start = time.monotonic()
            for worker in workers:
                worker.tick()
            elapsed = time.monotonic() - start
            time.sleep(max(1, config.poll_interval_seconds - elapsed))
    except KeyboardInterrupt:
        log.info("Shutting down")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
