import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import type { MemoryCard, ReportSummary } from "@/client";
import { browseMemoriesOptions, listReportsOptions, memoryAnalysisOptions } from "@/client/@tanstack/react-query.gen";
import { cardLevel, LEVEL_ORDER, nameOf, useMemoryLabels } from "@/components/memory/memory-parts";
import { LEVEL_COLOUR } from "@/components/memory/memory-split";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { Skeleton } from "@/components/shell/skeleton";
import { useLanguage, useTranslation } from "@/i18n";
import { usePageHeading } from "@/lib/breadcrumb";
import { usePersona } from "@/lib/persona";
import { TERMINAL_COMMAND } from "@/lib/terminal";
import "@/styles/overview.css";

export const Route = createFileRoute("/")({
  component: Home,
});

/* Each kind's colour, and its label: a kind name as it is, or a key of home.kinds. */
const KIND: Record<string, [string, string]> = {
  review: ["var(--stripe-blue)", "review"],
  investigation: ["var(--stripe-teal)", "investigation"],
  development: ["var(--stripe-orange)", "development"],
  "memory-curation": ["var(--stripe-violet)", "curation"],
  "session-report": ["var(--stripe-yellow)", "session"],
  journal: ["var(--stripe-red)", "journal"],
};
const MEMORY_EVENT: [string, string] = ["var(--phos)", "memory"];
const TRANSLATED_KINDS = ["curation", "journal", "memory"] as const;

type Event = { day: string; kind: string; title: string; sub: string; reportKey?: string; memory?: string };

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function kindOf(kind: string): [string, string] {
  return kind === "memory" ? MEMORY_EVENT : (KIND[kind] ?? ["var(--muted)", kind]);
}

/* The home: who the persona is, what happened, what waits for you. */
function Home() {
  usePageHeading("Whaat?!");
  const { persona } = usePersona();
  const { t } = useTranslation();
  const { language } = useLanguage();
  const labels = useMemoryLabels();
  const dayName = (day: string) => {
    const diff = Math.round((Date.parse(today()) - Date.parse(day)) / 864e5);
    if (diff === 0) return t("home.today");
    if (diff === 1) return t("home.yesterday");
    return new Date(`${day}T12:00:00`).toLocaleDateString(language, { month: "short", day: "numeric" });
  };
  const kindLabel = (key: string) =>
    (TRANSLATED_KINDS as readonly string[]).includes(key)
      ? t(`home.kinds.${key as (typeof TRANSLATED_KINDS)[number]}`)
      : key;
  const memories = useQuery(browseMemoriesOptions());
  const reports = useQuery(listReportsOptions({ query: persona ? { identity: persona } : {} }));
  const analysis = useQuery({ ...memoryAnalysisOptions({ query: { identity: persona ?? "" } }), retry: false });
  const who = memories.data?.find((x) => x.identity === persona);
  const mems: (MemoryCard & { layer: string; dir: string })[] = (who?.layers ?? []).flatMap((l) =>
    l.memories.map((m) => ({ ...m, layer: l.layer, dir: l.dir })),
  );
  const reps: ReportSummary[] = reports.data ?? [];
  const levels = new Map<string, number>();
  for (const m of mems) levels.set(cardLevel(m), (levels.get(cardLevel(m)) ?? 0) + 1);
  const core = mems.filter((m) => m.layer === "core");
  const self = core.find((m) => m.path.includes("self")) ?? core[0];
  const line = self ? (self.body.replace(/\*\*/g, "").split(/(?<=[.;])\s/)[0] ?? "") : "";

  const events: Event[] = [
    ...reps
      .filter((r) => r.envelope.created_date)
      .map((r) => ({
        day: r.envelope.created_date ?? "",
        kind: r.envelope.kind,
        title: r.envelope.title,
        sub: [r.envelope.repo, r.envelope.ticket].filter(Boolean).join(" · "),
        reportKey: r.key,
      })),
    ...mems
      .filter((m) => m.frontmatter.confirmed)
      .map((m) => ({
        day: String(m.frontmatter.confirmed).slice(0, 10),
        kind: "memory",
        title: m.frontmatter.description ?? nameOf(m),
        sub: m.dir && m.dir !== "." ? m.dir : labels.layer(m.layer),
        memory: m.path,
      })),
  ];
  const days = new Map<string, Event[]>();
  for (const e of events) days.set(e.day, [...(days.get(e.day) ?? []), e]);
  const order = [...days.keys()].sort().reverse().slice(0, 8);

  const check = (levels.get("uncertain") ?? 0) + (levels.get("stale") ?? 0);
  const todo: { n: number; title: string; text: string; level: string }[] = [
    {
      n: check,
      title: t("home.checkTitle"),
      text: t("home.checkText"),
      level: "uncertain",
    },
    {
      n: levels.get("likely") ?? 0,
      title: t("home.agingTitle"),
      text: t("home.agingText"),
      level: "likely",
    },
  ];
  const open = todo.filter((item) => item.n > 0);

  if (!persona) return null;
  if (memories.isPending) return <Skeleton rows={14} />;
  return (
    <div className="sh-view ov">
      <ModuleBar>
        <ModuleBarSection title={t("home.title")}>
          {[
            ["ov-who", t("home.who")],
            ["ov-past", t("home.past")],
            ["ov-next", t("home.next")],
          ].map(([id, label]) => (
            <button
              type="button"
              key={id}
              className="sh-item"
              onClick={() => document.getElementById(id ?? "")?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              {label}
            </button>
          ))}
        </ModuleBarSection>
      </ModuleBar>

      <div className="sh-tb">
        <h1>{t("home.title")}</h1>
        <span className="meta">{persona}</span>
        <span className="grow" />
        <Link to="/terminal" className="ov-tbterm">
          ▸ {TERMINAL_COMMAND}
        </Link>
      </div>
      <section className="ov-who" id="ov-who">
        <div className="ov-who-main">
          <span className="ov-bigav">{persona[0]?.toUpperCase()}</span>
          <div>
            <h1>{persona}</h1>
            {line ? <blockquote>{line}</blockquote> : <blockquote className="dim">{t("home.noCore")}</blockquote>}
            {core.length > 0 && (
              <div className="ov-core">
                <span>core</span>
                {core.map((m) => (
                  <Link
                    key={m.path}
                    to="/memory"
                    search={{ m: m.path }}
                    className="ov-cc"
                    title={m.frontmatter.description}
                  >
                    {nameOf(m)
                      .replace(/^(user|feedback)[_-]/, "")
                      .replace(/[_-]+/g, " ")}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="ov-health">
          <div className="ov-hrow">
            <b>{mems.length}</b>
            <span>{t("home.memories")}</span>
            <b>{who?.layers.length ?? 0}</b>
            <span>{t("home.folders")}</span>
            <b>{reps.length}</b>
            <span>{t("home.reports")}</span>
            {analysis.data && (
              <Link to="/memory" search={{ view: "analysis" }} className="ov-hlink">
                {t("home.analysisLink")}
              </Link>
            )}
          </div>
          <div className="ov-hbar">
            {LEVEL_ORDER.filter((l) => levels.get(l)).map((l) => (
              <Link
                key={l}
                to="/memory"
                search={{ level: l }}
                style={{ flex: levels.get(l), background: LEVEL_COLOUR[l] }}
                title={`${l}: ${levels.get(l)} · ${labels.level(l)}`}
              />
            ))}
          </div>
          <div className="ov-legend">
            {LEVEL_ORDER.filter((l) => levels.get(l)).map((l) => (
              <Link key={l} to="/memory" search={{ level: l }} title={labels.level(l)}>
                <i style={{ background: LEVEL_COLOUR[l] }} />
                {l} <b>{levels.get(l)}</b>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="ov-cols">
        <section id="ov-past" className="ov-pane">
          <h2 className="ov-ph">
            {t("home.past")}
            <small>{t("home.lastDays", { count: order.length })}</small>
          </h2>
          <div className="ov-scroll">
            <div className="ov-timeline">
              {order.length === 0 && <p className="ov-none">{t("home.noPast")}</p>}
              {order.map((day) => {
                const list = days.get(day) ?? [];
                const byKind = new Map<string, number>();
                for (const e of list) byKind.set(e.kind, (byKind.get(e.kind) ?? 0) + 1);
                return (
                  <div key={day} className="ov-day">
                    <div className="ov-dh">
                      <b>{dayName(day)}</b>
                      <span>{day}</span>
                      <span className="ov-dk">
                        {[...byKind].map(([k, n], i) => (
                          <span key={k}>
                            {i > 0 && " · "}
                            <i style={{ background: kindOf(k)[0] }} />
                            {n} {kindLabel(kindOf(k)[1])}
                          </span>
                        ))}
                      </span>
                    </div>
                    {list.slice(0, 4).map((e) => {
                      const [colour, label] = kindOf(e.kind);
                      const body = (
                        <>
                          <span className="ov-evk" style={{ background: colour }}>
                            {kindLabel(label)}
                          </span>
                          <span className="ov-evt" title={e.title}>
                            {e.title}
                          </span>
                          <span className="ov-evs">{e.sub}</span>
                        </>
                      );
                      return e.reportKey ? (
                        <Link key={e.reportKey} to="/reports/$key" params={{ key: e.reportKey }} className="ov-ev">
                          {body}
                        </Link>
                      ) : (
                        <Link key={e.memory} to="/memory" search={{ m: e.memory }} className="ov-ev">
                          {body}
                        </Link>
                      );
                    })}
                    {list.length > 4 && <div className="ov-more">{t("home.more", { count: list.length - 4 })}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section id="ov-next" className="ov-pane">
          <h2 className="ov-ph">{t("home.next")}</h2>
          <div className="ov-scroll">
            {mems.length === 0 && (
              // an identity with no memory yet starts by bringing in what exists
              <Link
                to="/settings/identities/$identity/migrate"
                params={{ identity: persona }}
                className="ov-todo ov-migrate"
              >
                <b>↧</b>
                <div>
                  <h4>{t("migrate.title")}</h4>
                  <p>{t("migrate.homeText")}</p>
                </div>
                <span className="arr">›</span>
              </Link>
            )}
            {open.map((item) => (
              <Link key={item.title} to="/memory" search={{ level: item.level }} className="ov-todo">
                <b>{item.n}</b>
                <div>
                  <h4>{item.title}</h4>
                  <p>{item.text}</p>
                </div>
                <span className="arr">›</span>
              </Link>
            ))}
            {open.length < todo.length && (
              <div className="ov-clear">
                {todo
                  .filter((item) => item.n === 0)
                  .map((item) => (
                    <span key={item.title}>✓ 0 {item.title}</span>
                  ))}
              </div>
            )}
            <p className="ov-later">{t("home.decisionsLater")}</p>
            <h3 className="ov-sub">{t("home.start")}</h3>
            <Link to="/terminal" className="ov-term">
              <span>▸</span> {t("home.startCommand", { command: TERMINAL_COMMAND })}
              <em>{persona}</em>
            </Link>
            <p className="ov-k">
              <kbd>⌘K</kbd> {t("home.searchHint")}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
