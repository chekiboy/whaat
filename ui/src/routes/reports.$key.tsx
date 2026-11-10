import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import type { ReportDetail } from "@/client";
import { getReportByKeyOptions } from "@/client/@tanstack/react-query.gen";
import { Pins, ReportFrame } from "@/components/report-frame";
import { useTranslation } from "@/i18n";
import { useKindInfo } from "@/lib/report-kinds";
import { viewOf } from "@/report-views/registry";

export const Route = createFileRoute("/reports/$key")({
  component: ReportPage,
});

function ReportPage() {
  const { key } = Route.useParams();
  const { data, error, isPending } = useQuery(getReportByKeyOptions({ path: { key } }));
  const { t } = useTranslation();

  return (
    <article>
      <Link
        to="/reports"
        search={{}}
        className="mb-6 inline-flex items-center gap-1 font-mono text-xs uppercase text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> {t("reports.allReports")}
      </Link>
      {isPending && <p className="font-mono text-muted-foreground">{t("reports.loadingOne")}</p>}
      {error && (
        <p className="font-mono text-destructive">{t("reports.loadErrorOne", { error: JSON.stringify(error) })}</p>
      )}
      {data && <Report report={data} />}
    </article>
  );
}

function Report({ report }: { report: ReportDetail }) {
  const view = viewOf(report.body);
  const kind = useKindInfo()(report.envelope.kind);
  const { t } = useTranslation();
  return (
    <ReportFrame
      crumbs={[
        { label: t("reports.title"), to: "/reports" },
        { label: `${kind.label}${report.private ? t("reports.private") : ""}` },
      ]}
      title={report.envelope.title}
      source={report.id}
    >
      <Pins envelope={report.envelope} path={report.path} extra={view.pins?.(report.body) ?? []} />
      {view.render(report.body, report)}
    </ReportFrame>
  );
}
