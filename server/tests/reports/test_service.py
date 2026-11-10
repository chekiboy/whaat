import json
from datetime import date
from pathlib import Path

import pytest

from tests.conftest import write
from whaat.config import Settings
from whaat.reports.exceptions import ReportNotFoundError
from whaat.reports.schemas import ReportBody, ReportSummary
from whaat.reports.service import MISSING_MARKER_WARNING, ReportService
from whaat.reports.store import FileReportStore, roots_from


def service_for(settings: Settings) -> ReportService:
    return ReportService(FileReportStore(roots_from(settings)))


def first(settings: Settings, kind: str, identity: str | None = None) -> ReportSummary:
    return next(s for s in service_for(settings).list_reports(kind, identity))


def test_envelopes_are_derived_from_path_and_header(settings: Settings) -> None:
    review = first(settings, "review")
    session = first(settings, "session-report")

    assert review.id == "artifacts:reviews/acme/shop/ABC-101/20261028-remove-metrics.md"
    assert review.envelope.model_dump() == {
        "v": 1,
        "kind": "review",
        "title": "Review: ABC-101",
        "created_date": date(2026, 10, 28),
        "created_at": None,
        "session": None,
        "repo": "acme/shop",
        "ticket": "ABC-101",
        "writer": "review-code",
        "identity": None,
        "tags": [],
    }
    assert (session.envelope.session, session.envelope.repo, session.envelope.ticket) == (
        "4c2f638a",
        "acme/tools",
        "ABC-102",
    )
    assert first(settings, "journal", "claude").envelope.session == "38e0994a"


def test_each_identity_owns_only_its_private_folder(settings: Settings) -> None:
    service = service_for(settings)
    claude = service.list_reports(identity="claude")
    second = service.list_reports(identity="second")

    assert [s.id for s in second] == ["private-second:journal/2026-10-29_5011e7aa.md"]
    assert all(s.private for s in second)
    assert not any(s.root == "private-second" for s in claude)
    assert {s.root for s in claude} == {"private-claude"}


def test_a_shared_report_that_names_no_identity_belongs_to_nobody(settings: Settings) -> None:
    shared = [s for s in service_for(settings).list_reports() if s.root in settings.shared_roots]

    assert {s.envelope.kind for s in shared} == {"review", "development", "memory-curation"}
    assert {s.envelope.identity for s in shared} == {None}


def test_shared_reports_name_who_generated_them(settings: Settings) -> None:
    meta = settings.shared_roots["artifacts"] / "reviews/acme/shop/ABC-101/20261028-remove-metrics.meta.json"
    write(meta, json.dumps({"kind": "review", "title": "Written by second", "identity": "second"}))

    review = first(settings, "review", "second")

    assert (review.envelope_source, review.envelope.identity, review.private) == ("meta", "second", False)
    assert service_for(settings).list_reports("review", "claude") == []


def test_a_private_report_belongs_to_its_folder_whatever_its_envelope_says(settings: Settings) -> None:
    meta = settings.identities["second"] / "journal/2026-10-29_5011e7aa.meta.json"
    write(meta, json.dumps({"kind": "journal", "title": "Claims to be claude", "identity": "claude"}))

    journal = first(settings, "journal", "second")

    assert journal.envelope.identity == "second"
    assert journal.warnings == ["its envelope names claude, but it lies in the private folder of second"]


def test_private_follows_the_marker_and_falls_back_to_the_folder_with_a_warning(settings: Settings) -> None:
    assert first(settings, "session-report").warnings == []

    (settings.identities["claude"] / ".private").unlink()
    write(settings.shared_roots["artifacts"] / "reviews/acme/shop/.private", "")

    session = first(settings, "session-report")
    assert (session.private, session.warnings) == (True, [MISSING_MARKER_WARNING])
    assert first(settings, "review").private is True
    assert first(settings, "memory-curation").private is False


def test_state_is_applied_when_rows_were_sent(settings: Settings) -> None:
    assert first(settings, "memory-curation").state == "applied"
    assert first(settings, "review").state == "done"


def test_meta_file_wins_over_derivation_and_a_broken_one_is_reported(settings: Settings) -> None:
    meta = settings.shared_roots["fw-state"] / "memory-curation/2026-10-26.meta.json"
    write(meta, json.dumps({"kind": "memory-curation", "title": "From meta", "writer": "memory-curation"}))
    curation = first(settings, "memory-curation")
    assert (curation.envelope_source, curation.envelope.title) == ("meta", "From meta")

    write(meta, json.dumps({"title": "no kind"}))
    curation = first(settings, "memory-curation")
    assert curation.envelope_source == "derived"
    assert curation.warnings == ["2026-10-26.meta.json is invalid (1 errors); envelope derived instead"]


@pytest.mark.parametrize(
    "report_id",
    [
        "artifacts:../fw-state/memory-curation/2026-10-26.md",
        "artifacts:reviews/acme/shop/ABC-101/missing.md",
        "fw-state:memory-curation/2026-10-26.sent.jsonl",
        "nowhere:reviews/x.md",
        "private-claude:.private",
        "private-claude:../second-archive/journal/2026-10-29_5011e7aa.md",
    ],
)
def test_unknown_or_escaping_ids_are_not_found(settings: Settings, report_id: str) -> None:
    with pytest.raises(ReportNotFoundError):
        service_for(settings).get_report(report_id)


def test_detail_carries_the_parsed_body(settings: Settings) -> None:
    detail = service_for(settings).get_report("artifacts:reviews/acme/shop/ABC-101/20261028-remove-metrics.md")

    assert isinstance(detail.body, ReportBody)
    assert [(section.heading, section.markdown) for section in detail.body.sections] == [
        ("Context pin", "- Repository: shop"),
        ("Verdict: Approve", "Ship it."),
    ]


def test_a_shared_root_lists_the_reports_of_its_own_dirs_only(tmp_path: Path) -> None:
    team = tmp_path / "team"
    write(team / "audits/acme/shop/20261101-checkout.md", "# Audit: checkout\n")
    write(team / "drafts/20261101-notes.md", "# Notes\n")
    settings = Settings(
        shared_roots={"team": team},
        identities={},
        state_dir=tmp_path / "state",
        shared_report_dirs={"team": ("audits",)},
    )

    assert [report.id for report in service_for(settings).list_reports()] == [
        "team:audits/acme/shop/20261101-checkout.md"
    ]
