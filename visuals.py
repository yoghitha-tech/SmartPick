"""Product illustrations for SmartPick.

The catalogue is fictional, so instead of downloading photos (which could break
offline or on a hosted demo) every product gets a generated SVG illustration.
The colour comes from the brand, the shape from the headphone type, and small
details (ANC badge, cable, neckband, charging case) from the product's data.

Pure Python, no network, no extra dependencies.
"""
from __future__ import annotations

import base64
import colorsys
import re
import zlib
from html import escape


def _hue(brand: str) -> int:
    return zlib.crc32(brand.encode("utf-8")) % 360


def _hsl(h: int, s: int, l: int) -> str:
    """HSL -> #rrggbb (hex works in every SVG renderer, hsl() does not)."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l / 100, s / 100)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def _num(product_id: str) -> int:
    m = re.search(r"(\d+)", str(product_id))
    return int(m.group(1)) if m else 0


def product_svg(p) -> str:
    """Return an SVG string (400x300) for a product row (Series or dict)."""
    brand, typ, name = str(p["brand"]), str(p["type"]), str(p["name"])
    feats = str(p["features"]).split(",")
    wired = int(p["battery_hours"]) == 0
    h = _hue(brand)
    shade = (_num(p["id"]) % 5) * 3
    bg1, bg2 = _hsl(h, 70, 95), _hsl(h + 30, 60, 86)
    dark, mid = _hsl(h, 55, 24 + shade), _hsl(h, 45, 44 + shade)
    accent = _hsl(h + 40, 85, 60)
    anc = "active_noise_cancellation" in feats

    parts = []
    if typ == "over_ear":
        parts.append(f'<path d="M112 170 C112 38 288 38 288 170" fill="none" stroke="{dark}" stroke-width="16" stroke-linecap="round"/>')
        for x in (80, 258):
            parts.append(f'<rect x="{x}" y="148" width="62" height="100" rx="28" fill="{dark}"/>')
            parts.append(f'<rect x="{x + 10}" y="162" width="42" height="72" rx="20" fill="{mid}"/>')
        if anc:
            for cx in (111, 289):
                parts.append(f'<circle cx="{cx}" cy="198" r="10" fill="{accent}"/>')
        if wired:
            parts.append(f'<path d="M111 248 C111 285 200 270 200 292" fill="none" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>')
    elif typ == "on_ear":
        parts.append(f'<path d="M122 165 C122 62 278 62 278 165" fill="none" stroke="{dark}" stroke-width="11" stroke-linecap="round"/>')
        for cx in (118, 282):
            parts.append(f'<ellipse cx="{cx}" cy="192" rx="30" ry="42" fill="{dark}"/>')
            parts.append(f'<ellipse cx="{cx}" cy="192" rx="19" ry="30" fill="{mid}"/>')
        if anc:
            for cx in (118, 282):
                parts.append(f'<circle cx="{cx}" cy="192" r="7" fill="{accent}"/>')
        if wired:
            parts.append(f'<path d="M118 234 C118 285 200 270 200 292" fill="none" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>')
    else:  # in_ear
        if "neckband" in name.lower():
            parts.append(f'<path d="M112 96 C100 250 300 250 288 96" fill="none" stroke="{dark}" stroke-width="13" stroke-linecap="round"/>')
        elif wired:
            parts.append(f'<path d="M140 150 C140 240 200 230 200 292" fill="none" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>')
            parts.append(f'<path d="M260 150 C260 240 200 230 200 292" fill="none" stroke="{dark}" stroke-width="4" stroke-linecap="round"/>')
        else:
            parts.append(f'<rect x="150" y="212" width="100" height="56" rx="22" fill="{dark}"/>')
            parts.append(f'<rect x="150" y="212" width="100" height="22" rx="11" fill="{mid}"/>')
            parts.append(f'<circle cx="200" cy="248" r="4" fill="{accent}"/>')
        for cx, dx in ((130, 8), (270, -8)):
            parts.append(f'<line x1="{cx}" y1="130" x2="{cx + dx}" y2="190" stroke="{dark}" stroke-width="13" stroke-linecap="round"/>')
            parts.append(f'<circle cx="{cx}" cy="108" r="28" fill="{dark}"/>')
            parts.append(f'<circle cx="{cx}" cy="108" r="16" fill="{mid}"/>')
            if anc:
                parts.append(f'<circle cx="{cx}" cy="108" r="6" fill="{accent}"/>')

    badge = "ANC" if anc else ("WIRED" if wired else "")
    badge_svg = ""
    if badge:
        w = 26 + 9 * len(badge)
        badge_svg = (f'<rect x="{384 - w}" y="16" width="{w}" height="24" rx="12" fill="{accent}"/>'
                     f'<text x="{384 - w / 2}" y="33" text-anchor="middle" font-family="Arial,sans-serif" '
                     f'font-size="12" font-weight="700" fill="#111">{badge}</text>')

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/>'
        f'<stop offset="1" stop-color="{bg2}"/></linearGradient></defs>'
        '<rect width="400" height="300" fill="url(#bg)"/>'
        + "".join(parts) + badge_svg +
        f'<text x="18" y="284" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="{dark}">{escape(brand)}</text>'
        '</svg>'
    )


def data_uri(p) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(product_svg(p).encode("utf-8")).decode("ascii")


def image_html(p, radius: int = 12) -> str:
    """<img> tag to use with st.markdown(..., unsafe_allow_html=True)."""
    alt = escape(str(p["name"]))
    return (f'<img src="{data_uri(p)}" alt="{alt}" '
            f'style="width:100%;border-radius:{radius}px;display:block;margin-bottom:6px"/>')
