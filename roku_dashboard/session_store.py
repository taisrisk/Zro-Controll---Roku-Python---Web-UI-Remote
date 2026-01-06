from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import typing as t
from pathlib import Path


def _now_ts() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def _parse_iso(s: str) -> float:
    return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))


def _safe_device_key(ip: str) -> str:
    return ip.replace(":", "_")


def make_user_id(device_key: str, browser_id: str) -> str:
    h = hashlib.sha256(f"{device_key}|{browser_id}".encode("utf-8")).hexdigest()
    return "u_" + h[:16]


class SessionStore:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.sessions_dir = self.root_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_ip(self, ip: str) -> Path:
        return self.sessions_dir / f"{_safe_device_key(ip)}.json"

    def load(self, ip: str) -> dict[str, t.Any]:
        path = self._path_for_ip(ip)
        if not path.exists():
            return {"device_ip": ip, "users": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"device_ip": ip, "users": {}}

    def save(self, ip: str, state: dict[str, t.Any]) -> None:
        path = self._path_for_ip(ip)
        state = dict(state)
        state["device_ip"] = ip

        tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(self.sessions_dir))
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

    def _get_user(self, state: dict[str, t.Any], ip: str, browser_id: str) -> tuple[str, dict[str, t.Any]]:
        users: dict[str, t.Any] = state.setdefault("users", {})
        device_key = ip
        user_id = make_user_id(device_key, browser_id)
        user = users.get(user_id)
        if not isinstance(user, dict):
            user = {
                "browser_id": browser_id,
                "sessions": [],
                "total_watch_time_sec": 0,
                "current": None,
                "last_active_app_id": None,
                "updated_ts": None,
            }
            users[user_id] = user
        user["browser_id"] = browser_id
        return user_id, user

    def observe_active_app(self, ip: str, browser_id: str, active_app: t.Optional[dict[str, t.Any]]) -> dict[str, t.Any]:
        ts = _now_ts()
        state = self.load(ip)
        user_id, user = self._get_user(state, ip, browser_id)

        active_id = None
        active_name = None
        if active_app and active_app.get("id"):
            active_id = str(active_app.get("id"))
            active_name = str(active_app.get("name") or active_id)

        current = user.get("current")
        current_id = current.get("channel_id") if isinstance(current, dict) else None

        def close_current(end_ts: float) -> None:
            cur = user.get("current")
            if not isinstance(cur, dict):
                return
            start_time = t.cast(str, cur.get("start_time"))
            try:
                start_ts = _parse_iso(start_time)
            except Exception:
                start_ts = end_ts
            duration = max(0, int(end_ts - start_ts))
            session = {
                "channel_id": cur.get("channel_id"),
                "channel_name": cur.get("channel_name"),
                "start_time": start_time,
                "end_time": _iso(end_ts),
                "duration_sec": duration,
            }
            sessions = user.setdefault("sessions", [])
            if isinstance(sessions, list):
                sessions.insert(0, session)
                del sessions[500:]
            user["total_watch_time_sec"] = int(user.get("total_watch_time_sec") or 0) + duration
            user["current"] = None

        def open_current(start_ts: float) -> None:
            user["current"] = {
                "channel_id": active_id,
                "channel_name": active_name,
                "start_time": _iso(start_ts),
            }

        if active_id is None:
            close_current(ts)
        elif current_id is None:
            open_current(ts)
        elif active_id != current_id:
            close_current(ts)
            open_current(ts)

        user["last_active_app_id"] = active_id
        user["updated_ts"] = _iso(ts)
        self.save(ip, state)

        return {"device_ip": ip, "user_id": user_id}

    def get_user_view(self, ip: str, browser_id: str) -> dict[str, t.Any]:
        state = self.load(ip)
        user_id, user = self._get_user(state, ip, browser_id)
        self.save(ip, state)

        sessions = user.get("sessions") if isinstance(user.get("sessions"), list) else []
        current = user.get("current") if isinstance(user.get("current"), dict) else None
        total = int(user.get("total_watch_time_sec") or 0)
        now_ts = _now_ts()

        def window_start_ts(days_back: int) -> float:
            lt = time.localtime(now_ts)
            midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            return midnight - (days_back * 86400)

        today_start = window_start_ts(0)
        week_start = window_start_ts(6)
        month_start = window_start_ts(29)

        def sum_since(start_ts: float) -> int:
            acc = 0
            for s in sessions:
                try:
                    st = _parse_iso(t.cast(str, s.get("start_time")))
                except Exception:
                    continue
                if st < start_ts:
                    continue
                acc += int(s.get("duration_sec") or 0)
            if current:
                try:
                    st = _parse_iso(t.cast(str, current.get("start_time")))
                    if st >= start_ts:
                        acc += max(0, int(now_ts - st))
                except Exception:
                    pass
            return acc

        return {
            "device_ip": ip,
            "user_id": user_id,
            "browser_id": browser_id,
            "totals": {
                "total_watch_time_sec": total,
                "today_sec": sum_since(today_start),
                "week_sec": sum_since(week_start),
                "month_sec": sum_since(month_start),
            },
            "current": current,
            "sessions": sessions[:100],
            "updated_ts": user.get("updated_ts"),
        }

