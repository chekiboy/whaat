import os
from pathlib import Path

import pytest

from whaat.config import Settings
from whaat.reports.schemas import ReportBody
from whaat.reports.service import ReportService
from whaat.reports.store import FileReportStore, roots_from

CORPUS = os.environ.get("WHAAT_MD_CORPUS")


@pytest.mark.skipif(
    not CORPUS, reason="set WHAAT_MD_CORPUS to a copy of a private folder with journal/ and session-reports/"
)
def test_the_markdown_written_before_json_still_lists_and_opens(tmp_path: Path) -> None:
    root = Path(str(CORPUS))
    settings = Settings(shared_roots={}, identities={"claude": root}, state_dir=tmp_path)
    service = ReportService(FileReportStore(roots_from(settings)))
    expected = len(list((root / "journal").glob("*.md"))) + len(list((root / "session-reports").glob("*.md")))

    summaries = service.list_reports()

    assert len(summaries) == expected
    assert [summary.warnings for summary in summaries if summary.warnings] == []
    assert all(isinstance(service.get_report(summary.id).body, ReportBody) for summary in summaries)
