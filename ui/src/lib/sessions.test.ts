import { describe, expect, it } from "vitest";
import type { ReportSummary } from "@/client";
import { groupSessions } from "./sessions";

function doc(session: string, kind: string, at: string, state: ReportSummary["state"] = "done"): ReportSummary {
  return {
    id: `private-trial:${kind}/${session}-${at}.json`,
    key: `${session}${at}`,
    root: "private-trial",
    path: `${kind}/${session}-${at}.json`,
    envelope: { v: 1, kind, title: `${kind} ${session}`, created_at: at, session, tags: [] },
    envelope_source: "embedded",
    private: true,
    state,
    warnings: [],
  };
}

describe("groupSessions", () => {
  it("names a session's state: a report wins, then a page that waits, else no report", () => {
    const groups = groupSessions([
      doc("aaaaaaaa", "decisions", "2026-11-01T09:00:00Z", "waiting"),
      doc("aaaaaaaa", "session-report", "2026-11-01T10:00:00Z"),
      doc("bbbbbbbb", "decisions", "2026-11-02T09:00:00Z", "waiting"),
      doc("cccccccc", "journal", "2026-11-03T09:00:00Z"),
    ]);
    const by = Object.fromEntries(groups.map((g) => [g.id, [g.state, g.main.envelope.kind]]));

    expect(by).toEqual({
      aaaaaaaa: ["finished", "session-report"],
      bbbbbbbb: ["waiting", "decisions"],
      cccccccc: ["noReport", "journal"],
    });
  });

  it("puts a session under the day it started and lists the latest start first", () => {
    const groups = groupSessions([
      doc("aaaaaaaa", "journal", "2026-11-01T23:00:00Z"),
      doc("aaaaaaaa", "session-report", "2026-11-03T01:00:00Z"),
      doc("bbbbbbbb", "journal", "2026-11-02T09:00:00Z"),
    ]);

    expect(groups.map((g) => [g.id, g.day])).toEqual([
      ["bbbbbbbb", "2026-11-02"],
      ["aaaaaaaa", "2026-11-01"],
    ]);
  });
});
