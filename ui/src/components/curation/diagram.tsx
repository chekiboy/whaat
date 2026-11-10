import { Fragment } from "react";

import type { CurationRow, RowFigure } from "@/client";
import { useTranslation } from "@/i18n";

/** The change drawn for one proposal, followed by the sentence on what
    that kind of change does; a row with several actions draws each in the order they run. */
export function Diagram({ row, figure }: { row: CurationRow; figure: RowFigure | undefined }) {
  const { t } = useTranslation();
  const name = figure?.name ?? row.file.replace(/[`*]/g, "");
  return row.actions.map((action) => (
    <Fragment key={action}>
      <Figure action={action} figure={figure} name={name} />
      <p className="cur-hint">{t(`curation.hint.${action}` as "curation.hint.fix")}</p>
    </Fragment>
  ));
}

function short(name: string): string {
  return name.includes("_") ? name.split("_").slice(1).join("_").replaceAll("_", " ") : name;
}

function Node({ label, kind = "" }: { label: string; kind?: string }) {
  return (
    <span className={`cur-node ${kind}`} title={label}>
      {short(label) || label}
    </span>
  );
}

const Flow = () => <span className="cur-flow" />;

function Figure({
  action,
  figure,
  name,
}: {
  action: CurationRow["actions"][number];
  figure: RowFigure | undefined;
  name: string;
}) {
  const { t } = useTranslation();
  switch (action) {
    case "delete":
      return (
        <div className="cur-dia">
          <Node label={name} />
          <Flow />
          <span className="cur-node ghost">{t("curation.diagram.deleted")}</span>
        </div>
      );
    case "merge": {
      const into = figure?.into ?? t("curation.diagram.target");
      return (
        <div className="cur-dia">
          <div className="cur-stack">
            <Node label={name} kind="src" />
            <Node label={into} />
          </div>
          <Flow />
          <Node label={into} kind="result" />
        </div>
      );
    }
    case "move": {
      const from = figure?.files.length ? (figure.from_dir ?? "") : null;
      const dest = figure?.dest ?? null;
      const here = from === null ? null : levelOf(from);
      const there = dest === null ? null : levelOf(dest);
      const where = (dir: string | null) => (dir === null ? "?" : dir ? `${dir}/` : "global");
      return (
        <div className="cur-dia move">
          <div className="cur-dia">
            <span className="cur-node dirnode">{where(from)}</span>
            <Flow />
            <span className="cur-node dirnode result">{where(dest)}</span>
          </div>
          <div className="cur-track">
            {(["global", "project", "repo"] as const).map((level) => (
              <span key={level} className={`cur-lvl${level === here ? " from" : ""}${level === there ? " to" : ""}`}>
                <i />
                {level}
                {level === there && dest ? <small>{dest}</small> : null}
              </span>
            ))}
          </div>
        </div>
      );
    }
    case "trim":
    case "split": {
      const bar = figure?.size && figure.budget ? <SizeBar size={figure.size} budget={figure.budget} /> : null;
      if (action === "split")
        return (
          <>
            <div className="cur-dia">
              <Node label={name} />
              <Flow />
              <div className="cur-stack">
                <Node label={`${name} · ${t("curation.diagram.part", { n: 1 })}`} kind="result" />
                <Node label={`${name} · ${t("curation.diagram.part", { n: 2 })}`} kind="result" />
              </div>
            </div>
            {bar}
          </>
        );
      return (
        <>
          <div className="cur-dia">
            <Node label={name} />
            <Flow />
            <Node label={name} kind="result slim" />
          </div>
          {bar}
        </>
      );
    }
    case "verify":
      return (
        <div className="cur-dia">
          <Node label={name} kind="scan" />
        </div>
      );
    case "retrigger":
      return (
        <div className="cur-dia retrig">
          <div className="cur-tline">
            <small>{t("curation.diagram.now")}</small>
            {figure?.now ?? "—"}
          </div>
          <Flow />
          <div className="cur-tline result">
            <small>{t("curation.diagram.after")}</small>
            {figure?.after ?? ""}
          </div>
        </div>
      );
    case "fix": {
      const count = figure?.files.length ?? 0;
      const label = count > 1 ? t("curation.diagram.files", { count }) : name;
      return (
        <div className="cur-dia">
          <Node label={label} />
          <Flow />
          <Node label={label} kind="result fixed" />
        </div>
      );
    }
    default:
      return null;
  }
}

function SizeBar({ size, budget }: { size: number; budget: number }) {
  const { t } = useTranslation();
  const scale = Math.max(size, budget) * 1.08;
  return (
    <div className="cur-size">
      <div className="cur-bar" style={{ width: `${((size / scale) * 100).toFixed(1)}%` }}>
        <b>{size}</b>
      </div>
      <div className="cur-budget" style={{ left: `${((budget / scale) * 100).toFixed(1)}%` }}>
        <span>{t("curation.diagram.budget", { n: budget })}</span>
      </div>
    </div>
  );
}

export function levelOf(dir: string): "global" | "project" | "repo" {
  if (!dir) return "global";
  return dir.includes("/") ? "repo" : "project";
}
