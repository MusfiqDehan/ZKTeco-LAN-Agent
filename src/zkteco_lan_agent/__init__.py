"""ZKTeco LAN Agent — bridges non-ADMS ZKTeco devices to Fitssort ADMS HTTP."""

from __future__ import annotations

try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("zkteco-lan-agent")
    except PackageNotFoundError:
        __version__ = "1.0.0"
except ImportError:  # pragma: no cover
    __version__ = "1.0.0"
