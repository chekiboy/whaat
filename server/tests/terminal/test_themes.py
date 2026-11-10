import plistlib
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import CLAUDE_TOKEN, TOKEN
from whaat.terminal import themes


def archived(**colour: bytes) -> bytes:
    """An NSKeyedArchiver blob of an NSColor, the way Terminal keeps a profile's colour."""
    return plistlib.dumps(
        {"$archiver": "NSKeyedArchiver", "$objects": ["$null", {**colour, "NSColorSpace": 1}], "$top": {}},
        fmt=plistlib.FMT_BINARY,
    )


def terminal_plist(path: Path) -> Path:
    path.write_bytes(
        plistlib.dumps(
            {
                "Window Settings": {
                    "Pro": {
                        "BackgroundColor": archived(NSWhite=b"0 0.9\x00"),
                        "TextColor": archived(NSRGB=b"1 0.5 0\x00"),
                        "ANSIRedColor": archived(NSRGB=b"0.8 0.1 0.1\x00"),
                    },
                    "Odd": {"BackgroundColor": b"not a plist"},
                }
            }
        )
    )
    return path


def iterm_plist(path: Path) -> Path:
    def c(r: float, g: float, b: float) -> dict[str, float]:
        return {"Red Component": r, "Green Component": g, "Blue Component": b}

    path.write_bytes(
        plistlib.dumps(
            {
                "New Bookmarks": [
                    {"Name": "Default", "Background Color": c(0.98, 0.98, 0.98), "Ansi 1 Color": c(1, 0, 0)}
                ],
                "Custom Color Presets": {"Night": {"Background Color": c(0, 0, 0.2)}},
            }
        )
    )
    return path


def test_terminal_profiles_are_read_as_xterm_colours_with_the_basic_palette_filling_the_rest(tmp_path: Path) -> None:
    found = {t["name"]: t for t in themes.terminal_app(terminal_plist(tmp_path / "t.plist"))}
    pro = found["Pro"]
    assert (pro["id"], pro["source"]) == ("terminal-app:Pro", "Terminal")
    assert (pro["colors"]["background"], pro["colors"]["foreground"], pro["colors"]["red"]) == (
        "#000000",
        "#ff8000",
        "#cc1a1a",
    )
    assert pro["colors"]["blue"] == themes.BASIC["blue"]
    assert found["Odd"]["colors"] == themes.BASIC


def test_iterm_profiles_and_presets_are_read(tmp_path: Path) -> None:
    found = {t["id"]: t for t in themes.iterm2(iterm_plist(tmp_path / "i.plist"))}
    assert set(found) == {"iterm2:Default", "iterm2:Night"}
    assert (found["iterm2:Default"]["colors"]["background"], found["iterm2:Default"]["colors"]["red"]) == (
        "#fafafa",
        "#ff0000",
    )
    assert found["iterm2:Night"]["colors"]["background"] == "#000033"


def test_a_missing_settings_file_gives_no_themes(tmp_path: Path) -> None:
    assert themes.terminal_app(tmp_path / "none.plist") == []
    assert themes.iterm2(tmp_path / "none.plist") == []


def test_the_api_lists_what_the_readers_find_to_the_admin_and_a_machine_theme_can_be_chosen(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(themes, "READERS", [lambda: themes.terminal_app(terminal_plist(tmp_path / "t.plist"))])
    admin = {"Authorization": f"Bearer {TOKEN}"}
    listed = client.get("/api/v1/terminal/themes", headers=admin).json()["themes"]
    assert {t["id"] for t in listed} == {"terminal-app:Pro", "terminal-app:Odd"}
    assert client.get("/api/v1/terminal/themes", headers={"Authorization": f"Bearer {CLAUDE_TOKEN}"}).status_code == 403
    chosen = client.patch("/api/v1/preferences", json={"terminal": {"theme": "terminal-app:Pro"}}, headers=admin)
    assert chosen.json()["terminal"]["theme"] == "terminal-app:Pro"
    assert client.patch("/api/v1/preferences", json={"terminal": {"theme": "neon"}}, headers=admin).status_code == 422


def test_a_profile_brings_its_font_cursor_and_option_key_and_the_app_s_default_is_marked(tmp_path: Path) -> None:
    font = plistlib.dumps(
        {
            "$archiver": "NSKeyedArchiver",
            "$objects": ["$null", {"NSSize": 12.0, "NSName": 2}, "SFMonoTerminal-Regular"],
        },
        fmt=plistlib.FMT_BINARY,
    )
    path = tmp_path / "t.plist"
    path.write_bytes(
        plistlib.dumps(
            {
                "Default Window Settings": "Clear Dark",
                "Window Settings": {
                    "Clear Dark": {"Font": font, "CursorType": 2, "CursorBlink": True, "useOptionAsMetaKey": True},
                    "Basic": {},
                },
            }
        )
    )
    found = {t["name"]: t for t in themes.terminal_app(path)}
    dark = found["Clear Dark"]
    assert (dark["default"], dark["font"], dark["cursor"], dark["optionIsMeta"]) == (
        True,
        {"family": "ui-monospace", "size": 12.0},
        {"style": "bar", "blink": True},
        True,
    )
    assert (found["Basic"]["default"], found["Basic"]["cursor"]["style"], found["Basic"]["optionIsMeta"]) == (
        False,
        "block",
        False,
    )
