import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ReportSummary } from "@/client";
import { listReportsOptions } from "@/client/@tanstack/react-query.gen";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { useTranslation } from "@/i18n";
import { useKindInfo } from "@/lib/report-kinds";
import { groupSessions } from "@/lib/sessions";

/** The Reports module's own bar: the open report's session with its documents, then the ways in. */
export function ReportsModuleBar({ session, current }: { session?: string | null; current?: string }) {
  const { t } = useTranslation();
  const kindInfo = useKindInfo();
  const { data } = useQuery(listReportsOptions());
  const groups = groupSessions(data ?? []);
  const mine = session ? groups.find((group) => group.id === session) : undefined;
  const docName = (doc: ReportSummary) =>
    doc.envelope.kind === "decisions" ? doc.envelope.title : kindInfo(doc.envelope.kind).label;
  return (
    <ModuleBar>
      {mine && (
        <ModuleBarSection title={t("decisions.thisSession")}>
          {mine.docs.map((doc) => (
            <Link
              key={doc.id}
              to="/reports/$key"
              params={{ key: doc.key }}
              className={`sh-item${doc.key === current ? " on" : ""}`}
              title={doc.envelope.title}
            >
              {docName(doc)}
              {doc.state === "waiting" && <span className="c">{t("decisions.sessionState.waiting")}</span>}
            </Link>
          ))}
        </ModuleBarSection>
      )}
      <ModuleBarSection title={t("shell.reports")}>
        <Link to="/reports/sessions" className="sh-item" activeProps={{ className: "sh-item on" }}>
          {t("terminal.sessions")}
          <span className="c">{groups.length}</span>
        </Link>
        <Link
          to="/reports"
          search={{}}
          className="sh-item"
          activeOptions={{ exact: true, includeSearch: false }}
          activeProps={{ className: "sh-item on" }}
        >
          {t("reports.allReports")}
          <span className="c">{data?.length ?? ""}</span>
        </Link>
      </ModuleBarSection>
    </ModuleBar>
  );
}
