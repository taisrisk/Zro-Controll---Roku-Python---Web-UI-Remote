from __future__ import annotations

import re
import typing as t


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def parse_tv_brand_and_size(device_name: str | None, model_name: str | None) -> tuple[t.Optional[str], t.Optional[str]]:
    text = (device_name or "").strip()
    if not text:
        text = (model_name or "").strip()
    if not text:
        return None, None

    # Common patterns: `32" TCL Roku TV`, `55 TCL Roku TV`, `65" Hisense Roku TV`
    m = re.search(r"(?P<size>\d{2,3})\s*(?:[\"”]|-inch|in\b)?\s+(?P<brand>[A-Za-z0-9]+)", text)
    if not m:
        return None, None
    size = m.group("size")
    brand = m.group("brand")
    return brand, size


def render_device_badge_svg(
    *,
    ip: str,
    device_name: str | None,
    model_name: str | None,
    model_number: str | None = None,
) -> str:
    brand, size = parse_tv_brand_and_size(device_name, model_name)
    title = (device_name or "").strip() or "Roku"
    subtitle = (model_name or "").strip() or ""
    model_no = (model_number or "").strip()

    big = ""
    small = ""
    if size and brand:
        big = f'{size}" {brand}'
        small = "Roku TV"
    elif subtitle:
        big = subtitle
        small = "Roku"
    else:
        big = title
        small = "Roku"

    lines = []
    lines.append(f"<text x='24' y='76' font-size='44' font-weight='800' fill='#F4F2FF'>{_escape(big)}</text>")
    lines.append(
        f"<text x='24' y='116' font-size='20' font-weight='700' fill='rgba(244,242,255,0.72)'>{_escape(small)}</text>"
    )
    if model_no:
        lines.append(
            f"<text x='24' y='150' font-size='16' font-weight='600' fill='rgba(244,242,255,0.55)'>Model { _escape(model_no) }</text>"
        )
    lines.append(
        f"<text x='24' y='232' font-size='14' font-family='ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' fill='rgba(244,242,255,0.55)'>{_escape(ip)}</text>"
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ff3bd4"/>
      <stop offset="0.55" stop-color="#7a62ff"/>
      <stop offset="1" stop-color="#0a0710"/>
    </linearGradient>
    <radialGradient id="rg" cx="0.3" cy="0.2" r="0.9">
      <stop offset="0" stop-color="rgba(255,255,255,0.18)"/>
      <stop offset="1" stop-color="rgba(255,255,255,0)"/>
    </radialGradient>
    <filter id="s" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="16" flood-color="rgba(0,0,0,0.55)"/>
    </filter>
  </defs>
  <rect x="12" y="12" width="232" height="232" rx="44" fill="url(#g)" filter="url(#s)"/>
  <rect x="12" y="12" width="232" height="232" rx="44" fill="url(#rg)"/>
  <rect x="12" y="12" width="232" height="232" rx="44" fill="none" stroke="rgba(255,255,255,0.10)"/>
  <circle cx="214" cy="46" r="10" fill="rgba(255,59,212,0.75)"/>
  <circle cx="214" cy="46" r="22" fill="rgba(255,59,212,0.12)"/>
  {''.join(lines)}
</svg>"""
    return svg

