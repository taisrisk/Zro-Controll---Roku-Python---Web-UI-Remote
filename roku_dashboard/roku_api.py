from __future__ import annotations

import dataclasses
import ipaddress
import socket
import time
import typing as t
import xml.etree.ElementTree as ET

import requests


@dataclasses.dataclass(frozen=True)
class RokuDevice:
    ip: str
    name: t.Optional[str] = None
    model_name: t.Optional[str] = None
    model_number: t.Optional[str] = None
    serial_number: t.Optional[str] = None
    udn: t.Optional[str] = None


class RokuECPError(RuntimeError):
    pass


def _xml_text(elem: t.Optional[ET.Element]) -> t.Optional[str]:
    if elem is None:
        return None
    text = (elem.text or "").strip()
    return text or None


def _parse_xml(xml_bytes: bytes) -> ET.Element:
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RokuECPError("Failed to parse Roku XML response") from exc


def _safe_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {ip}") from exc


class Roku:
    def __init__(self, ip: str, timeout_s: t.Union[float, tuple[float, float]] = 3.0):
        self.ip = _safe_ip(ip)
        self.base = f"http://{self.ip}:8060"
        self._timeout_s = timeout_s
        self._session = requests.Session()

    def _get(self, path: str) -> requests.Response:
        url = f"{self.base}{path}"
        try:
            resp = self._session.get(url, timeout=self._timeout_s)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            raise RokuECPError(f"Roku GET failed: {url}") from exc

    def _post(self, path: str, data: t.Optional[dict[str, str]] = None) -> None:
        url = f"{self.base}{path}"
        try:
            resp = self._session.post(url, data=data, timeout=self._timeout_s)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RokuECPError(f"Roku POST failed: {url}") from exc

    def get_device_info(self) -> RokuDevice:
        resp = self._get("/query/device-info")
        root = _parse_xml(resp.content)
        return RokuDevice(
            ip=self.ip,
            name=_xml_text(root.find("user-device-name")) or _xml_text(root.find("friendly-device-name")),
            model_name=_xml_text(root.find("model-name")),
            model_number=_xml_text(root.find("model-number")),
            serial_number=_xml_text(root.find("serial-number")),
            udn=_xml_text(root.find("udn")),
        )

    def get_apps(self) -> list[dict[str, t.Any]]:
        resp = self._get("/query/apps")
        root = _parse_xml(resp.content)
        apps: list[dict[str, t.Any]] = []
        for app_elem in root.findall("app"):
            app_id = app_elem.attrib.get("id")
            if not app_id:
                continue
            apps.append(
                {
                    "id": app_id,
                    "type": app_elem.attrib.get("type"),
                    "version": app_elem.attrib.get("version"),
                    "name": (app_elem.text or "").strip(),
                }
            )
        apps.sort(key=lambda a: (a.get("name") or "").lower())
        return apps

    def get_active_app(self) -> t.Optional[dict[str, t.Any]]:
        resp = self._get("/query/active-app")
        root = _parse_xml(resp.content)
        app = root.find("app")
        if app is None:
            return None
        return {"id": app.attrib.get("id"), "name": (app.text or "").strip()}

    def keypress(self, key: str) -> None:
        self._post(f"/keypress/{key}")

    def keydown(self, key: str) -> None:
        self._post(f"/keydown/{key}")

    def keyup(self, key: str) -> None:
        self._post(f"/keyup/{key}")

    def launch_app(self, app_id: str) -> None:
        self._post(f"/launch/{app_id}")

    def icon_bytes(self, app_id: str) -> tuple[bytes, str]:
        resp = self._get(f"/query/icon/{app_id}")
        content_type = resp.headers.get("Content-Type") or "image/png"
        return resp.content, content_type

    def device_icon_bytes(self) -> tuple[bytes, str]:
        resp = self._get("/query/icon/0")
        content_type = resp.headers.get("Content-Type") or "image/png"
        return resp.content, content_type


def _ssdp_msearch_payload(mx: int) -> bytes:
    lines = [
        "M-SEARCH * HTTP/1.1",
        "HOST: 239.255.255.250:1900",
        'MAN: "ssdp:discover"',
        f"MX: {mx}",
        "ST: roku:ecp",
        "",
        "",
    ]
    return "\r\n".join(lines).encode("utf-8")


def _parse_ssdp_response(msg: bytes) -> dict[str, str]:
    text = msg.decode("utf-8", errors="ignore")
    headers: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return headers


def discover_roku(
    timeout_s: float = 2.0,
    mx: int = 1,
    *,
    fetch_device_info: bool = True,
    info_timeout_s: float = 1.0,
) -> list[RokuDevice]:
    payload = _ssdp_msearch_payload(mx)
    deadline = time.monotonic() + timeout_s

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.25)

    try:
        sock.sendto(payload, ("239.255.255.250", 1900))
        ips: set[str] = set()
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            headers = _parse_ssdp_response(data)
            # addr[0] is usually the device IP; location may contain the same.
            ip = addr[0]
            try:
                ip = _safe_ip(ip)
            except ValueError:
                continue
            if headers.get("st", "").lower() != "roku:ecp":
                continue
            ips.add(ip)
    finally:
        sock.close()

    devices: list[RokuDevice] = []
    for ip in sorted(ips, key=lambda s: ipaddress.ip_address(s)):
        if not fetch_device_info:
            devices.append(RokuDevice(ip=ip))
            continue
        try:
            devices.append(Roku(ip, timeout_s=info_timeout_s).get_device_info())
        except Exception:
            devices.append(RokuDevice(ip=ip))
    return devices
