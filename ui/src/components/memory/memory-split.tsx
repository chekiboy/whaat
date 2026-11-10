import { useEffect, useRef, useState } from "react";
import type { MemoryCard } from "@/client";
import {
  cardLevel,
  MemoryBody,
  MemoryMeta,
  nameOf,
  TYPE_COLOUR,
  useMemoryLabels,
} from "@/components/memory/memory-parts";
import { useTranslation } from "@/i18n";
import "@/styles/report.css";
import "@/styles/memory.css";

export type Placed = MemoryCard & { layer: string; dir: string };

const WIDTH_KEY = "whaat-detail-width";
const MIN_DETAIL = 320;
const MIN_LIST = 380;

export const LEVEL_COLOUR: Record<string, string> = {
  certain: "#2f927b",
  likely: "#2e78c2",
  uncertain: "#c98a06",
  stale: "#e0442b",
  history: "#9a8f7a",
  unscored: "#9a8f7a",
};

function storedWidth(key: string): number | null {
  try {
    const width = Number(localStorage.getItem(key));
    return width > 0 ? width : null;
  } catch {
    return null;
  }
}

export function groupOf(memory: Placed, layerName: (layer: string) => string): string {
  return memory.layer === "project" || memory.layer === "repo" ? memory.dir : layerName(memory.layer);
}

function Row({ memory, selected, onSelect }: { memory: Placed; selected: boolean; onSelect: () => void }) {
  const labels = useMemoryLabels();
  const type = memory.frontmatter.type ?? "–";
  const level = cardLevel(memory);
  const score = memory.validity?.score;
  return (
    <button
      type="button"
      className={`mem-row${selected ? " sel" : ""}${level === "history" ? " hist" : ""}`}
      data-path={memory.path}
      onClick={onSelect}
    >
      <span className="mem-type" style={{ background: TYPE_COLOUR[type] ?? "var(--muted)" }}>
        {type}
      </span>
      <span className="mem-t" title={memory.frontmatter.description ?? nameOf(memory)}>
        {memory.frontmatter.description ?? nameOf(memory)}
      </span>
      <span className="mem-p" title={memory.path}>
        {memory.path}
      </span>
      <span className="mem-stamp" style={{ color: LEVEL_COLOUR[level] }} title={labels.level(level)}>
        {level}
        {score != null && level !== "history" && <b>{score.toFixed(2)}</b>}
      </span>
    </button>
  );
}

/** The paper sheet of one memory: its type, level, name, path, metadata and text. */
export function MemorySheet({ memory, onLink }: { memory: MemoryCard; onLink: (name: string) => void }) {
  const type = memory.frontmatter.type ?? "–";
  const level = cardLevel(memory);
  const labels = useMemoryLabels();
  return (
    <div className="mem-sheet sh-paper">
      <span className="mem-type" style={{ background: TYPE_COLOUR[type] ?? "var(--muted)" }}>
        {type}
      </span>
      <span className="mem-stamp" style={{ color: LEVEL_COLOUR[level] }} title={labels.level(level)}>
        {level}
      </span>
      <h2>
        {nameOf(memory)
          .replace(/^(feedback|project|reference|user)[_-]/, "")
          .replace(/[_-]+/g, " ")}
      </h2>
      <div className="mem-path">{memory.path}</div>
      <MemoryMeta memory={memory} />
      <MemoryBody body={memory.body} onLink={onLink} />
    </div>
  );
}

/** The details pane's frame: a bar with its title, the key hint and the close button, and a scrolling body. */
export function DetailShell({
  onClose,
  hint,
  children,
}: {
  onClose: () => void;
  hint?: string;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <aside className="mem-detail">
      <div className="mem-dtop">
        <span className="t">{t("memory.detail.title")}</span>
        {hint && <kbd>{hint}</kbd>}
        <button type="button" className="mem-x" onClick={onClose} title={t("memory.detail.close")}>
          ✕
        </button>
      </div>
      <div className="mem-dbody rp">{children}</div>
    </aside>
  );
}

/** The details width: a share of the pane by default (the list 65%, a drawing 35%), dragged on the
    grip and remembered under its own key. */
export function useDetailWidth(
  split: React.RefObject<HTMLDivElement | null>,
  { key = WIDTH_KEY, share = 65 }: { key?: string; share?: number } = {},
) {
  const [width, setWidth] = useState<number | null>(() => storedWidth(key));
  const [dragging, setDragging] = useState(false);
  const startDrag = (e: React.PointerEvent<HTMLButtonElement>) => {
    const box = split.current?.getBoundingClientRect();
    if (!box) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
    const clamp = (x: number) => Math.round(Math.max(MIN_DETAIL, Math.min(box.width - MIN_LIST, box.right - x)));
    const move = (ev: PointerEvent) => setWidth(clamp(ev.clientX));
    const up = (ev: PointerEvent) => {
      const final = clamp(ev.clientX);
      setWidth(final);
      setDragging(false);
      try {
        localStorage.setItem(key, String(final));
      } catch {
        /* the width still holds for this tab */
      }
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const resetWidth = () => {
    setWidth(null);
    try {
      localStorage.removeItem(key);
    } catch {
      /* nothing remembered */
    }
  };
  const detail = width != null ? `${width}px` : `min(max(${MIN_DETAIL}px, ${share}%), calc(100% - ${MIN_LIST}px))`;
  return { dragging, startDrag, resetWidth, detail };
}

export function Grip({
  onPointerDown,
  onDoubleClick,
}: {
  onPointerDown: (e: React.PointerEvent<HTMLButtonElement>) => void;
  onDoubleClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className="mem-grip"
      onPointerDown={onPointerDown}
      onDoubleClick={onDoubleClick}
      title={t("memory.detail.grip")}
      aria-label={t("memory.detail.gripLabel")}
    />
  );
}

/** The memory list beside its details: the details open only on a click, at 65% of the width by default, and the divider between them can be dragged; J and K step through the list, Esc closes. */
export function MemorySplit({
  title,
  memories,
  selected,
  onSelect,
  onLink,
  extra,
  search,
  onSearch,
}: {
  title: string;
  memories: Placed[];
  selected: string | null;
  onSelect: (path: string | null) => void;
  onLink: (name: string) => void;
  extra?: (memory: Placed) => React.ReactNode;
  search: string;
  onSearch: (q: string) => void;
}) {
  const split = useRef<HTMLDivElement>(null);
  const { dragging, startDrag, resetWidth, detail } = useDetailWidth(split);
  const { t } = useTranslation();
  const labels = useMemoryLabels();
  const current = memories.find((m) => m.path === selected) ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key === "Escape") onSelect(null);
      const down = e.key === "j" || e.key === "ArrowDown";
      if (down || e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const paths = memories.map((m) => m.path);
        const at = selected ? paths.indexOf(selected) : -1;
        const next = paths[Math.max(0, Math.min(paths.length - 1, at + (down ? 1 : -1)))];
        if (next) onSelect(next);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [memories, selected, onSelect]);

  useEffect(() => {
    if (selected)
      split.current?.querySelector(`[data-path="${CSS.escape(selected)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const groups = new Map<string, Placed[]>();
  for (const memory of memories) {
    const group = groupOf(memory, labels.layer);
    groups.set(group, [...(groups.get(group) ?? []), memory]);
  }
  const types = Object.keys(TYPE_COLOUR);
  return (
    <div
      ref={split}
      className={`mem-split${current ? " open" : ""}${dragging ? " dragging" : ""}`}
      style={{ "--dw": current ? detail : "0px" } as React.CSSProperties}
    >
      <div className="mem-list">
        <div className="sh-tb mem-tb">
          <h1>{title}</h1>
          <span className="meta">{memories.length}</span>
          <div className="mem-chips">
            {types.map((type) => (
              <span
                key={type}
                className="mem-chip"
                title={`${type}: ${memories.filter((m) => m.frontmatter.type === type).length}`}
              >
                <i style={{ background: TYPE_COLOUR[type] }} />
                {type}
                <b>{memories.filter((m) => m.frontmatter.type === type).length}</b>
              </span>
            ))}
          </div>
          <input
            type="search"
            className="sh-search"
            placeholder={t("memory.list.filter")}
            aria-label={t("memory.list.searchLabel")}
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </div>
        {memories.length === 0 && <p className="mem-none">{t("memory.list.none")}</p>}
        {[...groups].map(([group, list]) => (
          <section key={group}>
            <div className="mem-grp">
              {group}
              <small>{list.length}</small>
            </div>
            {list.map((memory) => (
              <Row
                key={memory.path}
                memory={memory}
                selected={memory.path === selected}
                onSelect={() => onSelect(memory.path)}
              />
            ))}
          </section>
        ))}
      </div>
      {current && (
        <>
          <Grip onPointerDown={startDrag} onDoubleClick={resetWidth} />
          <DetailShell onClose={() => onSelect(null)} hint="J / K">
            <MemorySheet memory={current} onLink={onLink} />
            {extra?.(current)}
          </DetailShell>
        </>
      )}
    </div>
  );
}
