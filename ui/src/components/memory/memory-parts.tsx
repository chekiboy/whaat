import type { CardValidity, MemoryCard } from "@/client";
import { useTranslation } from "@/i18n";

export const LAYER_ORDER = ["core", "personal", "global", "project", "repo"];
const LAYERS = ["core", "personal", "global", "project", "repo"] as const;
const LEVELS = ["certain", "likely", "uncertain", "stale", "history", "unscored"] as const;
const HALFLIFE_TYPES = ["project", "reference", "feedback", "user"] as const;
const isOne = <T extends string>(list: readonly T[], value: string): value is T => list.includes(value as T);

/** The names of the layers and the meanings of the levels in the chosen language; a value we do not know (a new
    layer) is shown as it is. */
export function useMemoryLabels(): { layer: (key: string) => string; level: (key: string) => string } {
  const { t } = useTranslation();
  return {
    layer: (key) => (isOne(LAYERS, key) ? t(`memory.layers.${key}`) : key),
    level: (key) => (isOne(LEVELS, key) ? t(`memory.levelMeans.${key}`) : ""),
  };
}
export const TYPE_COLOUR: Record<string, string> = {
  feedback: "var(--orange)",
  project: "var(--teal)",
  reference: "var(--blue)",
  user: "var(--red)",
};
export const OUTCOMES = ["held", "misled", "irrelevant"] as const;
export const LEVEL_ORDER = ["certain", "likely", "uncertain", "stale", "history", "unscored"];

export function cardLevel(memory: MemoryCard): string {
  return (memory.validity && levelOf(memory.validity)) || "unscored";
}

export function levelOf(validity: CardValidity): string | null {
  return validity.history ? "history" : (validity.level ?? null);
}

export function LevelStamp({ validity }: { validity: CardValidity | null }) {
  const level = validity && levelOf(validity);
  const labels = useMemoryLabels();
  if (!validity || !level) {
    return <span />;
  }
  return (
    <span className={`vstamp ${level}`} title={labels.level(level)}>
      {level}
      {validity.score != null && ` ${validity.score.toFixed(2)}`}
    </span>
  );
}

/* The halflife of the pilot (distilled/pilot), by the memory's type: an estimate, shown only on the opened card. */
export const HALFLIFE: Record<(typeof HALFLIFE_TYPES)[number], number> = {
  project: 30,
  reference: 90,
  feedback: 120,
  user: 365,
};
export const SOURCE_WEIGHT: Record<string, number> = { measured: 1, "user-decision": 1, inference: 0.75 };

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mf">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function MemoryMeta({ memory }: { memory: MemoryCard }) {
  const { t } = useTranslation();
  const fm = memory.frontmatter;
  const v = memory.validity ?? null;
  const level = v ? levelOf(v) : null;
  const when = (fm.when ?? "")
    .replace(/^\[|\]$/g, "")
    .split(",")
    .map((w) => w.trim())
    .filter(Boolean);
  const dir = memory.path.includes("/") ? memory.path.slice(0, memory.path.lastIndexOf("/")) : t("memory.meta.root");
  const halfType = fm.type && isOne(HALFLIFE_TYPES, fm.type) ? fm.type : null;
  const halfDays = halfType ? HALFLIFE[halfType] : undefined;
  const halfScore =
    halfDays && v?.age_days != null
      ? (SOURCE_WEIGHT[v.source ?? ""] ?? 0.9) * 0.5 ** (v.age_days / halfDays)
      : undefined;
  return (
    <div className="mem-meta">
      <dl>
        <h5>{t("memory.meta.memory")}</h5>
        <Field label={t("memory.meta.name")}>{fm.name ?? "—"}</Field>
        <Field label={t("memory.meta.folder")}>{dir}</Field>
        {when.length > 0 && (
          <Field label={t("memory.meta.when")}>
            {when.map((w) => (
              <span key={w} className="mchip">
                {w}
              </span>
            ))}
          </Field>
        )}
        {fm.supersedes && <Field label={t("memory.meta.supersedes")}>{fm.supersedes}</Field>}
        {fm.reach && <Field label={t("memory.meta.reach")}>{fm.reach}</Field>}
      </dl>
      <dl>
        <h5>{t("memory.meta.trust")}</h5>
        {!v && <p className="mnote">{t("memory.meta.unscoredNote")}</p>}
        {v && (
          <Field label={t("memory.meta.validity")}>
            {level ? <span className={`vstamp ${level}`}>{level}</span> : t("memory.meta.noDate")}
            {v.history
              ? ` → ${v.history}`
              : v.score != null && ` ${t("memory.meta.scoreAge", { score: v.score.toFixed(2), days: v.age_days })}`}
          </Field>
        )}
        <Field label={t("memory.meta.source")}>{fm.source ?? v?.source ?? t("memory.meta.noSource")}</Field>
        {fm.confirmed && <Field label={t("memory.meta.confirmed")}>{fm.confirmed}</Field>}
        {v && (
          <Field label={t("memory.meta.truthness")}>
            {OUTCOMES.map((name) => (
              <span key={name} className={`mcount ${name}`} title={t("memory.meta.sinceChange", { name })}>
                {name} <b className="n">{v.outcomes?.[name] ?? 0}</b>
              </span>
            ))}
          </Field>
        )}
        {halfType && halfDays && (
          <Field label={t("memory.meta.halflife")}>
            {t("memory.meta.halflifeValue", { days: halfDays, label: t(`memory.halflife.${halfType}`) })}
            {halfScore != null && t("memory.meta.halflifeScore", { score: halfScore.toFixed(2) })}
            <span className="mest">{t("memory.meta.estimated")}</span>
          </Field>
        )}
      </dl>
    </div>
  );
}

/* The memory's text with its light markdown: **bold**, `code`, "- " items and [[links]] as chips that search for the
   memory they name. */
export function inline(text: string, onLink: (name: string) => void, linkTitle = ""): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[\[([^\]]+)\]\]/g;
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    const at = m.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    if (m[1]) parts.push(<b key={at}>{m[1]}</b>);
    else if (m[2]) parts.push(<code key={at}>{m[2]}</code>);
    else if (m[3]) {
      const name = m[3];
      parts.push(
        <button key={at} type="button" className="mlink" onClick={() => onLink(name)} title={linkTitle}>
          {name}
        </button>,
      );
    }
    last = at + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function MemoryBody({ body, onLink }: { body: string; onLink: (name: string) => void }) {
  const { t } = useTranslation();
  const linkTitle = t("memory.meta.searchMemory");
  const blocks: React.ReactNode[] = [];
  let items: React.ReactNode[] = [];
  let n = 0;
  const flush = () => {
    if (items.length) {
      blocks.push(<ul key={`b${n++}`}>{items}</ul>);
      items = [];
    }
  };
  for (const line of body.split("\n")) {
    const item = line.match(/^\s*[-*]\s+(.*)$/);
    if (item?.[1] != null) {
      items.push(<li key={`b${n++}`}>{inline(item[1], onLink, linkTitle)}</li>);
      continue;
    }
    flush();
    if (line.trim()) blocks.push(<p key={`b${n++}`}>{inline(line, onLink, linkTitle)}</p>);
  }
  flush();
  return <div className="narrative mem-body">{blocks}</div>;
}

export function nameOf(memory: MemoryCard): string {
  return memory.frontmatter.name ?? memory.path.split("/").pop()?.replace(/\.md$/, "") ?? memory.path;
}
