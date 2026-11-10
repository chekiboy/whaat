import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { listIdentitiesOptions, listReportsOptions } from "@/client/@tanstack/react-query.gen";
import { tileClassName } from "@/components/nav-tile";
import { ReportCard } from "@/components/report-card";
import { useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { KIND_ORDER, useKindInfo } from "@/lib/report-kinds";

type ListSearch = { kind?: string; identity?: string; shared?: boolean };

export const Route = createFileRoute("/reports/")({
  validateSearch: (search: Record<string, unknown>): ListSearch => ({
    ...(typeof search.kind === "string" ? { kind: search.kind } : {}),
    ...(typeof search.identity === "string" ? { identity: search.identity } : {}),
    ...(search.shared === true || search.shared === "true" ? { shared: true } : {}),
  }),
  component: ReportList,
});

function ReportList() {
  const { t } = useTranslation();
  const kindInfo = useKindInfo();
  usePageHeading(sectionTitle("Reports"), [{ label: t("reports.title") }]);
  const { kind, identity, shared } = Route.useSearch();
  const { data: everything, error, isPending } = useQuery(listReportsOptions());
  const identities = useQuery(listIdentitiesOptions());

  if (isPending) return <p className="font-mono text-muted-foreground">{t("reports.loading")}</p>;
  if (error)
    return <p className="font-mono text-destructive">{t("reports.loadError", { error: JSON.stringify(error) })}</p>;

  const unowned = everything.filter((report) => !report.envelope.identity);
  const data = shared ? unowned : identity ? everything.filter((r) => r.envelope.identity === identity) : everything;
  const owner: ListSearch = shared ? { shared: true } : identity ? { identity } : {};
  const counts = new Map<string, number>();
  for (const report of data) counts.set(report.envelope.kind, (counts.get(report.envelope.kind) ?? 0) + 1);
  const kinds = [
    ...KIND_ORDER.filter((k) => counts.has(k)),
    ...[...counts.keys()].filter((k) => !KIND_ORDER.includes(k)),
  ];
  const shown = kind ? data.filter((report) => report.envelope.kind === kind) : data;

  return (
    <section>
      {identities.data && identities.data.length > 1 && (
        <nav className="mb-3 flex flex-wrap gap-2" aria-label={t("reports.byIdentity")}>
          <KindTile
            label={t("reports.everyone")}
            count={null}
            active={!identity && !shared}
            search={kind ? { kind } : {}}
          />
          {identities.data.map((who) => (
            <KindTile
              key={who.id}
              label={who.id}
              title={t("reports.identityCount", { count: who.report_count, private: who.private_report_count })}
              count={who.report_count}
              active={identity === who.id}
              search={{ ...(kind ? { kind } : {}), identity: who.id }}
            />
          ))}
          {unowned.length > 0 && (
            <KindTile
              label={t("reports.shared")}
              title={t("reports.sharedHint")}
              count={unowned.length}
              active={!!shared}
              search={{ ...(kind ? { kind } : {}), shared: true }}
            />
          )}
        </nav>
      )}
      <nav className="mb-6 flex flex-wrap gap-2" aria-label={t("reports.byKind")}>
        <KindTile label={t("reports.all")} count={data.length} active={!kind} search={owner} />
        {kinds.map((k) => (
          <KindTile
            key={k}
            label={kindInfo(k).label}
            title={kindInfo(k).description}
            count={counts.get(k) ?? 0}
            active={kind === k}
            search={{ kind: k, ...owner }}
          />
        ))}
      </nav>
      <ul className="grid gap-4 md:grid-cols-2" aria-label={t("reports.title")}>
        {shown.map((report) => (
          <li key={report.id}>
            <ReportCard report={report} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function KindTile(props: { label: string; title?: string; count: number | null; active: boolean; search: ListSearch }) {
  return (
    <Link to="/reports" search={props.search} title={props.title} className={tileClassName(props.active)}>
      {props.label}
      {props.count !== null && <b className="text-base text-foreground">{props.count}</b>}
    </Link>
  );
}
