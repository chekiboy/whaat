"""The terminal profiles this machine has, read when asked:
the profiles of macOS Terminal and of iTerm2, their colours turned into xterm's. A colour a profile does not set, or
names only as a system colour, comes from Terminal's own Basic palette."""

import plistlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

XTERM_KEYS = [
    "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
    "brightBlack", "brightRed", "brightGreen", "brightYellow",
    "brightBlue", "brightMagenta", "brightCyan", "brightWhite",
]  # fmt: skip
BASIC = {
    "background": "#ffffff",
    "foreground": "#000000",
    "cursor": "#7f7f7f",
    "selectionBackground": "#a4cdff",
    "black": "#000000",
    "red": "#990000",
    "green": "#00a600",
    "yellow": "#999900",
    "blue": "#0000b2",
    "magenta": "#b200b2",
    "cyan": "#00a6b2",
    "white": "#bfbfbf",
    "brightBlack": "#666666",
    "brightRed": "#e50000",
    "brightGreen": "#00d900",
    "brightYellow": "#e5e500",
    "brightBlue": "#0000ff",
    "brightMagenta": "#e500e5",
    "brightCyan": "#00e5e5",
    "brightWhite": "#e5e5e5",
}
TERMINAL_APP = Path.home() / "Library" / "Preferences" / "com.apple.Terminal.plist"
ITERM2 = Path.home() / "Library" / "Preferences" / "com.googlecode.iterm2.plist"
TERMINAL_APP_KEYS = {
    "background": "BackgroundColor",
    "foreground": "TextColor",
    "cursor": "CursorColor",
    "selectionBackground": "SelectionColor",
    **{k: f"ANSI{k[0].upper()}{k[1:]}Color" for k in XTERM_KEYS},
}
ITERM2_KEYS = {
    "background": "Background Color",
    "foreground": "Foreground Color",
    "cursor": "Cursor Color",
    "selectionBackground": "Selection Color",
    **{k: f"Ansi {i} Color" for i, k in enumerate(XTERM_KEYS)},
}


def _hex(parts: list[float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(p * 255))):02x}" for p in parts[:3])


def _numbers(raw: object) -> list[float]:
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
    return [float(x) for x in text.strip("\x00 ").split()]


def nscolor(blob: bytes) -> str | None:
    """An archived NSColor as #rrggbb: RGB, or grey (NSWhite); None for a named system colour."""
    try:
        archive = plistlib.loads(blob)
    except Exception:
        return None
    for obj in archive.get("$objects", []):
        if not isinstance(obj, dict):
            continue
        if "NSRGB" in obj:
            return _hex(_numbers(obj["NSRGB"]))
        if "NSWhite" in obj:
            white = _numbers(obj["NSWhite"])[0]
            return _hex([white, white, white])
    return None


def nsfont(blob: bytes) -> dict[str, Any] | None:
    """An archived NSFont as a CSS family and size; Terminal's SF Mono is ui-monospace in a browser."""
    try:
        objects = plistlib.loads(blob).get("$objects", [])
    except Exception:
        return None
    size = next((o["NSSize"] for o in objects if isinstance(o, dict) and "NSSize" in o), None)
    name = next((o for o in objects[1:] if isinstance(o, str)), None)
    if not name or not size:
        return None
    return {"family": _css_family(name), "size": float(size)}


def _css_family(name: str) -> str:
    if name.startswith("SFMono"):
        return "ui-monospace"
    return name.split("-")[0]


def _profile(
    colours: dict[str, str], font: dict[str, Any] | None, cursor: str, blink: bool, meta: bool
) -> dict[str, Any]:
    return {
        "colors": BASIC | colours,
        "font": font or {"family": "ui-monospace", "size": 12.0},
        "cursor": {"style": cursor, "blink": blink},
        "optionIsMeta": meta,
    }


TERMINAL_CURSOR = {0: "block", 1: "underline", 2: "bar"}
ITERM_CURSOR = {0: "underline", 1: "bar", 2: "block"}


def terminal_app(path: Path = TERMINAL_APP) -> list[dict[str, Any]]:
    try:
        prefs = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return []
    default = prefs.get("Default Window Settings")
    themes = []
    for name, profile in (prefs.get("Window Settings") or {}).items():
        colours = {
            key: colour
            for key, field in TERMINAL_APP_KEYS.items()
            if isinstance(profile.get(field), bytes) and (colour := nscolor(profile[field]))
        }
        font = nsfont(profile["Font"]) if isinstance(profile.get("Font"), bytes) else None
        themes.append(
            {
                "id": f"terminal-app:{name}",
                "name": name,
                "source": "Terminal",
                "default": name == default,
                **_profile(
                    colours,
                    font,
                    TERMINAL_CURSOR.get(int(profile.get("CursorType", 0)), "block"),
                    bool(profile.get("CursorBlink", False)),
                    bool(profile.get("useOptionAsMetaKey", False)),
                ),
            }
        )
    return themes


def iterm2(path: Path = ITERM2) -> list[dict[str, Any]]:
    try:
        prefs = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return []
    themes = []
    default_guid = prefs.get("Default Bookmark Guid")
    bookmarks = prefs.get("New Bookmarks") or []
    defaults = {b.get("Name", "Default") for b in bookmarks if b.get("Guid") == default_guid} or {
        bookmarks[0].get("Name", "Default") if bookmarks else ""
    }
    profiles = [(b.get("Name", "Default"), b) for b in bookmarks]
    profiles += list((prefs.get("Custom Color Presets") or {}).items())
    for name, profile in profiles:
        colours = {}
        for key, field in ITERM2_KEYS.items():
            c = profile.get(field)
            if isinstance(c, dict) and {"Red Component", "Green Component", "Blue Component"} <= set(c):
                colours[key] = _hex([c["Red Component"], c["Green Component"], c["Blue Component"]])
        font_name, _, font_size = str(profile.get("Normal Font", "")).rpartition(" ")
        font = (
            {"family": _css_family(font_name), "size": float(font_size)}
            if font_name and font_size.replace(".", "", 1).isdigit()
            else None
        )
        themes.append(
            {
                "id": f"iterm2:{name}",
                "name": name,
                "source": "iTerm2",
                "default": name in defaults,
                **_profile(
                    colours,
                    font,
                    ITERM_CURSOR.get(int(profile.get("Cursor Type", 2)), "block"),
                    bool(profile.get("Blinking Cursor", False)),
                    int(profile.get("Option Key Sends", 0)) == 2,
                ),
            }
        )
    return themes


READERS: list[Callable[[], list[dict[str, Any]]]] = [terminal_app, iterm2]


def default_theme_id(path: Path = TERMINAL_APP) -> str | None:
    """The machine's own theme: Terminal's default profile, or the first one found; None when there is none."""
    try:
        name = plistlib.loads(path.read_bytes()).get("Default Window Settings")
    except (OSError, plistlib.InvalidFileException):
        name = None
    found = machine_themes()
    ids = [theme["id"] for theme in found]
    if name and f"terminal-app:{name}" in ids:
        return f"terminal-app:{name}"
    return next((theme["id"] for theme in found if theme.get("default")), ids[0] if ids else None)


def machine_themes() -> list[dict[str, Any]]:
    """Every theme the readers find on this machine; a reader with nothing to read gives none."""
    return [theme for read in READERS for theme in read()]
