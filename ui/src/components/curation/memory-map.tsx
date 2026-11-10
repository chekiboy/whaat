import type { MemoryMap as MemoryMapData } from "@/client";
import { useTranslation } from "@/i18n";

export const ACTIONS = ["delete", "merge", "move", "split", "trim", "retrigger", "verify", "fix"] as const;

const range = (lo: number, hi: number) => (lo !== hi ? `${lo}–${hi}` : `${hi}`);

/** The memory map at the top of the page: one cell per memory file in three level
    columns, coloured by the first row that names it; a click jumps to that file's proposal. Sent rows tick their
    files and count in their dir's header. */
export function MemoryMap({
  map,
  sentFiles,
  onPick,
}: {
  map: MemoryMapData;
  sentFiles: Set<string>;
  onPick: (file: string) => void;
}) {
  const { t } = useTranslation();
  const levels = (["global", "project", "repo"] as const)
    .map((level) => ({ level, dirs: map.dirs.filter((dir) => dir.level === level) }))
    .filter((group) => group.dirs.length > 0);
  return (
    <section className="cur-map sh-paper">
      <div className="cur-maphead">
        <div>
          <h2>{t("curation.map.title")}</h2>
          <p className="muted">{t("curation.map.explain")}</p>
        </div>
        <div className="cur-total">
          <span>{map.total_before}</span>
          <em>{t("curation.map.filesNow")}</em>
          <span className="arrow">→</span>
          <span className="after">{range(map.total_lo, map.total_hi)}</span>
          <em>{t("curation.map.after")}</em>
        </div>
      </div>
      <div className="cur-legend">
        {ACTIONS.map((action) => (
          <span key={action}>
            <i className={`cur-cell a-${action}`} />
            {action}
          </span>
        ))}
        <span>
          <i className="cur-cell" />
          {t("curation.map.unchanged")}
        </span>
        {sentFiles.size > 0 && (
          <span>
            <i className="cur-cell a-trim sent" />
            {t("curation.map.sentLegend")}
          </span>
        )}
      </div>
      <div className="cur-levels">
        {levels.map(({ level, dirs }) => (
          <div key={level} className="cur-level">
            <h3>{level}</h3>
            {dirs.map((dir) => {
              const sent = dir.cells.filter((cell) => sentFiles.has(cell.file)).length;
              return (
                <div key={dir.dir} className="cur-dir">
                  <div className="cur-dirhead">
                    <span>{dir.dir || "(global)"}</span>
                    <span className="count">
                      {sent > 0 && <span className="dirsent">{t("curation.map.sentPrefix", { count: sent })}</span>}
                      {dir.before}
                      <em>→</em>
                      {range(dir.after_lo, dir.after_hi)}
                    </span>
                  </div>
                  <div className="cur-cells">
                    {dir.cells.map((cell) => (
                      <button
                        type="button"
                        key={cell.file}
                        className={`cur-cell${cell.action ? ` a-${cell.action}` : ""}${sentFiles.has(cell.file) ? " sent" : ""}`}
                        title={`${cell.file}${cell.action ? ` — ${cell.action}` : ""}`}
                        onClick={() => onPick(cell.file)}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
