import type { ReportSummary } from "@/client";

export type SessionState = "waiting" | "finished" | "noReport";

export type SessionGroup = {
  id: string;
  docs: ReportSummary[];
  state: SessionState;
  title: string;
  ticket: string | null;
  started: string;
  day: string;
  time: string;
  main: ReportSummary;
};

const ORDER: Record<string, number> = { "session-report": 0, journal: 1, decisions: 2 };

const stamp = (report: ReportSummary) => report.envelope.created_at ?? report.envelope.created_date ?? "";

/** The reports that name a session, one group per session. A session belongs to the day it started, and the list runs
    newest start first. A session report makes it finished, even beside a page nobody answered; without one, an
    unanswered decisions page makes it waiting. Its main document opens on a click: the report, else the page that
    waits, else its newest document. */
export function groupSessions(reports: ReportSummary[]): SessionGroup[] {
  const bySession = new Map<string, ReportSummary[]>();
  for (const report of reports) {
    const id = report.envelope.session;
    if (id) bySession.set(id, [...(bySession.get(id) ?? []), report]);
  }
  const groups = [...bySession].map(([id, all]): SessionGroup => {
    const docs = [...all].sort(
      (a, b) => (ORDER[a.envelope.kind] ?? 9) - (ORDER[b.envelope.kind] ?? 9) || stamp(a).localeCompare(stamp(b)),
    );
    const report = docs.find((doc) => doc.envelope.kind === "session-report");
    const waiting = docs.find((doc) => doc.state === "waiting");
    // a group exists only for a session that named at least one report
    const byTime = [...docs].sort((a, b) => stamp(a).localeCompare(stamp(b))) as [ReportSummary, ...ReportSummary[]];
    const first = byTime[0];
    const named = report ?? docs.find((doc) => doc.envelope.kind === "decisions") ?? first;
    const started = stamp(first);
    return {
      id,
      docs,
      state: report ? "finished" : waiting ? "waiting" : "noReport",
      title: named.envelope.title,
      ticket: docs.map((doc) => doc.envelope.ticket).find(Boolean) ?? null,
      started,
      day: started.slice(0, 10),
      time: started.slice(11, 16),
      main: report ?? waiting ?? byTime[byTime.length - 1] ?? first,
    };
  });
  return groups.sort((a, b) => b.started.localeCompare(a.started));
}
