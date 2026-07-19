# ZKTeco LAN Agent for Your Local Environment

Bridge non-ADMS ZKTeco devices (Ethernet / PC Connection only) to your application via
ADMS HTTP. Runs on a Office LAN laptop or Pi. If LAN is not available, the device should 

```
Device(s) ──TCP 4370──► Office Laptop (agent) ──HTTP :80 /iclock/*──► Production Cloud Server
```

Package on PyPI: [`zkteco-lan-agent`](https://pypi.org/project/zkteco-lan-agent/)

## Install (Office Laptop)

**Use Python 3.10–3.12** (3.12 recommended). The ZKTeco client is PyPI package
`pyzk` (`from zk import ZK`), not the unrelated `zk` package.

### With uv (recommended)

```bash
uv python install 3.12
uv tool install --python 3.12 zkteco-lan-agent
# or one-off:
uvx --python 3.12 zkteco-lan-agent --config devices.yaml
```

### With pip

```bash
# create a 3.12 venv first if your system python is 3.14
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install zkteco-lan-agent
zkteco-lan-agent --config devices.yaml
```

### If you stay on system Python 3.14 and must compile

```bash
sudo apt install python3-dev build-essential
uv pip install zkteco-lan-agent
```

### From this repo (development)

```bash
cd zkteco_lan_agent
uv sync --python 3.12
uv run zkteco-lan-agent --config ../devices.yaml
```

Copy and edit config:

```bash
cp devices.yaml.example devices.yaml   # from repo root, or create manually
```

Example `devices.yaml`/`devices.yml`:

```yaml
server_url: http://subdomain.domain.com
poll_interval_seconds: 30
command_poll_interval_seconds: 10
heartbeat_interval_seconds: 60

devices:
  - name: Device One
    device_ip: 192.168.1.100
    device_port: 4370
    device_sn: "CHANGEME_SN"
    comm_password: 0
    timezone: Asia/Dhaka

  - name: Device Two
    device_ip: 192.168.1.100
    device_port: 4370
    device_sn: "CHANGEME_SN"
    comm_password: 0
    timezone: Asia/Dhaka 

  ..........
```

Keep the laptop awake (disable sleep while the gym is open).

The agent polls attendance regularly and also syncs device users (USERINFO,
including card numbers) every `userinfo_sync_interval_seconds` (default 300).
That is what populates the Fingerprints page with card holders from the device.
You can also click **Sync Now** on the Devices page to pull users immediately.

---

## Run as a background service

**systemd does not exist on Windows.** Use the section that matches the OS.

### Linux — systemd

```bash
# After: uv tool install zkteco-lan-agent
which zkteco-lan-agent   # note the path, e.g. ~/.local/bin/zkteco-lan-agent

sudo cp zkteco-lan-agent.service /etc/systemd/system/
# edit ExecStart, WorkingDirectory (config path), User=
sudo systemctl daemon-reload
sudo systemctl enable --now zkteco-lan-agent
sudo systemctl status zkteco-lan-agent
```

### Windows — Task Scheduler (built-in) — Always Use the Latest Version

If you installed `zkteco-lan-agent` using `uv`, you should use `uv` for upgrades, as `zkteco-lan-agent upgrade` is not a built-in command of the agent and does not exist. Instead, run `uv pip install --upgrade zkteco-lan-agent` before starting the agent.

1. Create `start-lan-agent.bat` like this:

```bat
@echo off
cd /d C:\gym\agent
uv pip install --upgrade zkteco-lan-agent
zkteco-lan-agent --config devices.yaml
```

2. In Task Scheduler, **Create Task**, set to run at startup: Action: start the `.bat` file created above.
3. Enable restart on failure; uncheck “Stop if runs longer than…”.

This setup will upgrade `zkteco-lan-agent` to the latest available version every time before launching it, as long as you installed using `uv`.

### Windows — NSSM (Windows Service)

```powershell
nssm install ZktecoLanAgent "C:\Users\You\AppData\Local\Programs\Python\Python312\Scripts\zkteco-lan-agent.exe"
nssm set ZktecoLanAgent AppDirectory "C:\gym\agent"
nssm set ZktecoLanAgent AppParameters "--config devices.yaml"
nssm set ZktecoLanAgent AppRestartDelay 10000
nssm start ZktecoLanAgent
```

---

## Dashboard registration

| Field | Value |
|-------|-------|
| Profile | ZKTeco |
| Model | K40 (or actual model) |
| Mode | **TCP Relay** |
| Serial | Exact hardware SN |

## Production ADMS smoke tests

```bash
curl -v "http://<tenant>.fitssort.com/iclock/cdata?SN=<YOUR_SN>"
curl -v "http://<tenant>.fitssort.com/iclock/getrequest?SN=<YOUR_SN>"
```

Use `http://` only (HTTPS ADMS paths are not routed).

## Card + fingerprint

- Enroll fingerprints from the web app (ADMS or TCP Relay) or on the device.
- Provision cards from the app so USERINFO includes `Card=`.
- Device needs a card reader module for card taps.

---

## Publish to PyPI (maintainers)

Uses [uv](https://docs.astral.sh/uv/).

### One-time setup

1. Create a PyPI account at https://pypi.org (and TestPyPI at https://test.pypi.org).
2. Create an **API token** (Account → API tokens). Scope: entire account or project `zkteco-lan-agent`.
3. Prefer env vars (never commit tokens):

```bash
export UV_PUBLISH_TOKEN=pypi-AgEIcHlwaS5vcmc...   # PyPI
# or for TestPyPI:
export UV_PUBLISH_TOKEN=pypi-...                 # TestPyPI token
```

### Build & test locally

```bash
cd zkteco_lan_agent
uv sync --group dev
uv run pytest
uv build
# artifacts in dist/: .whl and .tar.gz
```

### Publish to TestPyPI first

```bash
cd zkteco_lan_agent
uv build
uv publish --publish-url https://test.pypi.org/legacy/ --token "$UV_PUBLISH_TOKEN"
```

Install from TestPyPI to verify:

```bash
uv tool install --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match zkteco-lan-agent
```

### Publish to PyPI

1. Bump `version` in `pyproject.toml` (and ensure changelog/notes if you keep them).
2. Build and publish:

```bash
cd zkteco_lan_agent
uv build
uv publish --token "$UV_PUBLISH_TOKEN"
```

Or interactive (uv prompts for username `__token__` and the API token as password):

```bash
uv publish
```

### Version bumps

Edit `version` in [`pyproject.toml`](pyproject.toml). Reinstall picks up `__version__` via `importlib.metadata`.
