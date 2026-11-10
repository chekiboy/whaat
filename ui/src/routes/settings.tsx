import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import type { ITheme } from "@xterm/xterm";
import { Fragment, useEffect, useState } from "react";
import { type CreatedIdentity, forgetProject } from "@/client";
import {
  createIdentityMutation,
  listIdentitiesQueryKey,
  listTerminalAppsOptions,
  regenerateTokenMutation,
} from "@/client/@tanstack/react-query.gen";
import { CreateIdentity, TokenOnce } from "@/components/identities/create-identity";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { LANGUAGES, useLanguage, useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { useIdentitySummaries, useMemoryCounts } from "@/lib/identities";
import { usePersona } from "@/lib/persona";
import { usePreferences } from "@/lib/preferences";
import { useMachineThemes } from "@/lib/terminal-themes";
import "@/styles/overview.css";

export const Route = createFileRoute("/settings")({
  component: Settings,
});

const SECTIONS = [
  ["st-identities", "identities"],
  ["st-general", "general"],
  ["st-terminal", "terminal"],
] as const;

/* The app's settings in one place, kept in the instance's preferences file: the
   language, and the terminal's default command, theme and saved folders. */
function Settings() {
  const { t } = useTranslation();
  usePageHeading(sectionTitle("Settings"), [{ label: t("settings.title") }]);
  const { language, setLanguage } = useLanguage();
  const { preferences, update, saving } = usePreferences();
  const terminal = preferences?.terminal;
  const projects = terminal?.projects ?? [];
  const machine = useMachineThemes();
  // only this machine's themes; the tab of the current theme is open
  const sources = [...new Set(machine.map((theme) => theme.source))];
  const chosenSource = machine.find((theme) => theme.id === terminal?.theme)?.source ?? sources[0] ?? null;
  const [source, setSource] = useState<string | null>(null);
  const shownSource = source ?? chosenSource;
  const shown: { id: string; name: string; colors: ITheme }[] = machine
    .filter((theme) => theme.source === shownSource)
    .map((theme) => ({ ...theme, colors: theme.colors as ITheme }));
  const apps = useQuery(listTerminalAppsOptions()).data?.installed ?? [];
  const openers = ["browser", ...apps] as const;
  const [command, setCommand] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => setCommand(terminal?.command ?? ""), [terminal?.command]);
  const saveCommand = async (value: string) => {
    await update({ terminal: { command: value } });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };
  return (
    <div className="sh-view st">
      <ModuleBar>
        <ModuleBarSection title={t("settings.title")}>
          {SECTIONS.map(([id, key]) => (
            <button
              type="button"
              key={id}
              className="sh-item"
              onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              {t(`settings.${key}`)}
            </button>
          ))}
        </ModuleBarSection>
      </ModuleBar>
      <div className="sh-tb">
        <h1>{t("settings.title")}</h1>
      </div>
      <div className="sh-pane st-pane">
        <Identities />
        <h2 className="st-h" id="st-general">
          {t("settings.general")}
        </h2>
        <section className="st-row">
          <div className="st-label">
            <b>{t("settings.language")}</b>
            <p>{t("settings.languageNote")}</p>
          </div>
          <div className="st-choices">
            {LANGUAGES.map((code) => (
              <button
                type="button"
                key={code}
                className={`st-choice${code === language ? " on" : ""}`}
                onClick={() => setLanguage(code)}
              >
                {t(`languages.${code}`)}
              </button>
            ))}
          </div>
        </section>

        <h2 className="st-h" id="st-terminal">
          {t("settings.terminal")}
        </h2>
        <section className="st-row">
          <div className="st-label">
            <b>{t("settings.opener")}</b>
            <p>{t("settings.openerNote")}</p>
          </div>
          <div className="st-choices">
            {openers.map((key) => (
              <button
                type="button"
                key={key}
                className={`st-choice${(terminal?.opener ?? "browser") === key ? " on" : ""}`}
                onClick={() => void update({ terminal: { opener: key as "browser" | "terminal-app" | "iterm2" } })}
              >
                {t(`settings.openers.${key as "browser" | "terminal-app" | "iterm2"}`)}
              </button>
            ))}
          </div>
        </section>
        <section className="st-row">
          <div className="st-label">
            <b>{t("settings.command")}</b>
            <p>{t("settings.commandNote")}</p>
          </div>
          <form
            className="st-command"
            onSubmit={(e) => {
              e.preventDefault();
              void saveCommand(command);
            }}
          >
            <input
              className="sh-search st-input"
              value={command}
              placeholder={terminal?.default_command}
              aria-label={t("settings.command")}
              onChange={(e) => setCommand(e.target.value)}
            />
            <button type="submit" className="dv-btn on" disabled={saving || command === terminal?.command}>
              {saved ? t("settings.saved") : t("settings.save")}
            </button>
            <button
              type="button"
              className="dv-btn"
              disabled={saving || terminal?.command === terminal?.default_command}
              onClick={() => void saveCommand("")}
            >
              {t("settings.reset")}
            </button>
            <small>{terminal && t("settings.commandDefault", { command: terminal.default_command })}</small>
          </form>
        </section>
        <section className="st-row">
          <div className="st-label">
            <b>{t("settings.inside")}</b>
            <p>{t("settings.insideNote")}</p>
          </div>
          <div className="st-themebox">
            <div className="st-sources" role="tablist" aria-label={t("settings.themeSource")}>
              {sources.map((name) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={name === shownSource}
                  key={name}
                  className={`st-choice${name === shownSource ? " on" : ""}`}
                  onClick={() => {
                    setSource(name);
                    // choosing the app takes its own default profile, unless one of its profiles is already chosen
                    const current = machine.find((theme) => theme.id === terminal?.theme);
                    const fallback = machine.find((theme) => theme.source === name && theme.default);
                    if (current?.source !== name && fallback) void update({ terminal: { theme: fallback.id } });
                  }}
                >
                  {name}
                  <small> {machine.filter((theme) => theme.source === name).length}</small>
                </button>
              ))}
            </div>
            <p className="st-none">{sources.length ? t("settings.machineNote") : t("settings.noMachineThemes")}</p>
            <div className="st-themes">
              {shown.map(({ id, name, colors: theme }) => {
                return (
                  <button
                    type="button"
                    key={id}
                    className={`st-theme${terminal?.theme === id ? " on" : ""}`}
                    onClick={() => void update({ terminal: { theme: id } })}
                  >
                    <span className="st-preview" style={{ background: theme.background, color: theme.foreground }}>
                      <span style={{ color: theme.green }}>~/whaat</span>{" "}
                      <span style={{ color: theme.blue }}>main</span> ${" "}
                      <span style={{ color: theme.yellow }}>claude</span>
                      <i style={{ background: theme.cursor }} />
                    </span>
                    <span className="st-tname">
                      {name}
                      {machine.find((m) => m.id === id)?.default && (
                        <em className="st-default">{t("settings.appDefault")}</em>
                      )}
                    </span>
                    <span className="st-tfont">
                      {(() => {
                        const m = machine.find((x) => x.id === id);
                        return m
                          ? `${m.font.family === "ui-monospace" ? "SF Mono" : m.font.family} ${m.font.size} · ${t(`settings.cursors.${m.cursor.style as "block" | "underline" | "bar"}`)}`
                          : "";
                      })()}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>
        <section className="st-row">
          <div className="st-label">
            <b>{t("settings.folders")}</b>
            <p>{t("settings.foldersNote")}</p>
          </div>
          <ul className="st-folders">
            {terminal && projects.length === 0 && <li className="st-none">{t("settings.noFolders")}</li>}
            {projects.map((project) => (
              <li key={project.path}>
                <code>{project.path}</code>
                <button
                  type="button"
                  className="dv-btn"
                  onClick={async () => {
                    await forgetProject({ query: { path: project.path } });
                    void update({});
                  }}
                >
                  {t("settings.remove")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

/* Who whaat works with: the identity the app opens with, the identities with their folder and token,
   and adding one; the only place an identity is created. */
function Identities() {
  const { t } = useTranslation();
  const { preferences, update } = usePreferences();
  const identities = useIdentitySummaries() ?? [];
  const counts = useMemoryCounts();
  const { persona } = usePersona();
  const openWith = preferences?.identity?.open_with ?? "last";
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<{ token: CreatedIdentity; regenerated: boolean } | null>(null);
  const done = (regenerated: boolean) => async (token: CreatedIdentity) => {
    setIssued({ token, regenerated });
    await queryClient.invalidateQueries({ queryKey: listIdentitiesQueryKey() });
  };
  const regenerate = useMutation({ ...regenerateTokenMutation(), onSuccess: done(true) });
  const create = useMutation({ ...createIdentityMutation(), onSuccess: done(false) });
  const busy = regenerate.isPending || create.isPending;
  return (
    <>
      <h2 className="st-h" id="st-identities">
        {t("settings.identities")}
      </h2>
      <section className="st-row">
        <div className="st-label">
          <b>{t("identities.openWith")}</b>
          <p>{t("identities.openWithNote")}</p>
        </div>
        <div className="st-choices">
          {["last", ...identities.map((who) => who.id)].map((choice) => (
            <button
              type="button"
              key={choice}
              className={`st-choice${choice === openWith ? " on" : ""}`}
              onClick={() => update({ identity: { open_with: choice } })}
            >
              {choice === "last" ? t("identities.openLast") : choice}
            </button>
          ))}
        </div>
      </section>
      <section className="st-row">
        <div className="st-label">
          <b>{t("identities.list")}</b>
          <p>{t("identities.listNote")}</p>
        </div>
        <div>
          <table className="id-table">
            <thead>
              <tr>
                <th>{t("identities.name")}</th>
                <th className="r">{t("identities.memories")}</th>
                <th className="r">{t("identities.reports")}</th>
                <th>{t("identities.folder")}</th>
                <th>{t("identities.token")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {identities.map((who) => (
                <Fragment key={who.id}>
                  <tr className={who.id === persona ? "on" : undefined}>
                    <td className="nm">
                      <span className="sh-av md">{who.id[0]?.toUpperCase()}</span>
                      {who.id}
                      {who.default && <span className="id-tag">{t("identities.default")}</span>}
                    </td>
                    <td className="r">{counts[who.id] ?? 0}</td>
                    <td className="r">{who.report_count}</td>
                    <td>{who.has_private_folder ? <span className="ok">● {t("identities.private")}</span> : "—"}</td>
                    <td>
                      {who.has_token ? (
                        <span className="ok">● {t("identities.hasToken")}</span>
                      ) : (
                        <span>○ {t("identities.noToken")}</span>
                      )}
                    </td>
                    <td className="act">
                      {who.has_token ? (
                        <button
                          type="button"
                          className="id-act"
                          disabled={busy}
                          onClick={() => {
                            if (window.confirm(t("identities.regenerateConfirm", { name: who.id })))
                              regenerate.mutate({ path: { identity: who.id } });
                          }}
                        >
                          ↻ {t("identities.regenerate")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="id-act"
                          disabled={busy}
                          onClick={() => create.mutate({ body: { id: who.id } })}
                        >
                          + {t("identities.issue")}
                        </button>
                      )}
                    </td>
                  </tr>
                  <tr className={`sub${who.id === persona ? " on" : ""}`}>
                    <td colSpan={6}>
                      <div className="id-agent-row">
                        <span className="lbl">{t("identities.agentConfig")}</span>
                        <AgentConfig identity={who.id} current={preferences?.identity?.agents?.[who.id] ?? ""} />
                        <Link
                          to="/settings/identities/$identity/migrate"
                          params={{ identity: who.id }}
                          className="id-migrate"
                        >
                          ↧ {t("migrate.title")}
                        </Link>
                      </div>
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
          {(regenerate.isError || create.isError) && <p className="id-error">{t("identities.failed")}</p>}
          {issued && <TokenOnce issued={issued.token} regenerated={issued.regenerated} />}
          <CreateIdentity onCreated={done(false)} />
        </div>
      </section>
    </>
  );
}

/* An identity's own Claude Code config folder: a terminal session of that identity then starts
   claude with it, whaat's plugin and the identity's token; empty means the plain start command. */
function AgentConfig({ identity, current }: { identity: string; current: string }) {
  const { t } = useTranslation();
  const { update } = usePreferences();
  const [value, setValue] = useState(current);
  const [state, setState] = useState<"idle" | "saved" | "failed">("idle");
  useEffect(() => setValue(current), [current]);
  const save = async () => {
    if (value.trim() === current) return;
    try {
      await update({ identity: { agents: { [identity]: value.trim() } } });
      setState("saved");
      setTimeout(() => setState("idle"), 1500);
    } catch {
      setState("failed");
    }
  };
  return (
    <input
      className={`sh-search st-input id-agent${state === "failed" ? " bad" : ""}`}
      value={value}
      placeholder={t("identities.agentConfigPlaceholder")}
      title={state === "failed" ? t("identities.agentConfigFailed") : state === "saved" ? t("settings.saved") : value}
      spellCheck={false}
      onChange={(event) => {
        setValue(event.target.value);
        setState("idle");
      }}
      onBlur={save}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
    />
  );
}
