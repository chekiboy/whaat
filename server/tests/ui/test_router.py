from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, write
from whaat.cli.main import report_url
from whaat.config import Settings
from whaat.main import create_app
from whaat.reports.store import report_key


@pytest.fixture
def built(settings: Settings, tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    write(dist / "index.html", '<meta name="whaat-token" content="%WHAAT_TOKEN%" /><div id="root"></div>')
    write(dist / "assets/index-abc.js", "console.log(1)")
    write(tmp_path / "secret.txt", "outside")
    return TestClient(create_app(replace(settings, ui_dir=dist), TOKEN))


def test_index_gets_the_server_token(built: TestClient) -> None:
    response = built.get("/ui/")

    assert response.status_code == 200
    assert f'content="{TOKEN}"' in response.text
    assert response.headers["cache-control"] == "no-store"


def test_a_deep_link_gets_index_and_an_asset_gets_its_file(built: TestClient) -> None:
    deep = built.get("/ui/reports/private-claude:session-reports/2026-10-29_session-report_c08cba1f_x.md")
    asset = built.get("/ui/assets/index-abc.js")

    assert deep.status_code == 200 and f'content="{TOKEN}"' in deep.text
    assert asset.text == "console.log(1)"


def test_missing_assets_and_paths_outside_the_build_are_not_served(built: TestClient) -> None:
    assert built.get("/ui/assets/missing.js").status_code == 404
    assert "outside" not in built.get("/ui/../secret.txt").text
    assert "outside" not in built.get("/ui/%2e%2e/secret.txt").text


def test_the_root_redirects_to_the_ui(built: TestClient) -> None:
    response = built.get("/", follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (307, "/ui/")


def test_an_unbuilt_ui_says_how_to_build_it(settings: Settings, tmp_path: Path) -> None:
    client = TestClient(create_app(replace(settings, ui_dir=tmp_path / "no-dist"), TOKEN))

    response = client.get("/ui/")

    assert response.status_code == 404
    assert "pnpm --dir ui build" in response.json()["detail"]


def test_the_report_url_hides_the_path_behind_its_key(settings: Settings) -> None:
    url = report_url(settings, "private-claude:session-reports/2026/10/x.json")

    assert (
        url == f"http://whaat.localhost:1111/ui/reports/{report_key('private-claude:session-reports/2026/10/x.json')}"
    )
    assert "session-reports" not in url and "private-claude" not in url
