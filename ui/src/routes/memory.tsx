import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Fragment, useEffect, useRef, useState } from "react";
import type { MemoryCard, MemoryGraph } from "@/client";
import { browseMemoriesOptions, memoryAnalysisOptions, memoryGraphOptions } from "@/client/@tanstack/react-query.gen";
import { Connections, type Distilled } from "@/components/memory/connections";
import { DrawingSplit } from "@/components/memory/drawing-split";
import { cardLevel, LAYER_ORDER, LEVEL_ORDER, nameOf, useMemoryLabels } from "@/components/memory/memory-parts";
import { LEVEL_COLOUR, MemorySheet, MemorySplit, type Placed } from "@/components/memory/memory-split";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { Skeleton } from "@/components/shell/skeleton";
import { useLanguage, useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { apiBase, authToken } from "@/lib/connection";
import { useStartCuration } from "@/lib/curation";
import { usePersona } from "@/lib/persona";

type MemoryView = "list" | "graph" | "rings" | "analysis";
type MemorySearch = {
  identity?: string;
  level?: string;
  q?: string;
  view?: MemoryView;
  layer?: string;
  dir?: string;
  m?: string;
};
const VIEWS: MemoryView[] = ["list", "graph", "rings", "analysis"];
const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export const Route = createFileRoute("/memory")({
  validateSearch: (search: Record<string, unknown>): MemorySearch => {
    const view =
      search.view === "graph" || search.view === "rings" || search.view === "analysis" ? search.view : undefined;
    const found: MemorySearch = {
      identity: text(search.identity),
      level: text(search.level),
      q: text(search.q),
      view,
      layer: text(search.layer),
      dir: text(search.dir),
      m: text(search.m),
    };
    return Object.fromEntries(Object.entries(found).filter(([, v]) => v !== undefined)) as MemorySearch;
  },
  component: MemoryPage,
});

function MemoryPage() {
  const search = Route.useSearch();
  const { level, q, view, layer, dir, m } = search;
  const navigate = useNavigate({ from: "/memory" });
  const { data, error, isPending } = useQuery(browseMemoriesOptions());
  const { persona } = usePersona();
  const { t } = useTranslation();
  const labels = useMemoryLabels();
  const chosen = data?.find((who) => who.identity === persona) ?? data?.find((who) => who.layers.length > 0);
  const { data: graph } = useQuery({
    ...memoryGraphOptions({ query: { identity: chosen?.identity ?? "" } }),
    enabled: !!chosen && !view,
  });
  usePageHeading(sectionTitle("Memory"), [{ label: t(`memory.views.${view ?? "list"}`) }]);
  const placed: Placed[] = (chosen?.layers ?? [])
    .slice()
    .sort((a, b) => LAYER_ORDER.indexOf(a.layer) - LAYER_ORDER.indexOf(b.layer) || a.dir.localeCompare(b.dir))
    .flatMap((l) => l.memories.map((memory) => ({ ...memory, layer: l.layer, dir: l.dir })));
  const all = placed.map(({ layer: _l, dir: _d, ...memory }) => memory);
  const needle = (q ?? "").toLowerCase();
  const shown = placed.filter(
    (memory) =>
      (!layer || memory.layer === layer) &&
      (!dir || memory.dir === dir) &&
      (!level || cardLevel(memory) === level) &&
      (!needle ||
        [memory.path, memory.body, ...Object.values(memory.frontmatter)].some((value) =>
          String(value).toLowerCase().includes(needle),
        )),
  );
  const go = (next: Partial<MemorySearch>) => navigate({ search: (prev) => ({ ...prev, ...next }) });
  // a drawing selects by node id (a memory's name, a distillate entry, the core); the URL keeps a memory's path, as
  // the list does, and any other node's id
  const drawnMemory = m ? placed.find((x) => x.path === m) : undefined;
  const drawn = drawnMemory ? nameOf(drawnMemory) : (m ?? null);
  const selectDrawn = (id: string | null) => {
    const target = id ? placed.find((x) => nameOf(x) === id) : undefined;
    go({ m: target ? target.path : (id ?? undefined) });
  };
  const openByName = (name: string) => {
    const target = placed.find((x) => nameOf(x) === name);
    go(target ? { m: target.path, q: undefined, level: undefined, layer: undefined, dir: undefined } : { q: name });
  };
  const title = dir ? (dir.split("/").pop() ?? dir) : layer ? labels.layer(layer) : t("memory.page.all");

  if (isPending) return <Skeleton rows={16} />;
  if (error)
    return <p className="font-mono text-destructive">{t("memory.page.loadError", { error: JSON.stringify(error) })}</p>;
  return (
    <>
      <MemoryModuleBar placed={placed} search={search} go={go} />
      {chosen && !view && (
        <MemorySplit
          title={title}
          memories={shown}
          selected={m ?? null}
          onSelect={(path) => go({ m: path ?? undefined })}
          onLink={openByName}
          extra={(memory) => <Connections name={nameOf(memory)} memories={all} graph={graph} onLink={openByName} />}
          search={q ?? ""}
          onSearch={(value) => navigate({ search: (prev) => ({ ...prev, q: value || undefined }), replace: true })}
        />
      )}
      {chosen && view === "analysis" && (
        <div className="rp">
          <AnalysisView identity={chosen.identity} />
        </div>
      )}
      {chosen && view === "graph" && (
        <BrainView identity={chosen.identity} memories={all} selected={drawn} onSelect={selectDrawn} />
      )}
      {chosen && view === "rings" && (
        <RingsView identity={chosen.identity} memories={all} selected={drawn} onSelect={selectDrawn} />
      )}
    </>
  );
}

/* The memory module's bar: the views, the layers (a layer with several folders opens into them) and the levels, each
   with its count; the filters stay in the URL. */
function MemoryModuleBar({
  placed,
  search,
  go,
}: {
  placed: Placed[];
  search: MemorySearch;
  go: (next: Partial<MemorySearch>) => void;
}) {
  const { view, layer, dir, level } = search;
  const { t } = useTranslation();
  const labels = useMemoryLabels();
  const [open, setOpen] = useState<Set<string>>(new Set(layer ? [layer] : []));
  const byLayer = new Map<string, Map<string, number>>();
  for (const memory of placed) {
    const dirs = byLayer.get(memory.layer) ?? new Map<string, number>();
    dirs.set(memory.dir, (dirs.get(memory.dir) ?? 0) + 1);
    byLayer.set(memory.layer, dirs);
  }
  const levels = new Map<string, number>();
  for (const memory of placed) levels.set(cardLevel(memory), (levels.get(cardLevel(memory)) ?? 0) + 1);
  const list = { view: undefined, m: undefined };
  return (
    <ModuleBar>
      <CurationSection />
      <MigrationSection />
      <ModuleBarSection title={t("memory.page.views")}>
        {VIEWS.map((id) => (
          <button
            type="button"
            key={id}
            title={t(`memory.views.${id}Title`)}
            className={`sh-item${(view ?? "list") === id ? " on" : ""}`}
            onClick={() => go({ view: id === "list" ? undefined : id, m: undefined })}
          >
            {t(`memory.views.${id}`)}
          </button>
        ))}
      </ModuleBarSection>
      {!view && (
        <>
          <ModuleBarSection title={t("memory.page.layers")}>
            <button
              type="button"
              className={`sh-item${!layer && !dir ? " on" : ""}`}
              onClick={() => go({ ...list, layer: undefined, dir: undefined })}
            >
              {t("memory.page.allShort")}
              <span className="c">{placed.length}</span>
            </button>
            {LAYER_ORDER.filter((name) => byLayer.has(name)).map((name) => {
              const dirs = byLayer.get(name) ?? new Map<string, number>();
              const many = dirs.size > 1;
              const isOpen = open.has(name);
              const total = [...dirs.values()].reduce((a, n) => a + n, 0);
              return (
                <Fragment key={name}>
                  <button
                    type="button"
                    className={`sh-item${layer === name && !dir ? " on" : ""}`}
                    onClick={() => {
                      if (many)
                        setOpen((set) =>
                          set.has(name) && layer === name && !dir
                            ? new Set([...set].filter((x) => x !== name))
                            : new Set([...set, name]),
                        );
                      go({ ...list, layer: name, dir: undefined });
                    }}
                  >
                    <span className="car">{many ? (isOpen ? "▾" : "▸") : ""}</span>
                    {labels.layer(name)}
                    <span className="c">{total}</span>
                  </button>
                  {many &&
                    isOpen &&
                    [...dirs].map(([d, n]) => (
                      <button
                        type="button"
                        key={d}
                        title={d}
                        className={`sh-item sub${dir === d ? " on" : ""}`}
                        onClick={() => go({ ...list, layer: name, dir: d })}
                      >
                        <span className="path">{d}</span>
                        <span className="c">{n}</span>
                      </button>
                    ))}
                </Fragment>
              );
            })}
          </ModuleBarSection>
          <ModuleBarSection title={t("memory.page.trust")}>
            {LEVEL_ORDER.filter((name) => levels.has(name)).map((name) => (
              <button
                type="button"
                key={name}
                title={labels.level(name)}
                className={`sh-item${level === name ? " on" : ""}`}
                onClick={() => go({ ...list, level: level === name ? undefined : name })}
              >
                <i className="dot" style={{ background: LEVEL_COLOUR[name] }} />
                {name}
                <span className="c">{levels.get(name)}</span>
              </button>
            ))}
          </ModuleBarSection>
        </>
      )}
    </ModuleBar>
  );
}

type BrainReady = {
  types: Record<string, { label: string; color: string }>;
  counts: Record<string, number>;
  distilled?: Distilled;
};
const DISTILLED = "d:";

const toggled = (set: Set<string>, key: string) => {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
};

/* The Emlékagy as the memory page's drawing: the frame draws only the brain (embed); the toolbar, the module bar's
   type filters and the details pane are this page's, and the two talk through messages. */
function BrainView({
  identity,
  memories,
  selected,
  onSelect,
}: {
  identity: string;
  memories: MemoryCard[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { frame, html, failed, post } = useEmbedded("brain", identity);
  const { t } = useTranslation();
  const { data: graph } = useQuery(memoryGraphOptions({ query: { identity } }));
  const [ready, setReady] = useState<BrainReady | null>(null);
  const pick = useRef(onSelect);
  pick.current = onSelect;
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [spin, setSpin] = useState(true);
  useEffect(() => {
    const listen = (ev: MessageEvent) => {
      if (ev.source !== frame.current?.contentWindow || !ev.data?.whaat) return;
      if (ev.data.whaat === "ready") setReady(ev.data as BrainReady);
      if (ev.data.whaat === "select") pick.current(ev.data.id ?? null);
    };
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [frame]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: post reads the frame ref, which never changes
  useEffect(() => {
    if (ready) post({ whaat: "filter", hiddenTypes: [...hidden], query });
  }, [ready, hidden, query]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: post reads the frame ref, which never changes
  useEffect(() => {
    if (ready) post({ whaat: "select", id: selected });
  }, [ready, selected]);
  const choose = onSelect;
  const types = ready ? Object.entries(ready.types).filter(([key]) => ready.counts[key]) : [];
  const live = types.filter(([key]) => !key.startsWith(DISTILLED));
  const layer = types.filter(([key]) => key.startsWith(DISTILLED));
  const layerShown = layer.some(([key]) => !hidden.has(key));
  const count = (list: typeof types) => list.reduce((sum, [key]) => sum + (ready?.counts[key] ?? 0), 0);
  const item = ([key, type]: (typeof types)[number]) => (
    <button
      type="button"
      key={key}
      className={`sh-item${hidden.has(key) ? " off" : ""}`}
      onClick={() => setHidden((set) => toggled(set, key))}
    >
      <i className="dot" style={{ background: type.color }} />
      {type.label.replace(t("memory.page.distillatePrefix"), "")}
      <span className="c">{ready?.counts[key]}</span>
    </button>
  );
  if (failed) return <p className="font-mono text-destructive">{t("memory.page.brainError", { error: failed })}</p>;
  if (!html) return <p className="font-mono text-muted-foreground">{t("memory.page.loadingBrain")}</p>;
  return (
    <>
      {ready && (
        <ModuleBar>
          <ModuleBarSection title={t("memory.page.types")}>{live.map(item)}</ModuleBarSection>
          {layer.length > 0 && (
            <ModuleBarSection title={t("memory.page.distillate")}>
              <button
                type="button"
                className={`sh-item${layerShown ? "" : " off"}`}
                title={t("memory.page.distillateTitle")}
                onClick={() =>
                  setHidden((set) => {
                    const next = new Set(set);
                    for (const [key] of layer) {
                      if (layerShown) next.add(key);
                      else next.delete(key);
                    }
                    return next;
                  })
                }
              >
                <i className="dot" style={{ background: "var(--yellow)" }} />
                {t("memory.page.allShort")}
                <span className="c">{count(layer)}</span>
              </button>
              {layerShown && layer.map(item)}
            </ModuleBarSection>
          )}
        </ModuleBar>
      )}
      <DrawingSplit
        onClose={() => choose(null)}
        toolbar={
          <div className="sh-tb">
            <h1>{t("memory.page.brain")}</h1>
            <span className="meta">
              {t("memory.page.brainMeta", { memories: memories.length, edges: graph?.edges.length ?? "…" })}
            </span>
            <input
              type="search"
              className="sh-search"
              placeholder={t("memory.page.brainSearch")}
              aria-label={t("memory.page.brainSearchLabel")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button
              type="button"
              className={`dv-btn${spin ? " on" : ""}`}
              onClick={() => {
                setSpin(!spin);
                post({ whaat: "spin", on: !spin });
              }}
            >
              {t("memory.page.spin")}
            </button>
          </div>
        }
        frame={<iframe ref={frame} className="dv-frame" title={t("memory.page.brainFrame")} srcDoc={html} />}
        detail={
          selected ? (
            <DrawingDetail
              selected={selected}
              memories={memories}
              distilled={ready?.distilled ?? null}
              graph={graph ?? null}
              links
              onLink={choose}
            />
          ) : null
        }
      />
    </>
  );
}

/* The details of a point of a drawing: a memory's sheet as on the list, the core's files, or a distillate entry. */
function DrawingDetail({
  selected,
  memories,
  distilled = null,
  graph = null,
  links = false,
  onLink,
}: {
  selected: string;
  memories: MemoryCard[];
  distilled?: BrainReady["distilled"];
  graph?: MemoryGraph | null;
  links?: boolean;
  onLink: (name: string) => void;
}) {
  const { t } = useTranslation();
  const node = distilled?.nodes[selected];
  if (node) {
    const live = node.linked
      ? memories.find((m) => nameOf(m) === node.mem || m.path.endsWith(`/${node.mem}.md`))
      : null;
    return (
      <div className="mem-sheet sh-paper">
        <span className="mem-type" style={{ background: "var(--yellow)", color: "var(--ink)" }}>
          {t("memory.page.distillateKind")}
        </span>
        <h2>{node.label}</h2>
        <div className="mem-path">
          {node.date} · {distilled?.lobes[node.lobe] ?? ""}
        </div>
        <p className="narrative">{node.detail}</p>
        {node.mem && (
          <p className="muted">
            {t("memory.page.liveMemory")}{" "}
            {live ? (
              <button type="button" className="mlink" onClick={() => onLink(nameOf(live))}>
                {nameOf(live)}
              </button>
            ) : (
              <>
                <b>{node.mem}</b> {t("memory.page.notInMemory")}
              </>
            )}
          </p>
        )}
      </div>
    );
  }
  if (selected === "__core__") {
    const core = memories.filter((m) => m.path.startsWith("personal/core/"));
    return (
      <div className="mem-sheet sh-paper">
        <span className="mem-type" style={{ background: "var(--yellow)", color: "var(--ink)" }}>
          {t("memory.page.coreKind")}
        </span>
        <h2>{t("memory.page.core")}</h2>
        <div className="mem-path">{t("memory.page.coreNote")}</div>
        <ul className="core-list">
          {core.map((m) => (
            <li key={m.path}>
              <button type="button" className="mlink" onClick={() => onLink(nameOf(m))}>
                {nameOf(m)}
              </button>{" "}
              {m.frontmatter.description}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const memory = memories.find((m) => nameOf(m) === selected);
  return (
    <>
      {memory ? (
        <MemorySheet memory={memory} onLink={onLink} />
      ) : (
        <p className="muted">
          <b>{selected}</b>: {t("memory.page.ghost")}
        </p>
      )}
      {links && <Connections name={selected} memories={memories} graph={graph} distilled={distilled} onLink={onLink} />}
    </>
  );
}

/* A drawing fetched in the chosen language (the server draws its words), again when the language changes. */
function useEmbedded(kind: "brain" | "rings", identity: string) {
  const { language } = useLanguage();
  const frame = useRef<HTMLIFrameElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setHtml(null);
    const query = new URLSearchParams({ identity, embed: "true", lang: language });
    fetch(`${apiBase()}/api/v1/memory/${kind}?${query}`, {
      headers: { Authorization: `Bearer ${authToken()}` },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
        return response.text();
      })
      .then((text) => alive && setHtml(text))
      .catch((error: Error) => alive && setFailed(error.message));
    return () => {
      alive = false;
    };
  }, [kind, identity, language]);
  const post = (message: Record<string, unknown>) => frame.current?.contentWindow?.postMessage(message, "*");
  return { frame, html, failed, post };
}

type RingsReady = {
  levels: Record<string, string>;
  levelLabels?: Record<string, string>;
  levelCounts: Record<string, number>;
  when: Record<string, number>;
};

/* The Memória-gyűrűk as the memory page's drawing: the frame draws only the rings (embed); the level and "when"
   filters sit in the module bar, the toolbar and the details pane are this page's. */
function RingsView({
  identity,
  memories,
  selected,
  onSelect,
}: {
  identity: string;
  memories: MemoryCard[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { data: graph } = useQuery(memoryGraphOptions({ query: { identity } }));
  const { frame, html, failed, post } = useEmbedded("rings", identity);
  const { t } = useTranslation();
  const [ready, setReady] = useState<RingsReady | null>(null);
  const pick = useRef(onSelect);
  pick.current = onSelect;
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [when, setWhen] = useState<string | null>(null);
  useEffect(() => {
    const listen = (ev: MessageEvent) => {
      if (ev.source !== frame.current?.contentWindow || !ev.data?.whaat) return;
      if (ev.data.whaat === "ready") setReady(ev.data as RingsReady);
      if (ev.data.whaat === "select") pick.current(ev.data.id ?? null);
    };
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [frame]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: post reads the frame ref, which never changes
  useEffect(() => {
    if (ready) post({ whaat: "filter", hiddenLevels: [...hidden], when });
  }, [ready, hidden, when]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: post reads the frame ref, which never changes
  useEffect(() => {
    if (ready) post({ whaat: "select", id: selected });
  }, [ready, selected]);
  const choose = onSelect;
  if (failed) return <p className="font-mono text-destructive">{t("memory.page.ringsError", { error: failed })}</p>;
  if (!html) return <p className="font-mono text-muted-foreground">{t("memory.page.loadingRings")}</p>;
  const total = ready ? Object.values(ready.levelCounts).reduce((a, n) => a + n, 0) : 0;
  return (
    <>
      {ready && (
        <ModuleBar>
          <ModuleBarSection title={t("memory.page.level")}>
            {Object.entries(ready.levels).map(([level, color]) => (
              <button
                type="button"
                key={level}
                className={`sh-item${hidden.has(level) ? " off" : ""}`}
                onClick={() => setHidden((set) => toggled(set, level))}
              >
                <i className="dot" style={{ background: color }} />
                {ready.levelLabels?.[level] ?? level}
                <span className="c">{ready.levelCounts[level] ?? 0}</span>
              </button>
            ))}
          </ModuleBarSection>
          <ModuleBarSection title={t("memory.page.when")}>
            {Object.entries(ready.when)
              .sort((a, b) => b[1] - a[1])
              .map(([w, n]) => (
                <button
                  type="button"
                  key={w}
                  className={`sh-item${when === w ? " on" : ""}`}
                  onClick={() => setWhen(when === w ? null : w)}
                >
                  {w}
                  <span className="c">{n}</span>
                </button>
              ))}
          </ModuleBarSection>
        </ModuleBar>
      )}
      <DrawingSplit
        onClose={() => choose(null)}
        toolbar={
          <div className="sh-tb">
            <h1>{t("memory.page.rings")}</h1>
            <span className="meta">
              {t("memory.page.ringsMeta", { count: total })}
              {when ? t("memory.page.ringsWhen", { when }) : ""}
            </span>
            <span className="grow" />
            <button type="button" className="dv-btn" onClick={() => post({ whaat: "open", all: true })}>
              {t("memory.page.openAll")}
            </button>
            <button
              type="button"
              className="dv-btn"
              onClick={() => {
                setWhen(null);
                post({ whaat: "open", all: false });
              }}
            >
              {t("memory.page.closeAll")}
            </button>
          </div>
        }
        frame={<iframe ref={frame} className="dv-frame" title={t("memory.page.ringsFrame")} srcDoc={html} />}
        detail={
          selected ? (
            <DrawingDetail selected={selected} memories={memories} graph={graph ?? null} links onLink={choose} />
          ) : null
        }
      />
    </>
  );
}

/* The distillate's verdicts and its wording are data: matched as they were written, in Hungarian. */
const VERDICT_COLOUR: Record<string, [string, string]> = {
  MARAD: ["var(--red)", "#fff8e8"],
  ELTŰNT: ["var(--teal)", "#fff8e8"], // i18n-content
  "ELTŰNT?": ["#5d9d8b", "#fff8e8"], // i18n-content
  ALAKOT: ["var(--orange)", "var(--ink)"],
  EGYSZERI: ["#8a7f6c", "#fff8e8"],
  ÚJ: ["var(--blue)", "#fff8e8"], // i18n-content
};
const WARN_VIEW = /élő memória/; // i18n-content

/* The distillate's analysis, as the Emlékgráf showed it under its graph: the arc, the heatmap, the ladder and the
   changed views, the hub sessions and my reading, one page drawn from the server's data. */
function AnalysisView({ identity }: { identity: string }) {
  const { data, error, isPending } = useQuery(memoryAnalysisOptions({ query: { identity } }));
  const { t } = useTranslation();
  if (isPending) return <p className="font-mono text-muted-foreground">{t("analysis.loading")}</p>;
  if (error || !data) {
    const detail = (error as { detail?: unknown } | null)?.detail;
    const none = typeof detail === "string" && detail.endsWith("keeps no distillate");
    return (
      <p className={none ? "muted" : "font-mono text-destructive"}>
        {none ? t("analysis.noDistillate") : t("analysis.loadError", { error: JSON.stringify(error) })}
      </p>
    );
  }
  const to = data.last.slice(5);
  return (
    <div className="an">
      <div className="an-kicker">{t("analysis.kicker", { first: data.first, last: to })}</div>

      <h2 id="iv">{t("analysis.arc")}</h2>
      <p className="an-sub">{t("analysis.arcSub")}</p>
      <div className="an-phases">
        {data.phases.map((phase) => (
          <div className="an-phase sh-paper" key={phase.span}>
            <div className="span">{phase.span}</div>
            <h4>{phase.title}</h4>
            <span className="who me">{t("analysis.me")}</span>
            <p>{phase.me}</p>
            <span className="who user">{t("analysis.user")}</span>
            <p>{phase.user}</p>
          </div>
        ))}
      </div>

      <h2 id="heat">{t("analysis.heat")}</h2>
      <p className="an-sub">{t("analysis.heatSub")}</p>
      <div className="an-heat sh-paper">
        <div
          className="hgrid"
          style={{
            gridTemplateColumns: `minmax(220px,260px) repeat(${data.batches.length},34px) 150px minmax(240px,1fr)`,
          }}
        >
          <div className="hl">{t("analysis.failureMode")}</div>
          {data.batches.map((batch, i) => (
            <div className="hh" key={batch}>
              {i + 1} · {batch}
            </div>
          ))}
          <div className="hl">{t("analysis.verdict")}</div>
          <div className="hl">{t("analysis.note")}</div>
          {data.heat.map((row) => {
            const [bg, fg] = VERDICT_COLOUR[row.verdict.split(" ")[0] ?? ""] ?? ["#8a7f6c", "#fff8e8"];
            return (
              <Fragment key={row.id}>
                <div className="rl">{row.label}</div>
                {data.batches.map((batch, i) => {
                  const kind = row.ep.includes(i + 1) ? "ep" : row.mention.includes(i + 1) ? "mn" : "";
                  const what = kind === "ep" ? t("analysis.namedCase") : kind === "mn" ? t("analysis.mentioned") : "";
                  return <div className={`cell ${kind}`} key={batch} title={`${batch}${what}`} />;
                })}
                <div className="verdict" style={{ background: bg, color: fg }}>
                  {row.verdict}
                </div>
                <div className="note">{row.note}</div>
              </Fragment>
            );
          })}
        </div>
      </div>

      <h2 id="user">{t("analysis.yourArc")}</h2>
      <p className="an-sub">{t("analysis.yourArcSub")}</p>
      <div className="an-two">
        <div className="an-box sh-paper">
          <h3>{t("analysis.ladder")}</h3>
          <div className="steps">
            {data.ladder.map((step) => (
              <div className="step" key={`${step.date}${step.text}`}>
                <b>{step.date}</b>
                <span>{step.text}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="an-box sh-paper">
          <h3>{t("analysis.changed")}</h3>
          {data.changed.map((view) => (
            <div className={`crow${WARN_VIEW.test(view.new) ? " warn" : ""}`} key={`${view.date}${view.old}`}>
              <span className="d">{view.date}</span>
              <span className="o">{view.old}</span>
              <span className="ar">→</span>
              <span className="n">{view.new}</span>
            </div>
          ))}
        </div>
      </div>

      <h2 id="hubs">{t("analysis.hubs")}</h2>
      <p className="an-sub">{t("analysis.hubsSub", { to })}</p>
      <div className="an-hubs">
        {data.hubs.map((hub) => (
          <div className="hub" key={hub.id}>
            <span className="c">{hub.n}</span>
            <code>{hub.id}</code> <span className="date">{hub.date}</span>
            <p>{hub.text}</p>
          </div>
        ))}
      </div>

      {data.reading && (
        <>
          <h2 id="nezet">{data.reading.title}</h2>
          <div className="an-view sh-paper">
            {data.reading.paragraphs.map((paragraph) => (
              <p key={paragraph.lead}>
                <strong>{paragraph.lead}</strong> {paragraph.text}
              </p>
            ))}
            <div className="caveat">
              <ul>
                {data.reading.caveats.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </div>
          </div>
        </>
      )}
      <footer className="an-foot">{t("analysis.footer", { to })}</footer>
    </div>
  );
}

function CurationSection() {
  const { t } = useTranslation();
  const curation = useStartCuration();
  return (
    <ModuleBarSection title={t("curation.section")}>
      <button
        type="button"
        className="sh-item"
        title={t("curation.startTitle")}
        disabled={!curation.can || curation.pending}
        onClick={curation.start}
      >
        {curation.pending ? t("curation.starting") : t("curation.start")}
      </button>
      {curation.error && <p className="sh-note">{t("curation.startFailed", { error: curation.error })}</p>}
    </ModuleBarSection>
  );
}

/* Bringing existing memory into the persona: next to
   curation, where memory work starts; the page itself is the persona's own (Settings › Identities). */
function MigrationSection() {
  const { t } = useTranslation();
  const { persona } = usePersona();
  if (!persona) return null;
  return (
    <ModuleBarSection title={t("migrate.section")}>
      <Link to="/settings/identities/$identity/migrate" params={{ identity: persona }} className="sh-item">
        ↧ {t("migrate.title")}
      </Link>
    </ModuleBarSection>
  );
}
