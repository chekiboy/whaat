import { Link } from "@tanstack/react-router";
import { CheckCheck, Lock, TriangleAlert } from "lucide-react";
import type { ReportSummary } from "@/client";
import { Badge } from "@/components/ui/badge";
import { useKindInfo } from "@/lib/report-kinds";
import { cn } from "@/lib/utils";

export function ReportCard({ report }: { report: ReportSummary }) {
  const { envelope } = report;
  const kind = useKindInfo()(envelope.kind);
  const meta = [envelope.created_date, envelope.identity, envelope.repo, envelope.ticket].filter(Boolean);

  return (
    <Link
      to="/reports/$key"
      params={{ key: report.key }}
      className="group relative block overflow-hidden sh-paper rounded-sm pl-5 pr-4 py-3 shadow-hard transition-transform hover:-translate-y-0.5 [clip-path:polygon(0_0,calc(100%-14px)_0,100%_14px,100%_100%,0_100%)]"
    >
      <span className={cn("absolute inset-y-0 left-0 w-1.5", kind.stripe)} aria-hidden />
      <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-muted">
        <span title={kind.description}>{kind.label}</span>
        {report.private && (
          <Badge variant="outline" className="gap-1 border-ink-muted/40 text-ink-muted" title="Private: never shared">
            <Lock /> private
          </Badge>
        )}
        {report.state === "applied" && (
          <Badge
            variant="outline"
            className="gap-1 border-stripe-teal text-stripe-teal"
            title="Its decisions were sent"
          >
            <CheckCheck /> applied
          </Badge>
        )}
        {report.warnings.length > 0 && (
          <span title={report.warnings.join("\n")} className="text-stripe-red">
            <TriangleAlert className="size-3.5" />
          </span>
        )}
      </div>
      <h3 className="mt-1 truncate font-heading text-xl font-bold leading-tight" title={envelope.title}>
        {envelope.title}
      </h3>
      <p className="mt-1 truncate font-mono text-xs text-ink-muted" title={report.path}>
        {meta.join(" · ")}
      </p>
    </Link>
  );
}
