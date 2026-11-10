import type { ReactNode } from "react";
import type { ReportDetail } from "@/client";
import { CurationReportView } from "@/components/curation-report-view";
import { JournalBlocks } from "@/components/journal-view";
import { SessionReportView } from "@/components/session-report-view";
import { MarkdownView } from "@/report-views/markdown";

type Body = ReportDetail["body"];
type Format = Body["format"];
type BodyOf<F extends Format> = Extract<Body, { format: F }>;
type Pin = [string, string | null | undefined];

export type ReportView<F extends Format> = {
  pins?: (body: BodyOf<F>) => Pin[];
  render: (body: BodyOf<F>, report: ReportDetail) => ReactNode;
};

/** One entry per body format: the frame (header, pins) is shared, only the body is swapped. */
const VIEWS: { [F in Format]: ReportView<F> } = {
  markdown: {
    pins: (body) => body.pins.map((pin, index) => [`Pin ${index + 1}`, pin]),
    render: (body) => <MarkdownView body={body} />,
  },
  journal: {
    render: (body) => <JournalBlocks blocks={body.blocks} />,
  },
  "session-report": {
    pins: (body) => [
      ["Branch", body.report.branch],
      ["Transcript", body.report.transcript],
    ],
    render: (body, report) => <SessionReportView report={body.report} session={report.envelope.session} />,
  },
  "memory-curation": {
    render: (body, report) => (
      <CurationReportView report={body.report} reportId={report.id} identity={report.envelope.identity} />
    ),
  },
};

export function viewOf<F extends Format>(body: BodyOf<F>): ReportView<F> {
  return VIEWS[body.format as F];
}
