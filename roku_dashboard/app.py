from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import time
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, url_for, send_file

from device_badge import render_device_badge_svg
from device_store import DeviceStore
from session_store import SessionStore
from roku_api import Roku, RokuECPError, discover_roku


def create_app() -> Flask:
    app = Flask(__name__)
    data_root = Path(__file__).resolve().parent / "data"
    store = DeviceStore(root_dir=data_root)
    sessions = SessionStore(root_dir=data_root)
    badges_dir = data_root / "badges"
    badges_dir.mkdir(parents=True, exist_ok=True)
    lan_cache: dict[str, object] = {"ts": 0.0, "devices": []}

    BROWSER_ID_COOKIE = "zrocontrol_bid"

    def _get_browser_id() -> str:
        bid = request.cookies.get(BROWSER_ID_COOKIE)
        if bid:
            return bid
        return uuid4().hex

    @app.after_request
    def _set_browser_id_cookie(resp):
        if request.cookies.get(BROWSER_ID_COOKIE):
            return resp
        bid = _get_browser_id()
        resp.set_cookie(BROWSER_ID_COOKIE, bid, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax")
        return resp

    @lru_cache(maxsize=64)
    def _roku(ip: str) -> Roku:
        return Roku(ip, timeout_s=3.0)

    @lru_cache(maxsize=64)
    def _roku_fast(ip: str) -> Roku:
        return Roku(ip, timeout_s=1.5)

    def _format_duration(sec: int) -> str:
        sec = max(0, int(sec))
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/lan")
    def lan_control():
        timeout_s = float(request.args.get("timeout", "2.0"))
        now = time.time()
        cached = lan_cache.get("devices") if (now - float(lan_cache.get("ts") or 0.0)) < 60.0 else None
        if not cached:
            cached = store.list_known_devices()
        return render_template("lan_control.html", devices=cached or [], timeout_s=timeout_s)

    @app.get("/lan/devices")
    def lan_devices():
        timeout_s = float(request.args.get("timeout", "1.8"))
        try:
            devices = discover_roku(timeout_s=timeout_s, fetch_device_info=True, info_timeout_s=0.9)
        except Exception:
            devices = []

        result = []
        for d in devices:
            reachable = bool(d.name or d.model_name or d.model_number or d.serial_number or d.udn)
            cached = store.update_seen(
                d.ip,
                reachable=reachable,
                name=d.name,
                model=d.model_name or d.model_number,
            )
            result.append(
                {
                    "name": (d.name or cached.get("device_name") or "Roku"),
                    "ip": d.ip,
                    "model": (d.model_name or d.model_number or cached.get("device_model") or ""),
                    "icon_url": url_for("api_device_badge", ip=d.ip),
                    "reachable": reachable,
                    "last_seen_ts": cached.get("last_seen_ts"),
                    "last_reachable_ts": cached.get("last_reachable_ts"),
                }
            )
        lan_cache["ts"] = time.time()
        lan_cache["devices"] = result
        return jsonify(result)

    @app.get("/channels")
    def channels():
        ip = request.args.get("ip")
        apps = []
        active = None
        error = None
        if ip:
            try:
                roku = _roku(ip)
                apps = roku.get_apps()
                active = roku.get_active_app()
                state = store.load(ip)
            except (ValueError, RokuECPError) as exc:
                error = str(exc)

        # Sort apps so most-recent launched appear first (no separate "recent" section).
        recent = []
        if ip:
            try:
                recent = list(store.load(ip).get("recent_channels") or [])
            except Exception:
                recent = []
        rank: dict[str, int] = {}
        for idx, ch in enumerate(recent):
            if ch.get("id"):
                rank[str(ch["id"])] = idx
        if rank:
            apps.sort(key=lambda a: (rank.get(str(a.get("id")), 10_000), (a.get("name") or "").lower()))
        else:
            apps.sort(key=lambda a: ((a.get("name") or "").lower()))
        return render_template(
            "channels.html", ip=ip, apps=apps, active=active, error=error
        )

    @app.get("/remote")
    def remote():
        ip = request.args.get("ip")
        info = None
        error = None
        recent_preview: list[dict[str, object]] = []
        if ip:
            try:
                info = _roku(ip).get_device_info()
                recent_channels = list(store.load(ip).get("recent_channels") or [])
                watch_totals = sessions.get_app_watch_totals(ip, _get_browser_id())
                for ch in recent_channels[:8]:
                    cid = str(ch.get("id") or "")
                    if not cid:
                        continue
                    watched_sec = int(watch_totals.get(cid) or 0)
                    recent_preview.append(
                        {
                            "id": cid,
                            "name": ch.get("name") or cid,
                            "watched_text": _format_duration(watched_sec) if watched_sec > 0 else "not watched yet",
                        }
                    )
            except (ValueError, RokuECPError) as exc:
                error = str(exc)
        return render_template(
            "remote.html",
            ip=ip,
            info=info,
            error=error,
            recent_preview=recent_preview,
        )

    @app.get("/user")
    def user_tab():
        ip = request.args.get("ip")
        error = None
        if ip:
            try:
                _ = _roku_fast(ip).get_active_app()
            except Exception:
                pass
        else:
            error = "Select a device first (LAN tab)."
        return render_template("user.html", ip=ip, error=error)

    @app.get("/api/device-info")
    def api_device_info():
        ip = request.args.get("ip", "")
        try:
            device = _roku(ip).get_device_info()
        except (ValueError, RokuECPError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "device": device.__dict__})

    @app.get("/api/apps")
    def api_apps():
        ip = request.args.get("ip", "")
        try:
            apps = _roku(ip).get_apps()
        except (ValueError, RokuECPError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "apps": apps})

    @app.get("/api/active-app")
    def api_active_app():
        ip = request.args.get("ip", "")
        try:
            active = _roku_fast(ip).get_active_app()
            store.note_active_app(ip, active)
            sessions.observe_active_app(ip, _get_browser_id(), active)
        except (ValueError, RokuECPError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "active": active})

    @app.get("/api/recent-channels")
    def api_recent_channels():
        ip = request.args.get("ip", "")
        try:
            state = store.load(ip)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "recent_channels": list(state.get("recent_channels") or [])})

    @app.get("/api/user-data")
    def api_user_data():
        ip = request.args.get("ip", "")
        refresh = request.args.get("refresh", "0") == "1"
        if not ip:
            return jsonify({"ok": False, "error": "Missing ip"}), 400
        if refresh:
            try:
                active = _roku_fast(ip).get_active_app()
                store.note_active_app(ip, active)
                sessions.observe_active_app(ip, _get_browser_id(), active)
            except Exception:
                pass
        data = sessions.get_user_view(ip, _get_browser_id())
        return jsonify({"ok": True, "data": data})

    @app.get("/api/reachable")
    def api_reachable():
        ip = request.args.get("ip", "")
        try:
            info = _roku_fast(ip).get_device_info()
            cached = store.update_seen(ip, reachable=True, name=info.name, model=info.model_name or info.model_number)
            return jsonify(
                {
                    "ok": True,
                    "reachable": True,
                    "name": info.name,
                    "model": info.model_name or info.model_number,
                    "last_seen_ts": cached.get("last_seen_ts"),
                    "last_reachable_ts": cached.get("last_reachable_ts"),
                }
            )
        except (ValueError, RokuECPError):
            cached = store.update_seen(ip, reachable=False)
            return jsonify(
                {
                    "ok": True,
                    "reachable": False,
                    "last_seen_ts": cached.get("last_seen_ts"),
                    "last_reachable_ts": cached.get("last_reachable_ts"),
                }
            )

    @app.post("/api/keypress")
    def api_keypress():
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "")
        key = data.get("key", "")
        try:
            _roku_fast(ip).keypress(key)
        except (ValueError, RokuECPError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True})

    @app.post("/api/launch")
    def api_launch():
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "")
        app_id = data.get("app_id", "")
        app_name = data.get("app_name", None)
        try:
            _roku_fast(ip).launch_app(app_id)
            store.bump_recent(ip, app_id, app_name)
        except (ValueError, RokuECPError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True})

    @app.get("/api/icon/<app_id>")
    def api_icon(app_id: str):
        ip = request.args.get("ip", "")
        try:
            content, content_type = _roku(ip).icon_bytes(app_id)
        except (ValueError, RokuECPError):
            return Response(status=404)
        return Response(content, content_type=content_type)

    @app.get("/api/device-icon")
    def api_device_icon():
        ip = request.args.get("ip", "")
        try:
            content, content_type = _roku_fast(ip).device_icon_bytes()
        except (ValueError, RokuECPError):
            return Response(status=404)
        return Response(content, content_type=content_type)

    @app.get("/api/device-badge")
    def api_device_badge():
        ip = request.args.get("ip", "")
        state = store.load(ip)
        sig_src = f"{ip}|{state.get('device_name') or ''}|{state.get('device_model') or ''}"
        sig = hashlib.sha256(sig_src.encode("utf-8")).hexdigest()[:16]
        badge_path = badges_dir / f"{ip}.svg"
        try:
            if badge_path.exists():
                head = badge_path.read_text(encoding="utf-8")[:120]
                if f"sig:{sig}" in head:
                    return send_file(badge_path, mimetype="image/svg+xml", max_age=86400)
        except Exception:
            pass

        svg = render_device_badge_svg(
            ip=ip,
            device_name=state.get("device_name"),
            model_name=state.get("device_model"),
            model_number=None,
        )
        svg = f"<!-- sig:{sig} -->\n{svg}"
        try:
            badge_path.write_text(svg, encoding="utf-8")
        except Exception:
            return Response(svg, content_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})
        return send_file(badge_path, mimetype="image/svg+xml", max_age=86400)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=9191, debug=False, use_reloader=False)
