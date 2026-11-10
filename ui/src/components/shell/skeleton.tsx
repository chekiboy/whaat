import { useTranslation } from "@/i18n";

/** Placeholder rows while a view loads, so the frame keeps its shape instead of showing a line of text. */
export function Skeleton({ rows = 10 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <div className="sh-skel" role="status" aria-busy="true" aria-label={t("common.loading")}>
      {Array.from({ length: rows }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: the rows are identical placeholders
        <span key={i} className="sh-skel-row" style={{ width: `${70 + ((i * 37) % 30)}%` }} />
      ))}
    </div>
  );
}
