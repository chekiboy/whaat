import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { Decision, Drift, OpenQuestion, SessionReportBody } from "@/client";
import { getReportOptions, listReportsOptions } from "@/client/@tanstack/react-query.gen";
import { JournalBlocks } from "@/components/journal-view";
import { Lines, Panel, Text } from "@/components/report-frame";

type Kind = "du" | "dc" | "df" | "q";
type Filter = Kind | "all";

const OUTCOME = {
  done: { label: "Done", tone: "v-green" },
  partly_done: { label: "Partly done", tone: "v-amber" },
  stuck: { label: "Stuck", tone: "v-red" },
} as const;

const TILES: { kind: Kind; label: string }[] = [
  { kind: "du", label: "User's decision" },
  { kind: "dc", label: "Claude's decision" },
  { kind: "df", label: "Drift" },
  { kind: "q", label: "Open" },
];

function Card({
  kind,
  id,
  title,
  tagline,
  open,
  children,
}: {
  kind: Kind;
  id: string;
  title: string;
  tagline?: string;
  open: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className={`card k-${kind}`} open={open}>
      <summary>
        <span className="sev">{id}</span>
        <span className="ctitle">{title}</span>
        <span className="tagline">{tagline}</span>
        <span className="chev" />
      </summary>
      <div className="cbody">{children}</div>
    </details>
  );
}

function DecisionCard({ decision, open }: { decision: Decision; open: boolean }) {
  return (
    <Card
      kind={decision.by === "user" ? "du" : "dc"}
      id={decision.id}
      title={decision.title}
      tagline={decision.by === "user" ? "the user" : "Claude"}
      open={open}
    >
      <h4>Options</h4>
      <ul className="options">
        {decision.options.map((option) => (
          <li key={option.text} className={option.chosen ? "" : "lost"}>
            <span>{option.chosen ? "✔" : "·"}</span>
            <span>
              {option.text}
              {option.note && <em> — {option.note}</em>}
            </span>
          </li>
        ))}
      </ul>
      <p>
        <strong>Why:</strong> {decision.why}
      </p>
    </Card>
  );
}

function SessionJournal({ session, open }: { session: string; open: boolean }) {
  const { data: entries } = useQuery(listReportsOptions({ query: { session, kind: "journal" } }));
  const details = useQueries({
    queries: (entries ?? []).map((entry) => getReportOptions({ path: { report_id: entry.id } })),
  });
  const blocks = details.flatMap(({ data }) => (data?.body.format === "journal" ? data.body.blocks : []));
  return blocks.length > 0 ? (
    <JournalBlocks blocks={blocks} idPrefix="journal" collapsible open={open} />
  ) : (
    <Panel id="journal-reflection" title="Reflection" collapsible open={open}>
      <p className="muted">No journal entry yet.</p>
    </Panel>
  );
}

function count<T>(items: T[] | null | undefined, test: (item: T) => boolean = () => true): number {
  return (items ?? []).filter(test).length;
}

export function SessionReportView({
  report,
  session,
}: {
  report: SessionReportBody;
  session: string | null | undefined;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState({ open: false, version: 0 });
  const outcome = report.outcome ? OUTCOME[report.outcome.status] : null;
  const counts: Record<Kind, number> = {
    du: count(report.decisions, (decision) => decision.by === "user"),
    dc: count(report.decisions, (decision) => decision.by === "claude"),
    df: count(report.drift),
    q: count(report.open_questions),
  };
  const all = filter === "all";
  const shows = (kind: Kind) => all || filter === kind;
  const decisions = (report.decisions ?? []).filter((decision) => shows(decision.by === "user" ? "du" : "dc"));
  const setAll = (open: boolean) => setExpanded(({ version }) => ({ open, version: version + 1 }));
  const v = expanded.version;

  return (
    <>
      <nav className="toc">
        {[
          ["task", "Task"],
          ["steps", "What we did"],
          ["decisions", "Decisions"],
          ["drift", "Drift"],
          ["open-questions", "Open questions"],
          ["journal-narrative", "Narrative"],
          ["journal-reflection", "Reflection"],
        ].map(([id, label]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>
      {report.outcome && outcome ? (
        <div className={`verdict sh-paper ${outcome.tone}`}>
          <div className="vhead">
            <span className="vlabel">Outcome</span>
            <span className="vtext">{outcome.label}</span>
            <span className="vsub">{report.outcome.line}</span>
          </div>
          <p>{report.outcome.summary}</p>
        </div>
      ) : (
        <div className="verdict sh-paper">
          <span className="vlabel">Outcome</span> <span className="muted">Not recorded.</span>
        </div>
      )}
      <div className="dash">
        <div className="tiles">
          {TILES.map(({ kind, label }) => (
            <button
              key={kind}
              type="button"
              className={`tile k-${kind}${filter === kind ? " active" : ""}`}
              onClick={() => setFilter(filter === kind ? "all" : kind)}
            >
              <b>{counts[kind]}</b> {label}
            </button>
          ))}
          <button type="button" className={`tile all${all ? " active" : ""}`} onClick={() => setFilter("all")}>
            <b>{counts.du + counts.dc + counts.df + counts.q}</b> All
          </button>
        </div>
        <div className="tools">
          <button type="button" onClick={() => setAll(true)}>
            ↓ Expand
          </button>
          <button type="button" onClick={() => setAll(false)}>
            ↑ Collapse
          </button>
        </div>
      </div>
      {all && (
        <Panel id="task" title="Task">
          <Text value={report.task} />
        </Panel>
      )}
      {all && (
        <Panel key={`steps-${v}`} id="steps" title="What we did" collapsible open={expanded.open}>
          <Lines items={report.steps} none="Nothing recorded as done." />
        </Panel>
      )}
      {(all || filter === "du" || filter === "dc") && (
        <Panel id="decisions" title="Decisions">
          {report.decisions == null ? (
            <p className="muted">Not recorded.</p>
          ) : decisions.length === 0 ? (
            <p className="muted">No decisions.</p>
          ) : (
            <div className="cards">
              {decisions.map((decision) => (
                <DecisionCard key={`${decision.id}-${v}`} decision={decision} open={expanded.open} />
              ))}
            </div>
          )}
        </Panel>
      )}
      {shows("df") && (
        <Panel id="drift" title="Drift">
          <Items
            items={report.drift}
            none="No drift."
            render={(drift: Drift) => (
              <Card key={`${drift.id}-${v}`} kind="df" id={drift.id} title={drift.title} open={expanded.open}>
                <p>{drift.cause}</p>
              </Card>
            )}
          />
        </Panel>
      )}
      {shows("q") && (
        <Panel id="open-questions" title="Open questions">
          <Items
            items={report.open_questions}
            none="None."
            render={(question: OpenQuestion) => (
              <Card key={`${question.id}-${v}`} kind="q" id={question.id} title={question.text} open={expanded.open}>
                <p>{question.text}</p>
              </Card>
            )}
          />
        </Panel>
      )}
      {all && session && <SessionJournal key={`journal-${v}`} session={session} open={expanded.open} />}
    </>
  );
}

function Items<T>({
  items,
  none,
  render,
}: {
  items: T[] | null | undefined;
  none: string;
  render: (item: T) => React.ReactNode;
}) {
  if (items == null) return <p className="muted">Not recorded.</p>;
  if (items.length === 0) return <p className="muted">{none}</p>;
  return <div className="cards">{items.map(render)}</div>;
}
