import type { ReportSummary } from "@/client";

export function summary(
  session: string,
  kind: string,
  at: string,
  state: ReportSummary["state"] = "done",
): ReportSummary {
  return {
    id: `private-trial:${kind}/${session}-${at}.json`,
    key: `${session}-${kind}-${at}`,
    root: "private-trial",
    path: `${kind}/${session}-${at}.json`,
    envelope: { v: 1, kind, title: `${kind} ${session}`, created_at: at, session, tags: [] },
    envelope_source: "embedded",
    private: true,
    state,
    warnings: [],
  };
}

/** A fetch that answers every report list call with these summaries. */
export function listing(reports: ReportSummary[]): (input: RequestInfo | URL) => Promise<Response> {
  return async (input) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    const kind = url.searchParams.get("kind");
    const session = url.searchParams.get("session");
    const shown = reports.filter(
      (r) => (!kind || r.envelope.kind === kind) && (!session || r.envelope.session === session),
    );
    return new Response(JSON.stringify(shown), { status: 200, headers: { "Content-Type": "application/json" } });
  };
}
