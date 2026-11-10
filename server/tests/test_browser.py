from pathlib import Path

import pytest

from whaat.platform import browser


def test_the_app_window_opens_the_page_without_browser_chrome_in_a_profile_of_its_own(tmp_path: Path) -> None:
    command = browser.app_window_command("/bin/chrome", "http://whaat.localhost:1111/ui/", tmp_path / "app-window")

    assert command[0] == "/bin/chrome"
    assert "--app=http://whaat.localhost:1111/ui/" in command
    assert f"--user-data-dir={tmp_path / 'app-window'}" in command


def test_the_first_installed_app_browser_is_used_and_none_when_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chromium = tmp_path / "Chromium"
    chromium.touch()
    monkeypatch.setattr(browser, "APP_BROWSER_PATHS", (str(tmp_path / "Chrome"), str(chromium)))
    monkeypatch.setattr(browser.shutil, "which", lambda _: None)
    found = browser.app_browser()
    monkeypatch.setattr(browser, "APP_BROWSER_PATHS", ())

    assert found == str(chromium)
    assert browser.app_browser() is None
