import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal as XTerm } from "@xterm/xterm";
import { useEffect, useRef, useState } from "react";
import "@xterm/xterm/css/xterm.css";
import type { TerminalSession } from "@/client";
import {
  closeTerminalMutation,
  listTerminalsOptions,
  listTerminalsQueryKey,
  migrationPlanListOptions,
  openNativelyMutation,
  openTerminalMutation,
  renameTerminalMutation,
} from "@/client/@tanstack/react-query.gen";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { ProjectPicker } from "@/components/terminal/project-picker";
import { type TFunction, useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { apiBase, authToken } from "@/lib/connection";
import { usePersona } from "@/lib/persona";
import { usePreferences } from "@/lib/preferences";
import { profileOf, useMachineThemes } from "@/lib/terminal-themes";
import "@/styles/overview.css";
import "@/styles/memory.css";

type TerminalSearch = { s?: string; pick?: boolean };

export const Route = createFileRoute("/terminal")({
  validateSearch: (search: Record<string, unknown>): TerminalSearch => ({
    ...(typeof search.s === "string" && search.s ? { s: search.s } : {}),
    ...(search.pick === true || search.pick === "true" ? { pick: true } : {}),
  }),
  component: Terminal,
});

const MIGRATE_LABEL = "memory-migrate";
const PLAN_POLL_MS = 3000;
const MIGRATION_POLL_MS = 2000;

/** A plan id starts with its local save time, `YYYYMMDD-HHMMSS-`; as epoch seconds, to compare with a session's start. */
const savedAt = (planId: string) => {
  const [y, mo, d, h, mi, se] = (/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-/.exec(planId) ?? [])
    .slice(1)
    .map(Number);
  return y === undefined ? 0 : new Date(y, (mo ?? 1) - 1, d, h, mi, se).getTime() / 1000;
};

/** While a migration session is open here, the plan it saves opens on the identity's page by itself, and once its
    turn ends in `[whaat] done` the page comes back; a question keeps the user here. */
function useFollowMigrationPlan(current: TerminalSession | null) {
  const navigate = useNavigate();
  const migrating = current?.label === MIGRATE_LABEL ? current : null;
  const wasDone = useRef<boolean | null>(null);
  useEffect(() => {
    const done = Boolean(migrating?.done);
    if (migrating && done && wasDone.current === false) {
      navigate({ to: "/settings/identities/$identity/migrate", params: { identity: migrating.persona } });
    }
    wasDone.current = migrating ? done : null;
  }, [migrating, navigate]);
  const plans = useQuery({
    ...migrationPlanListOptions({ query: { identity: migrating?.persona ?? "" } }),
    enabled: !!migrating,
    refetchInterval: PLAN_POLL_MS,
  }).data;
  useEffect(() => {
    if (!migrating || !plans) return;
    const saved = plans
      .filter((p) => p.groups === null && !p.imported_at && savedAt(p.id) >= migrating.created)
      .sort((a, b) => b.id.localeCompare(a.id))[0];
    if (saved) {
      navigate({
        to: "/settings/identities/$identity/migrate",
        params: { identity: migrating.persona },
        search: { plan: saved.id },
      });
    }
  }, [migrating, plans, navigate]);
}

const since = (t: TFunction, created: number) => {
  const minutes = Math.max(0, Math.round((Date.now() / 1000 - created) / 60));
  if (minutes < 1) return t("terminal.age.now");
  if (minutes < 60) return t("terminal.age.minutes", { count: minutes });
  const hours = Math.floor(minutes / 60);
  return hours < 24
    ? t("terminal.age.hours", { count: hours })
    : t("terminal.age.days", { count: Math.floor(hours / 24) });
};

/* The terminal module: each window runs in a tmux session of its own on whaat's own tmux server, so closing one by
   accident leaves it running and it can be opened again. The open session is in the URL. */
function Terminal() {
  const { s, pick } = Route.useSearch();
  const navigate = useNavigate({ from: "/terminal" });
  const { t } = useTranslation();
  usePageHeading(sectionTitle("Terminal"), [{ label: t("terminal.title") }]);
  const { persona } = usePersona();
  const queryClient = useQueryClient();
  const { data, error } = useQuery({
    ...listTerminalsOptions({ query: { persona: persona ?? undefined } }),
    enabled: !!persona,
    refetchInterval: (query) =>
      query.state.data?.sessions.some((session) => session.label === MIGRATE_LABEL) ? MIGRATION_POLL_MS : 5000,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: listTerminalsQueryKey() });
  // where a session opens: here, or a terminal app of the machine attached to the same tmux session
  const opener = usePreferences().preferences?.terminal.opener ?? "browser";
  const native = opener !== "browser";
  const [here, setHere] = useState<string | null>(null);
  const openNative = useMutation({ ...openNativelyMutation() });
  const show = (name: string) => {
    if (native) openNative.mutate({ path: { name }, body: {} });
    navigate({ search: { s: name } });
  };
  const open = useMutation({
    ...openTerminalMutation(),
    onSuccess: (session) => {
      refresh();
      show(session.name);
    },
  });
  const close = useMutation({
    ...closeTerminalMutation(),
    onSuccess: (_, variables) => {
      refresh();
      if (variables.path.name === s) navigate({ search: {} });
    },
  });
  const rename = useMutation({ ...renameTerminalMutation(), onSuccess: () => refresh() });
  const [editing, setEditing] = useState<string | null>(null);
  const [state, setState] = useState<Connection>("connecting");
  const sessions = data?.sessions ?? [];
  const current = pick ? null : (sessions.find((session) => session.name === s && !session.gone) ?? null);
  useFollowMigrationPlan(current);
  return (
    <div className="sh-view tm">
      <ModuleBar>
        <ModuleBarSection title={t("terminal.sessions")}>
          <button
            type="button"
            disabled={!persona}
            className={`sh-item${pick ? " on" : ""}`}
            onClick={() => navigate({ search: { pick: true } })}
          >
            {t("terminal.newSession")}
          </button>
          {sessions.map((session) => (
            <div key={session.name} className={`sh-item tm-row${session.name === s ? " on" : ""}`}>
              {editing === session.name ? (
                <div className="tm-open">
                  <i className={`tm-dot ${stateOf(session, s)}`} />
                  <SessionNameInput
                    initial={session.label ?? ""}
                    placeholder={`${session.cwd.split("/").pop() || session.cwd} · ${session.number}`}
                    onDone={(label) => {
                      setEditing(null);
                      if (label !== null && label !== (session.label ?? ""))
                        rename.mutate({ path: { name: session.name }, body: { label } });
                    }}
                  />
                </div>
              ) : (
                <button
                  type="button"
                  className="tm-open"
                  title={t("terminal.rowTitle")}
                  onClick={() => show(session.name)}
                  onDoubleClick={() => setEditing(session.name)}
                >
                  <i className={`tm-dot ${stateOf(session, s)}`} title={t(`terminal.states.${stateOf(session, s)}`)} />
                  <span className="tm-lines">
                    <span className="tm-name">
                      <span className="tm-proj" title={session.cwd}>
                        {session.label || session.cwd.split("/").pop() || session.cwd}
                      </span>
                      {!session.label && <span className="tm-num">· {session.number}</span>}
                    </span>
                    <small className="tm-age">
                      {session.label ? `${session.cwd.split("/").pop() || session.cwd} · ${session.number} · ` : ""}
                      {statusLine(t, session, s)}
                    </small>
                  </span>
                </button>
              )}
              <button
                type="button"
                className="tm-kill"
                title={t(session.gone ? "terminal.forget" : "terminal.stop", { name: session.name })}
                onClick={() => {
                  if (
                    window.confirm(
                      t(session.gone ? "terminal.forgetConfirm" : "terminal.stopConfirm", { name: session.name }),
                    )
                  )
                    close.mutate({ path: { name: session.name } });
                }}
              >
                ✕
              </button>
            </div>
          ))}
          {persona && data && sessions.length === 0 && <p className="sh-note">{t("terminal.none")}</p>}
          {sessions.length > 0 && (
            <ul className="tm-legend">
              {STATES.map((key) => (
                <li key={key}>
                  <i className={`tm-dot ${key}`} />
                  {t(`terminal.states.${key}`)}
                </li>
              ))}
            </ul>
          )}
          {error && <p className="sh-note">{t("terminal.readError", { error: JSON.stringify(error) })}</p>}
        </ModuleBarSection>
        <ModuleBarSection title={t("terminal.settings")}>
          <div className="sh-setting">
            <span>{t("terminal.defaultCommand")}</span>
            <code>{data?.command ?? "…"}</code>
            <Link to="/settings" hash="st-terminal" className="sh-setlink">
              {t("settings.fromTerminal")}
            </Link>
          </div>
        </ModuleBarSection>
      </ModuleBar>
      <div className="sh-tb">
        <h1>{t("terminal.title")}</h1>
        <span className="sh-experimental" title={t("terminal.experimentalNote")}>
          {t("terminal.experimental")}
        </span>
        <span className="meta tm-meta" title={current ? `${current.command} · ${current.cwd}` : undefined}>
          {persona}
          {current ? ` · ${current.name} · ${current.command} · ${current.cwd}` : ""}
        </span>
        <span className="grow" />
        {current && (
          <span className={`tm-state${state === "open" ? " ok" : ""}`}>
            {state === "open"
              ? t("terminal.connected")
              : state === "connecting"
                ? t("terminal.connecting")
                : t(`terminal.closed.${state}`)}
          </span>
        )}
        {current && (
          <button
            type="button"
            className="dv-btn"
            title={t("terminal.detachTitle")}
            onClick={() => navigate({ search: {} })}
          >
            {t("terminal.detach")}
          </button>
        )}
      </div>
      <div className={`sh-pane tm-pane${current ? " full" : ""}`}>
        {pick && persona ? (
          <ProjectPicker
            command={data?.command ?? "…"}
            starting={open.isPending}
            onStart={(cwd) => open.mutate({ body: { persona, cwd } })}
            onCancel={() => navigate({ search: {} })}
          />
        ) : current && native && here !== current.name ? (
          <div className="tm-tx tm-empty">
            <p className="hl">
              {openNative.isError
                ? t("terminal.nativeFailed", { app: t(`settings.openers.${opener}`) })
                : t("terminal.nativeOpened", {
                    name: current.label || current.name,
                    app: t(`settings.openers.${opener}`),
                  })}
            </p>
            {openNative.isError && (
              <p>{String((openNative.error as { detail?: string })?.detail ?? openNative.error)}</p>
            )}
            <p>{t("terminal.nativeHelp")}</p>
            <div className="tm-native">
              <button
                type="button"
                className="dv-btn"
                onClick={() => openNative.mutate({ path: { name: current.name }, body: {} })}
              >
                {t("terminal.nativeAgain", { app: t(`settings.openers.${opener}`) })}
              </button>
              <button type="button" className="dv-btn on" onClick={() => setHere(current.name)}>
                {t("terminal.nativeHere")}
              </button>
            </div>
          </div>
        ) : current ? (
          <TerminalWindow key={current.name} session={current} onState={setState} />
        ) : (
          <div className="tm-tx tm-empty">
            <p className="hl">{s && data ? t("terminal.gone", { name: s }) : t("terminal.noOpen")}</p>
            <p>{t("terminal.help")}</p>
            <span className="cur" />
          </div>
        )}
      </div>
    </div>
  );
}

/* What a session is doing, as its dot shows it: the one open here, one whose start command has exited (only the
   shell waits), one another window shows, or one running with no window on it. */
const STATES = ["open", "stopped", "elsewhere", "background", "gone"] as const;
type SessionState = (typeof STATES)[number];
type Connection = "connecting" | "open" | "refused" | "gone" | "lost";

function stateOf(session: TerminalSession, open: string | undefined): SessionState {
  if (session.gone) return "gone";
  if (session.name === open) return "open";
  if (session.idle) return "stopped";
  return session.attached ? "elsewhere" : "background";
}

function statusLine(t: TFunction, session: TerminalSession, open: string | undefined): string {
  const age = since(t, session.created);
  if (session.gone) return t("terminal.status.gone", { age });
  if (session.idle) return t("terminal.status.stopped", { age });
  if (session.name === open) return t("terminal.status.running", { age });
  return t(session.attached ? "terminal.status.elsewhere" : "terminal.status.background", { age });
}

/* The inline editor of a session's name: Enter or leaving the field saves, Esc cancels; an empty name takes it off. */
function SessionNameInput({
  initial,
  placeholder,
  onDone,
}: {
  initial: string;
  placeholder: string;
  onDone: (label: string | null) => void;
}) {
  const { t } = useTranslation();
  const label = t("terminal.nameLabel");
  const done = useRef(false);
  const finish = (label: string | null) => {
    if (done.current) return;
    done.current = true;
    onDone(label === null ? null : label.trim());
  };
  return (
    <input
      className="tm-rename"
      // biome-ignore lint/a11y/noAutofocus: the field appears because the user asked to rename, so it takes the focus
      autoFocus
      maxLength={60}
      defaultValue={initial}
      placeholder={placeholder}
      aria-label={label}
      onFocus={(e) => e.currentTarget.select()}
      onBlur={(e) => finish(e.currentTarget.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") finish(e.currentTarget.value);
        if (e.key === "Escape") finish(null);
        e.stopPropagation();
      }}
    />
  );
}

function socketUrl(name: string): string {
  const url = new URL(
    `/api/v1/terminal/sessions/${encodeURIComponent(name)}/attach`,
    apiBase() || window.location.origin,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

const CLOSED: Record<number, Connection> = { 4401: "refused", 4404: "gone" };

/* One session in xterm: keys go out as binary frames, the screen comes back the same way, a resize as a text frame.
   Unmounting closes the socket, which only detaches: the session keeps running. */
function TerminalWindow({ session, onState }: { session: TerminalSession; onState: (state: Connection) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const name = usePreferences().preferences?.terminal.theme;
  const machine = useMachineThemes();
  const profile = profileOf(name, machine);
  const theme = profile.theme;
  const profileRef = useRef(profile);
  profileRef.current = profile;
  const look = JSON.stringify(profile);
  // a changed profile repaints the open session at once: colours, font, cursor, Option key
  // biome-ignore lint/correctness/useExhaustiveDependencies: `look` stands for the profile's content
  useEffect(() => {
    const term = terminal.current;
    if (!term) return;
    Object.assign(term.options, profileRef.current);
    fitRef.current?.fit();
  }, [look]);
  const report = useRef(onState);
  report.current = onState;
  useEffect(() => {
    const setState = (state: Connection) => report.current(state);
    setState("connecting");
    if (!host.current) return;
    const term = new XTerm({ ...profileRef.current });
    terminal.current = term;
    const fit = new FitAddon();
    fitRef.current = fit;
    term.loadAddon(fit);
    term.open(host.current);
    fit.fit();
    const ws = new WebSocket(socketUrl(session.name), ["whaat", authToken()]);
    ws.binaryType = "arraybuffer";
    const encoder = new TextEncoder();
    const sendSize = () => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cols: term.cols, rows: term.rows }));
    };
    ws.onopen = () => {
      setState("open");
      sendSize();
      term.focus();
    };
    ws.onmessage = (event) => term.write(new Uint8Array(event.data as ArrayBuffer));
    ws.onclose = (event) => setState(CLOSED[event.code] ?? "lost");
    const input = term.onData((text) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(encoder.encode(text));
    });
    const resized = new ResizeObserver(() => {
      fit.fit();
      sendSize();
    });
    resized.observe(host.current);
    return () => {
      resized.disconnect();
      input.dispose();
      ws.onclose = null;
      ws.close();
      term.dispose();
      terminal.current = null;
    };
  }, [session.name]);
  return <div ref={host} className="tm-term" style={{ background: theme.background }} />;
}
