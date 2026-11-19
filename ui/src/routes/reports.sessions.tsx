import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Fragment, useState } from "react";
import { listReportsOptions } from "@/client/@tanstack/react-query.gen";
import { ReportsModuleBar } from "@/components/reports-module-bar";
import { useLanguage, useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { useKindInfo } from "@/lib/report-kinds";
import { groupSessions, type SessionGroup, type SessionState } from "@/lib/sessions";
import "@/styles/memory.css";

export const Route = createFileRoute("/reports/sessions")({
  component: SessionsPage,
});

const PAGE = 20;
type Filter = "all" | "waiting" | "finished";
const COLOR: Record<SessionState, string> = {
  waiting: "var(--orange)",
  finished: "var(--teal)",
  running: "var(--blue)",
};

/** Every session that left a document, one dense line each, paged and filtered; a line opens the session's main
    document, a chip on it opens that document. */
function SessionsPage() {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const kindInfo = useKindInfo();
  const navigate = useNavigate();
  usePageHeading(sectionTitle("Reports"), [
    { label: t("shell.reports"), to: "/reports" },
    { label: t("terminal.sessions") },
  ]);
  const { data } = useQuery(listReportsOptions());
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const all = groupSessions(data ?? []);
  const q = query.trim().toLowerCase();
  const matching = all.filter((s) => !q || `${s.id} ${s.ticket ?? ""} ${s.title}`.toLowerCase().includes(q));
  const shown = matching.filter((s) => filter === "all" || s.state === filter);
  const part = shown.slice(page * PAGE, (page + 1) * PAGE);
  const open = (key: string) => navigate({ to: "/reports/$key", params: { key } });

  const dayLabel = (day: string) => {
    const days = Math.round((Date.parse(new Date().toISOString().slice(0, 10)) - Date.parse(day)) / 864e5);
    if (days === 0) return t("home.today");
    if (days === 1) return t("home.yesterday");
    return new Date(day).toLocaleDateString(language, { month: "short", day: "numeric" });
  };
  const chips: [Filter, string, string, number][] = [
    ["all", t("curation.bar.all"), "var(--cream2)", matching.length],
    ["waiting", t("decisions.sessionWaiting"), COLOR.waiting, matching.filter((s) => s.state === "waiting").length],
    [
      "finished",
      t("decisions.sessionState.finished"),
      COLOR.finished,
      matching.filter((s) => s.state === "finished").length,
    ],
  ];
  const set = (next: () => void) => {
    next();
    setPage(0);
  };

  return (
    <div className="mem-list">
      <ReportsModuleBar />
      <div className="sh-tb mem-tb">
        <h1>{t("terminal.sessions")}</h1>
        <span className="meta">
          {shown.length ? `${page * PAGE + 1}–${page * PAGE + part.length} / ${shown.length}` : "0"}
        </span>
        <div className="mem-chips">
          {chips.map(([id, label, color, count]) => (
            <button
              type="button"
              key={id}
              className="mem-chip"
              style={filter === id ? { borderColor: "var(--yellow)" } : undefined}
              onClick={() => set(() => setFilter(id))}
            >
              <i style={{ background: color }} />
              {label}
              <b>{count}</b>
            </button>
          ))}
          <button type="button" className="mem-chip" disabled={page === 0} onClick={() => setPage(page - 1)}>
            ‹
          </button>
          <button
            type="button"
            className="mem-chip"
            disabled={(page + 1) * PAGE >= shown.length}
            onClick={() => setPage(page + 1)}
          >
            ›
          </button>
        </div>
        <input
          className="sh-search"
          type="search"
          placeholder={t("memory.list.filter")}
          value={query}
          onChange={(event) => set(() => setQuery(event.target.value))}
        />
      </div>
      {part.length === 0 && <p className="mem-none">{t("decisions.noSessions")}</p>}
      {part.map((session, index) => (
        <Fragment key={session.id}>
          {(index === 0 || part[index - 1]?.day !== session.day) && (
            <div className="mem-grp">
              {dayLabel(session.day)}
              <small>{part.filter((s) => s.day === session.day).length}</small>
            </div>
          )}
          <SessionRow session={session} onOpen={open} docName={(kind) => kindInfo(kind).label} />
        </Fragment>
      ))}
    </div>
  );
}

function SessionRow({
  session,
  onOpen,
  docName,
}: {
  session: SessionGroup;
  onOpen: (key: string) => void;
  docName: (kind: string) => string;
}) {
  const { t } = useTranslation();
  const name = `${session.ticket ? `${session.ticket} · ` : ""}${session.title}`;
  return (
    // a line is not a button: its label stays selectable, and its chips are buttons of their own
    // biome-ignore lint/a11y/useKeyWithClickEvents: the chips and the main document open from the keyboard too
    // biome-ignore lint/a11y/noStaticElementInteractions: as above
    <div
      className={`mem-row ses${session.state === "waiting" ? " sel" : ""}`}
      onClick={() => !window.getSelection()?.toString() && onOpen(session.main.key)}
    >
      <span className="mem-type" style={{ background: COLOR[session.state] }}>
        {session.id}:{t(`decisions.sessionState.${session.state}`)}
      </span>
      <span className="mem-t" title={name}>
        {name}
      </span>
      <span className="mem-chips ses-docs">
        {session.docs.map((doc) => (
          <button
            type="button"
            key={doc.id}
            className="mem-chip"
            title={doc.envelope.title}
            onClick={(event) => {
              event.stopPropagation();
              onOpen(doc.key);
            }}
          >
            <i style={{ background: doc.state === "waiting" ? COLOR.waiting : "var(--muted)" }} />
            {doc.envelope.kind === "decisions" ? doc.envelope.title : docName(doc.envelope.kind)}
            {doc.state === "waiting" && <b>{t("decisions.sessionState.waiting")}</b>}
          </button>
        ))}
      </span>
      <span className="mem-stamp">
        <b>{session.time}</b>
      </span>
    </div>
  );
}
