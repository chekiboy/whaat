from fastapi.testclient import TestClient

from tests.conftest import TOKEN

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["app"] == "whaat"


def test_reports_and_identities_need_the_token(client: TestClient) -> None:
    assert client.get("/api/v1/reports").status_code == 401
    assert client.get("/api/v1/reports", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/identities").status_code == 401


def test_list_filters_and_detail(client: TestClient) -> None:
    listed = client.get("/api/v1/reports", headers=AUTH).json()
    reviews = client.get("/api/v1/reports", params={"kind": "review"}, headers=AUTH).json()
    second = client.get("/api/v1/reports", params={"identity": "second"}, headers=AUTH).json()
    detail = client.get(f"/api/v1/reports/{reviews[0]['id']}", headers=AUTH)

    assert len(listed) == 6
    assert [report["envelope"]["kind"] for report in reviews] == ["review"]
    assert [report["id"] for report in second] == ["private-second:journal/2026-10-29_5011e7aa.md"]
    assert detail.status_code == 200
    assert detail.json()["body"]["title"] == "Review: ABC-101"


def test_identities_are_listed_with_their_counts(client: TestClient) -> None:
    identities = client.get("/api/v1/identities", headers=AUTH).json()

    assert identities == [
        {
            "id": "claude",
            "default": True,
            "has_private_folder": True,
            "has_token": True,
            "report_count": 2,
            "private_report_count": 2,
        },
        {
            "id": "second",
            "default": False,
            "has_private_folder": True,
            "has_token": False,
            "report_count": 1,
            "private_report_count": 1,
        },
    ]


def test_unknown_report_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/reports/artifacts:reviews/nope.md", headers=AUTH).status_code == 404


def test_a_report_opens_by_its_opaque_key(client: TestClient) -> None:
    listed = client.get("/api/v1/reports", headers=AUTH).json()

    detail = client.get(f"/api/v1/reports/by-key/{listed[0]['key']}", headers=AUTH)

    assert detail.status_code == 200
    assert detail.json()["id"] == listed[0]["id"]
    assert len(listed[0]["key"]) == 16 and listed[0]["id"] not in listed[0]["key"]
    assert client.get("/api/v1/reports/by-key/0000000000000000", headers=AUTH).status_code == 404
