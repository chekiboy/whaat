import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import type { MigratedGroup, MigrationGroup, MigrationPlanView, MigrationSent } from "@/client";
import {
  listTerminalsOptions,
  migrationPlanDecideMutation,
  migrationPlanGetOptions,
  migrationPlanListOptions,
  migrationStartMutation,
} from "@/client/@tanstack/react-query.gen";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { ProjectPicker } from "@/components/terminal/project-picker";
import { useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { usePersona } from "@/lib/persona";
import { usePreferences } from "@/lib/preferences";
import "@/styles/migrate.css";
import "@/styles/overview.css";

type Search = { plan?: string };

export const Route = createFileRoute("/settings_/identities/$identity/migrate")({
  validateSearch: (search: Record<string, unknown>): Search =>
    typeof search.plan === "string" && search.plan ? { plan: search.plan } : {},
  component: Migrate,
});

const LAYERS = ["core", "personal", "global", "project", "repo"] as const;
type Layer = (typeof LAYERS)[number];

/** The layer a path below the memory root sits in, as the server's layer_of has it. */
function layerOf(path: string): Layer {
  const parts = path.split("/").slice(0, -1);
  if (parts[0] === "personal") return parts[1] === "core" ? "core" : "personal";
  return parts.length === 0 ? "global" : parts.length === 1 ? "project" : "repo";
}

function targetLayer(target: string): Layer {
  return target === "." ? "global" : target === "personal" ? "personal" : layerOf(`${target}/x.md`);
}

const sourceNumber = (group: MigrationGroup) => group.id.split(":")[0] ?? "";

/** A path as the user writes it: the home folder as ~. */
const short = (path: string) => path.replace(/^\/(Users|home)\/[^/]+/, "~");

/** How often the page asks for the identity's plans, so the one the migration session saves shows up by itself. */
const PLAN_POLL_MS = 3000;
/** The label whaat gives the migration's terminal session; a question it asks takes the user there. */
const MIGRATE_LABEL = "memory-migrate";

/* The identity's page for bringing existing memory in: who the memory goes to is the subject of the page, the
   user picks the groups and a loose folder's layer here, and Send types the import into the migration session. */
function Migrate() {
  const { identity } = Route.useParams();
  const { plan: planId } = Route.useSearch();
  const { t } = useTranslation();
  usePageHeading(sectionTitle("Settings"), [
    { label: t("settings.title") },
    { label: identity },
    { label: t("migrate.title") },
  ]);
  const { persona } = usePersona();
  const navigate = useNavigate();
  const plans =
    useQuery({ ...migrationPlanListOptions({ query: { identity } }), refetchInterval: PLAN_POLL_MS }).data ?? [];
  const latest = [...plans].sort((a, b) => b.id.localeCompare(a.id))[0];
  const asking = useQuery({
    ...listTerminalsOptions({ query: { persona: identity } }),
    refetchInterval: PLAN_POLL_MS,
  }).data?.sessions.find((s) => s.label === MIGRATE_LABEL && s.asking && !s.gone);
  useEffect(() => {
    if (asking) navigate({ to: "/terminal", search: { s: asking.name } });
  }, [asking, navigate]);
  useEffect(() => {
    if (!planId && latest) {
      navigate({
        to: "/settings/identities/$identity/migrate",
        params: { identity },
        search: { plan: latest.id },
        replace: true,
      });
    }
  }, [planId, latest, identity, navigate]);
  return (
    <div className="sh-view mg">
      <ModuleBar>
        <ModuleBarSection title={t("settings.title")}>
          <Link to="/settings" className="sh-item">
            {t("settings.identities")}
          </Link>
        </ModuleBarSection>
        <ModuleBarSection title={identity}>
          <Link
            to="/settings/identities/$identity/migrate"
            params={{ identity }}
            className={`sh-item${planId ? "" : " on"}`}
          >
            {t("migrate.title")}
          </Link>
          {plans.map((plan) => (
            <Link
              key={plan.id}
              to="/settings/identities/$identity/migrate"
              params={{ identity }}
              search={{ plan: plan.id }}
              className={`sh-item sub${plan.id === planId ? " on" : ""}`}
            >
              {plan.created_at}
              {(plan.imported_at || plan.groups !== null) && (
                <span className="c">{plan.imported_at ? "✓" : plan.groups}</span>
              )}
            </Link>
          ))}
        </ModuleBarSection>
      </ModuleBar>
      {planId ? (
        <PlanPage identity={identity} planId={planId} persona={persona} />
      ) : (
        <NoPlan identity={identity} persona={persona} />
      )}
    </div>
  );
}

function Profile({ identity, view, persona }: { identity: string; view?: MigrationPlanView; persona: string | null }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="mg-prof">
        <span className="sh-av mg-big">{identity[0]?.toUpperCase()}</span>
        <div>
          <div className="mg-kicker">{t("migrate.kicker")}</div>
          <div className="mg-name">{identity}</div>
          {view && (
            <div className="mg-meta">
              {t("migrate.meta", { folder: short(view.folder), instance: view.instance, name: identity })}
            </div>
          )}
        </div>
        <div className="mg-stamp">{t("migrate.stamp", { name: identity })}</div>
      </div>
      {persona && persona !== identity && (
        <div className="mg-warn">{t("migrate.mismatch", { persona, name: identity })}</div>
      )}
    </>
  );
}

function NoPlan({ identity, persona }: { identity: string; persona: string | null }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const start = useMutation({
    ...migrationStartMutation(),
    onSuccess: (session) => navigate({ to: "/terminal", search: { s: session.name } }),
  });
  const [picking, setPicking] = useState(false);
  const config = usePreferences().preferences?.identity?.agents?.[identity];
  const detail = (start.error as { detail?: unknown } | null)?.detail;
  if (picking) {
    return (
      <>
        <Profile identity={identity} persona={persona} />
        <p className="mg-pick">{t("migrate.pickFolder")}</p>
        <div className="mg-picker">
          <ProjectPicker
            key={config ?? ""}
            command="claude /whaat:memory-migrate"
            start={config || undefined}
            starting={start.isPending}
            onStart={(cwd) => start.mutate({ body: { identity, cwd } })}
            onCancel={() => setPicking(false)}
          />
        </div>
        {start.isError && (
          <p className="mg-warn">
            {t("migrate.failed", { detail: typeof detail === "string" ? detail : String(start.error) })}
          </p>
        )}
      </>
    );
  }
  return (
    <>
      <Profile identity={identity} persona={persona} />
      <div className="mg-empty">
        <h2>{t("migrate.noPlan")}</h2>
        <p>{t("migrate.noPlanNote")}</p>
        <button type="button" className="mg-go" disabled={start.isPending} onClick={() => setPicking(true)}>
          <span className="sh-av">{identity[0]?.toUpperCase()}</span>
          {t("migrate.start")}
        </button>
        {start.isError && (
          <p className="mg-warn">
            {t("migrate.failed", { detail: typeof detail === "string" ? detail : String(start.error) })}
          </p>
        )}
      </div>
    </>
  );
}

function kindOf(group: MigrationGroup): "store" | "personal" | "auto" | "subagent" | "loose" {
  if (group.kind !== "loose") return group.kind;
  if (group.source.includes("/agent-memory/")) return "subagent";
  return group.source.includes("/.claude/projects/") ? "auto" : "loose";
}

function PlanPage({ identity, planId, persona }: { identity: string; planId: string; persona: string | null }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [sent, setSent] = useState<MigrationSent | null>(null);
  const query = useQuery({
    ...migrationPlanGetOptions({ path: { plan_id: planId }, query: { identity } }),
    refetchInterval: (q) => ((q.state.data?.plan.sent_at || sent) && !q.state.data?.plan.imported_at ? 3000 : false),
  });
  const view = query.data;
  const groups = asImported(view?.listing.groups ?? [], view?.plan.result?.groups);
  const plan = view?.plan;
  const done = Boolean(plan?.imported_at);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Set<string> | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!plan || chosen) return;
    const loose: Record<string, string> = {};
    plan.sources.forEach((source, index) => {
      if (source.kind === "loose" && source.target) loose[String(index + 1)] = source.target;
    });
    setTargets(loose);
    setChosen(new Set(plan.groups ?? groups.map((group) => group.id)));
  }, [plan, groups, chosen]);
  const decide = useMutation({
    ...migrationPlanDecideMutation(),
    onSuccess: (result) => {
      setSent(result);
      if (result.typed && result.session) navigate({ to: "/terminal", search: { s: result.session } });
    },
  });
  // a loose folder's group is named by its source and the layer the user gives it here
  const idOf = (group: MigrationGroup) =>
    group.kind === "loose" ? `${sourceNumber(group)}:${targets[sourceNumber(group)] ?? group.target}` : group.id;
  const isOn = (group: MigrationGroup) => chosen?.has(group.id) ?? false;
  const toggle = (group: MigrationGroup) =>
    setChosen((current) => {
      const next = new Set(current);
      next.has(group.id) ? next.delete(group.id) : next.add(group.id);
      return next;
    });
  const picked = groups.filter(isOn);
  const totals = useMemo(() => {
    const by = Object.fromEntries(LAYERS.map((layer) => [layer, 0])) as Record<Layer, number>;
    let files = 0;
    let conflicts = 0;
    for (const group of picked) {
      conflicts += group.conflicts.length;
      for (const file of group.new) {
        files += 1;
        by[layerOf(file)] += 1;
      }
    }
    return { by, files, conflicts };
  }, [picked]);
  const shown = groups.find((group) => group.id === selected) ?? groups[0];
  const sources = [...new Set(groups.map(sourceNumber))];
  const send = () =>
    decide.mutate({
      path: { plan_id: planId },
      body: { identity, targets, groups: picked.map(idOf) },
    });
  const sendError = (decide.error as { detail?: unknown } | null)?.detail;
  return (
    <>
      <Profile identity={identity} view={view} persona={persona} />
      {view && (
        <div className="mg-layers">
          {LAYERS.map((layer) => (
            <div className="mg-lc" key={layer}>
              <div className="k">{t(`migrate.layers.${layer}`)}</div>
              <div className="v">
                {view.layers_now[layer] ?? 0}
                {!done && totals.by[layer] > 0 && <em>+{totals.by[layer]}</em>}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="mg-steps">
        <div className="mg-stp">
          1 · {t("migrate.steps.sources")} {sources.length}
        </div>
        <div className={`mg-stp${done || sent ? "" : " on"}`}>
          2 · {t("migrate.steps.groups")} {picked.length}/{groups.length}
        </div>
        <div className={`mg-stp${done || sent ? " on" : ""}`}>3 · {t("migrate.steps.send")}</div>
        <div className="grow" />
        {!done && (
          <>
            <button type="button" className="mg-ghost" onClick={() => setChosen(new Set(groups.map((g) => g.id)))}>
              {t("migrate.all")}
            </button>
            <button type="button" className="mg-ghost" onClick={() => setChosen(new Set())}>
              {t("migrate.none")}
            </button>
          </>
        )}
      </div>
      <div className="mg-split">
        <div className="mg-list">
          <div className="mg-row hdr">
            <span />
            <span>{t("migrate.head.layer")}</span>
            <span>{t("migrate.head.target")}</span>
            <span className="num">{t("migrate.head.new")}</span>
            <span className="num">{t("migrate.head.same")}</span>
            <span className="num">{t("migrate.head.conflict")}</span>
            <span>{t("migrate.head.index")}</span>
          </div>
          {sources.map((number) => {
            const own = groups.filter((group) => sourceNumber(group) === number);
            const first = own[0];
            if (!first) return null;
            const path = plan?.sources[Number(number) - 1]?.path ?? first.source;
            return (
              <div key={number}>
                <div className="mg-srch" title={short(path)}>
                  {t(`migrate.kinds.${kindOf(first)}`)}
                  <span>{short(path)}</span>
                </div>
                {own.map((group) => (
                  <GroupRow
                    key={group.id}
                    group={group}
                    on={isOn(group)}
                    selected={group.id === shown?.id}
                    done={done}
                    target={group.kind === "loose" ? (targets[number] ?? group.target) : group.target}
                    onTarget={(value) => setTargets((current) => ({ ...current, [number]: value }))}
                    onToggle={() => toggle(group)}
                    onSelect={() => setSelected(group.id)}
                  />
                ))}
              </div>
            );
          })}
        </div>
        <div className="mg-detail">{shown && <GroupDetail group={shown} folder={view?.folder ?? ""} />}</div>
      </div>
      <div className="mg-action">
        {done && plan?.result ? (
          <span className="mg-sum">
            {t("migrate.imported", { at: plan.imported_at })} ·{" "}
            {t("migrate.copied", { n: plan.result.groups.reduce((sum, group) => sum + group.copied.length, 0) })}
          </span>
        ) : (
          <>
            <button
              type="button"
              className="mg-go"
              disabled={!picked.length || decide.isPending || !view}
              onClick={send}
            >
              <span className="sh-av">{identity[0]?.toUpperCase()}</span>
              {t("migrate.send", { groups: picked.length, files: totals.files, name: identity })}
            </button>
            <span className="mg-sum">{t("migrate.sendNote", { n: totals.conflicts })}</span>
          </>
        )}
        {sent && !done && (
          <div className="mg-cmd">
            {sent.typed ? (
              t("migrate.sent", { session: sent.session ?? "" })
            ) : (
              <>
                {t("migrate.notSent", { detail: sent.detail ?? "", name: identity })}
                <code>{sent.command}</code>
              </>
            )}
          </div>
        )}
        {decide.isError && (
          <div className="mg-cmd">
            {t("migrate.failed", { detail: typeof sendError === "string" ? sendError : String(decide.error) })}
          </div>
        )}
      </div>
    </>
  );
}

function GroupRow(props: {
  group: MigrationGroup;
  on: boolean;
  selected: boolean;
  done: boolean;
  target: string;
  onTarget: (value: string) => void;
  onToggle: () => void;
  onSelect: () => void;
}) {
  const { group, on, selected, done, target } = props;
  const { t } = useTranslation();
  const inPlace = group.new.length === 0 && group.conflicts.length === 0 && group.same.length > 0;
  const locked = done || inPlace;
  const ticked = on || inPlace;
  const layer = targetLayer(target);
  const flags = [
    group.unindexed.length && t("migrate.flags.history", { n: group.unindexed.length }),
    group.rewritten.length && t("migrate.flags.rewritten", { n: group.rewritten.length }),
    group.dropped.length && t("migrate.flags.dropped", { n: group.dropped.length }),
    group.converted.length && t("migrate.flags.converted", { n: group.converted.length }),
    group.edited?.length && t("migrate.flags.edited", { n: group.edited.length }),
  ].filter(Boolean);
  return (
    // biome-ignore lint/a11y/useSemanticElements: a dense list row that holds its own checkbox and input
    <div
      className={`mg-row${ticked ? "" : " off"}${selected ? " sel" : ""}`}
      role="button"
      tabIndex={0}
      onClick={props.onSelect}
      onKeyDown={(event) => event.key === "Enter" && props.onSelect()}
    >
      <button
        type="button"
        className={`mg-box${ticked ? " on" : ""}${locked ? " done" : ""}`}
        disabled={locked}
        aria-pressed={ticked}
        title={inPlace ? t("migrate.inPlace") : done ? t("migrate.importedHere") : undefined}
        onClick={(event) => {
          event.stopPropagation();
          props.onToggle();
        }}
      >
        {ticked ? "✓" : ""}
      </button>
      <span className={`mg-lay ${layer}`}>{t(`migrate.layers.${layer}`)}</span>
      {group.kind === "loose" && !done ? (
        <input
          className="dir"
          value={target}
          title={t("migrate.targetHint")}
          spellCheck={false}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => props.onTarget(event.target.value.trim())}
        />
      ) : (
        <span className="dir" title={target}>
          {target === "." ? `(${t("migrate.layers.global")})` : target}
        </span>
      )}
      <span className="num">{group.new.length}</span>
      <span className={`num${group.same.length ? "" : " z"}`}>{group.same.length}</span>
      <span className={`num${group.conflicts.length ? " cf" : " z"}`}>{group.conflicts.length}</span>
      <span className="flags" title={flags.join(" · ")}>
        {flags.join(" · ") || "—"}
      </span>
    </div>
  );
}

/** A plan already imported shows what the import found then, not a fresh comparison with today's memory, in which
    every file improved since would look like a conflict. */
function asImported(groups: MigrationGroup[], result: MigratedGroup[] | undefined): MigrationGroup[] {
  if (!result) return groups;
  const byId = new Map(result.map((done) => [done.id, done]));
  return groups.map((group) => {
    const done = byId.get(group.id);
    return done
      ? { ...group, new: done.copied, same: done.same, edited: done.edited ?? [], conflicts: done.conflicts }
      : group;
  });
}

function GroupDetail({ group, folder }: { group: MigrationGroup; folder: string }) {
  const { t } = useTranslation();
  const status = (file: string) =>
    group.conflicts.includes(file)
      ? "conflict"
      : group.edited?.includes(file)
        ? "edited"
        : group.same.includes(file)
          ? "same"
          : "new";
  const notes = group.converted.filter((file) => file.notes.length);
  return (
    <>
      <h3>{group.target === "." ? t("migrate.layers.global") : group.target}</h3>
      <div className="mg-from">
        {t("migrate.from", { path: short(group.source) })}
        <br />
        {t("migrate.to", { path: `${short(folder)}/memory/${group.target === "." ? "" : `${group.target}/`}` })}
      </div>
      {group.conflicts.length > 0 && (
        <>
          <h4>{t("migrate.conflicts")}</h4>
          {group.conflicts.map((file) => (
            <div className="mg-f" key={file}>
              <span className="mg-st conflict">{t("migrate.head.conflict")}</span>
              <span title={file}>{file}</span>
            </div>
          ))}
        </>
      )}
      {notes.length > 0 && (
        <>
          <h4>{t("migrate.needs")}</h4>
          {notes.map((file) => (
            <div className="mg-q note" key={file.file}>
              {file.file}: {file.notes.join(" ")}
            </div>
          ))}
        </>
      )}
      {group.dropped.length > 0 && (
        <>
          <h4>{t("migrate.notCarried")}</h4>
          {group.dropped.map((line) => (
            <div className="mg-q" key={line}>
              {line}
            </div>
          ))}
        </>
      )}
      {group.converted.length > 0 && (
        <>
          <h4>{t("migrate.changes")}</h4>
          {group.converted.map((file) => (
            <div className="mg-f" key={file.file} title={file.changes.join("\n")}>
              <span className="mg-st same">{file.changes.length}</span>
              <span>{file.file}</span>
            </div>
          ))}
        </>
      )}
      <h4>{t("migrate.files", { n: group.files.length })}</h4>
      {group.files
        .filter((file) => status(file) !== "conflict")
        .map((file) => (
          <div className="mg-f" key={file}>
            <span className={`mg-st ${status(file)}`}>{t(`migrate.head.${status(file)}`)}</span>
            <span title={file}>{file}</span>
            {group.unindexed.includes(file) && <span className="mg-st same">history</span>}
          </div>
        ))}
    </>
  );
}
