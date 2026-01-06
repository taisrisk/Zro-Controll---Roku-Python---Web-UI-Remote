from __future__ import annotations

import json
import os
import tempfile
import time
import typing as t
from dataclasses import dataclass
from pathlib import Path


def _now_ts() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def _safe_device_key(ip: str) -> str:
    return ip.replace(":", "_")


@dataclass
class RecentChannel:
    id: str
    name: str
    last_opened: str


class DeviceStore:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.devices_dir = self.root_dir / "devices"
        self.devices_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_ip(self, ip: str) -> Path:
        return self.devices_dir / f"{_safe_device_key(ip)}.json"

    def load(self, ip: str) -> dict[str, t.Any]:
        path = self._path_for_ip(ip)
        if not path.exists():
            return {
                "device_ip": ip,
                "recent_channels": [],
                "last_active_app": None,
                "last_active_seen_ts": None,
                "last_seen_ts": None,
                "last_reachable_ts": None,
                "device_name": None,
                "device_model": None,
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "device_ip": ip,
                "recent_channels": [],
                "last_active_app": None,
                "last_active_seen_ts": None,
                "last_seen_ts": None,
                "last_reachable_ts": None,
                "device_name": None,
                "device_model": None,
            }

    def save(self, ip: str, state: dict[str, t.Any]) -> None:
        path = self._path_for_ip(ip)
        state = dict(state)
        state["device_ip"] = ip

        tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(self.devices_dir))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(state, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_path, path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def update_seen(
        self,
        ip: str,
        *,
        reachable: bool | None = None,
        name: str | None = None,
        model: str | None = None,
    ) -> dict[str, t.Any]:
        ts = _now_ts()
        state = self.load(ip)
        state["last_seen_ts"] = _iso(ts)
        if reachable is True:
            state["last_reachable_ts"] = _iso(ts)
        if name:
            state["device_name"] = name
        if model:
            state["device_model"] = model
        self.save(ip, state)
        return state

    def bump_recent(self, ip: str, app_id: str, app_name: str | None) -> list[dict[str, t.Any]]:
        if not app_id:
            return []
        ts = _now_ts()
        state = self.load(ip)
        name = (app_name or "").strip() or app_id

        recent: list[dict[str, t.Any]] = list(state.get("recent_channels") or [])
        recent = [x for x in recent if x.get("id") != app_id]
        recent.insert(0, {"id": app_id, "name": name, "last_opened": _iso(ts)})
        state["recent_channels"] = recent[:12]
        self.save(ip, state)
        return state["recent_channels"]

    def note_active_app(self, ip: str, active_app: dict[str, t.Any] | None) -> None:
        ts = _now_ts()
        state = self.load(ip)
        state["last_active_seen_ts"] = _iso(ts)
        state["last_active_app"] = active_app
        self.save(ip, state)

        if active_app and active_app.get("id"):
            self.bump_recent(ip, str(active_app.get("id")), t.cast(t.Optional[str], active_app.get("name")))

    def list_known_devices(self) -> list[dict[str, t.Any]]:
        devices: list[dict[str, t.Any]] = []
        try:
            paths = sorted(self.devices_dir.glob("*.json"), key=lambda p: p.name)
        except Exception:
            return devices
        for p in paths:
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            ip = state.get("device_ip")
            if not ip:
                continue
            devices.append(
                {
                    "ip": ip,
                    "name": state.get("device_name"),
                    "model": state.get("device_model"),
                    "last_seen_ts": state.get("last_seen_ts"),
                    "last_reachable_ts": state.get("last_reachable_ts"),
                }
            )
        devices.sort(key=lambda d: (d.get("last_seen_ts") or "", d.get("ip") or ""), reverse=True)
        return devices
