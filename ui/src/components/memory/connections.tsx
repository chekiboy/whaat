import type { MemoryCard, MemoryGraph } from "@/client";
import { nameOf } from "@/components/memory/memory-parts";
import { useTranslation } from "@/i18n";

export type DistilledNode = {
  label: string;
  type: string;
  detail: string;
  date: string;
  mem: string;
  linked: boolean;
  lobe: string;
};
export type Distilled = { lobes: Record<string, string>; nodes: Record<string, DistilledNode> } | null;

/** How a memory is tied to the others, by direction: the links it writes and the ones written to it, what it
    supersedes and what superseded it, and the distillate's entries that name it (only where the brain sends them). */
export function Connections({
  name,
  memories,
  graph,
  distilled = null,
  onLink,
}: {
  name: string;
  memories: MemoryCard[];
  graph: MemoryGraph | null | undefined;
  distilled?: Distilled;
  onLink: (id: string) => void;
}) {
  const { t } = useTranslation();
  if (!graph) return <p className="muted dv-links">{t("memory.links.loading")}</p>;
  const ghost = new Set(graph.nodes.filter((n) => n.ghost).map((n) => n.id));
  const edges = (kind: string, from: "source" | "target") =>
    graph.edges
      .filter((e) => e.kind === kind && e[from] === name)
      .map((e) => (from === "source" ? e.target : e.source));
  const groups = [
    { arrow: "→", label: t("memory.links.linksTo"), ids: edges("link", "source") },
    { arrow: "←", label: t("memory.links.linkedFrom"), ids: edges("link", "target") },
    { arrow: "→", label: t("memory.links.supersedes"), ids: edges("supersedes", "source") },
    { arrow: "←", label: t("memory.links.supersededBy"), ids: edges("supersedes", "target") },
    {
      arrow: "←",
      label: t("memory.links.distillate"),
      ids: Object.entries(distilled?.nodes ?? {})
        .filter(([, node]) => node.linked && node.mem === name)
        .map(([id]) => id),
    },
  ]
    .map((group) => ({ ...group, ids: [...new Set(group.ids)] }))
    .filter((group) => group.ids.length > 0);
  const titleOf = (id: string) =>
    distilled?.nodes[id]?.label ?? memories.find((m) => nameOf(m) === id)?.frontmatter.description ?? id;
  return (
    <section className="dv-links">
      <h3>
        {t("memory.links.title")} <b className="cnt">{groups.reduce((n, g) => n + g.ids.length, 0)}</b>
      </h3>
      {groups.length === 0 && <p className="muted">{t("memory.links.none")}</p>}
      {groups.map((group) => (
        <div className="dv-lgroup" key={group.label}>
          <div className="dv-lhead">
            <span className="arr">{group.arrow}</span> {group.label} <b className="cnt">{group.ids.length}</b>
          </div>
          {group.ids.map((id) => (
            <button
              type="button"
              key={id}
              className={`dv-lrow${ghost.has(id) ? " ghost" : ""}`}
              title={ghost.has(id) ? t("memory.links.ghost", { id }) : titleOf(id)}
              onClick={() => onLink(id)}
            >
              <span className="arr">{group.arrow}</span>
              <span className="n">{id}</span>
              <span className="d">{ghost.has(id) ? t("memory.links.ghostShort") : titleOf(id)}</span>
            </button>
          ))}
        </div>
      ))}
    </section>
  );
}
