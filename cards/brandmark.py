"""The footer brand mark.

Drop a file at cards/brand/logo.png and every layout picks it up. With no file
present the templates fall back to the typed REVO wordmark, so nothing breaks
while artwork is being prepared.

A transparent PNG is expected — the mark sits on a dark card and, on covers,
directly on a photograph, so a white box around it would be visible.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

BRAND_DIR = Path(__file__).resolve().parent / "brand"
CANDIDATES = ["logo.png", "logo.svg", "logo.webp", "logo.jpg"]

# Height in the footer. The supplied wordmark is a heavy rounded italic that
# carries much more ink than the typed Saira version it replaced, so it reads
# larger at the same height and needs to be set smaller to sit at the same
# weight as the date opposite it.
LOGO_HEIGHT = 38


def logo_path() -> Path | None:
    for name in CANDIDATES:
        p = BRAND_DIR / name
        if p.exists():
            return p
    return None


def mark_html() -> tuple[str, str]:
    """Returns (inner html, extra class) for the footer .mark element."""
    p = logo_path()
    if not p:
        return "REVO", ""
    if p.suffix.lower() == ".svg":
        # Inlined so it can inherit currentColor if the artwork uses it.
        return p.read_text(encoding="utf-8"), "has-logo"
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:{mime};base64,{b64}" alt="REVO">', "has-logo"


def apply(tpl: str, logo_color: str = "white") -> str:
    """Fill __MARK__ and __LOGO_CLASS__ in a template."""
    inner, cls = mark_html()
    if not cls and logo_color == "accent":
        cls = "accent"
    return (
        tpl.replace("__MARK__", inner)
        .replace("__LOGO_CLASS__", cls)
        .replace(
            "--pad:76px;",
            f"--pad:76px; --logo-h:{LOGO_HEIGHT}px; --logo-sm:{LOGO_HEIGHT * 1.6:.0f}px;",
        )
    )
