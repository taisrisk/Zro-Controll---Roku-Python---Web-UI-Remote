# ZroControl

Local Roku dashboard for LAN control: devices discovery, fast remote, channels launcher, and local viewing/session stats.

## Why

The official Roku mobile app can feel laggy (button delay), randomly disconnect, and generally gets in the way when you just want a responsive remote. This project is a lightweight local web UI that talks directly to Roku ECP on your network.

## Features

- **LAN Devices**: SSDP discovery with cached results + smooth updates.
- **Remote**: low-latency buttons, hold-to-repeat on the D-pad, optional keyboard control toggle.
- **Channels**: browse installed apps with icons and launch; recently used apps float to the top.
- **User**: local per-browser watch sessions and live-updating totals (stored on disk).

## Run (Windows / PowerShell)

```powershell
cd roku_dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open:

- From the same PC: `http://127.0.0.1:9191`
- From your phone (same Wi‑Fi): `http://<your-pc-lan-ip>:9191`

If your phone can’t connect, allow inbound `9191/TCP` through Windows Firewall.

## Notes

- Roku ECP is `http://<roku-ip>:8060`.
- Local caches are written under `roku_dashboard/data/` (ignored by git).

