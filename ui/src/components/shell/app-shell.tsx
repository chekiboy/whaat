import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  Brain,
  FileText,
  House,
  Info,
  type LucideIcon,
  PanelLeft,
  Scale,
  Search,
  Settings,
  SquareTerminal,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { browseMemoriesOptions, getHealthOptions } from "@/client/@tanstack/react-query.gen";
import { CreateIdentity } from "@/components/identities/create-identity";
import { applyLanguage, LANGUAGES, useLanguage, useTranslation } from "@/i18n";
import { useCurrentHeading } from "@/lib/breadcrumb";
import { useStartCuration } from "@/lib/curation";
import { useIdentitySummaries, useMemoryCounts } from "@/lib/identities";
import { usePersona } from "@/lib/persona";
import { usePreferences } from "@/lib/preferences";
import { type RestartState, type StopState, useRestart, useStop } from "@/lib/restart";
import { ModuleBarProvider, ModuleBarSlot } from "./module-bar";
import "@/styles/shell.css";

type Module = {
  to: "/" | "/memory" | "/reports" | "/terminal" | "/about" | "/settings";
  label: "home" | "memory" | "reports" | "terminal" | "about" | "settings";
  page: string;
  icon: LucideIcon;
  key: string;
};

const HOME: Module = { to: "/", label: "home", page: "Whaat?!", icon: House, key: "h" };
const MODULES: Module[] = [
  HOME,
  { to: "/memory", label: "memory", page: "Memory", icon: Brain, key: "m" },
  { to: "/reports", label: "reports", page: "Reports", icon: FileText, key: "r" },
  { to: "/terminal", label: "terminal", page: "Terminal", icon: SquareTerminal, key: "t" },
];
const ABOUT: Module = { to: "/about", label: "about", page: "About", icon: Info, key: "i" };
const SETTINGS: Module = { to: "/settings", label: "settings", page: "Settings", icon: Settings, key: "s" };

function moduleOf(path: string): Module {
  return [...MODULES, SETTINGS, ABOUT].find((m) => m.to !== "/" && path.startsWith(m.to)) ?? HOME;
}

/** The app frame: rail, module bar, top bar, status bar and the command palette around the page. It opens with an
    identity without asking; only with no identity at all it asks for the first one. */
export function AppShell({ children }: { children: ReactNode }) {
  const { status } = usePersona();
  const { t } = useTranslation();
  const [sideOff, setSideOff] = useState(false);
  const [palette, setPalette] = useState(false);
  const restarting = useRestart();
  const { preferences } = usePreferences();
  const { language } = useLanguage();
  // the server's preferences name the language when they first load; the browser's copy only bridges the first
  // paint, and a later switch goes from here to the server
  const synced = useRef(false);
  useEffect(() => {
    if (synced.current || !preferences) return;
    synced.current = true;
    if (preferences.language && preferences.language !== language) applyLanguage(preferences.language);
  }, [preferences, language]);
  const restart = {
    state: restarting.state,
    error: restarting.error,
    ask: () => {
      if (window.confirm(t("shell.restartConfirm"))) void restarting.restart();
    },
  };
  const stopping = useStop();
  const stop = {
    state: stopping.state,
    ask: () => {
      if (window.confirm(t("shell.stopConfirm"))) void stopping.stop();
    },
  };
  const [menu, setMenu] = useState(false);
  const navigate = useNavigate();
  const path = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    let g = 0;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((open) => !open);
        return;
      }
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable) return;
      if (e.key === "[") setSideOff((off) => !off);
      else if (e.key === "p") setMenu((open) => !open);
      else if (e.key === "g") g = Date.now();
      else if (Date.now() - g < 900) {
        const m = [...MODULES, SETTINGS, ABOUT].find((x) => x.key === e.key);
        g = 0;
        if (m) navigate({ to: m.to });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (status === "loading") return <div className="sh-boot" />;
  if (status === "empty") return <FirstIdentity />;
  const current = moduleOf(path);
  return (
    <ModuleBarProvider>
      <div className={`shell${sideOff ? " side-off" : ""}`}>
        <nav className="sh-rail" aria-label={t("shell.modules")}>
          <Link to="/" className="sh-logo" title={t("shell.home")}>
            <i />
          </Link>
          {MODULES.map((m) => (
            <Link
              key={m.to}
              to={m.to}
              className={`sh-rbtn${current.to === m.to ? " on" : ""}`}
              aria-label={t(`shell.${m.label}`)}
            >
              <m.icon />
              <span className="sh-tip">
                {t(`shell.${m.label}`)}
                {m.to === "/terminal" && <i className="sh-exp-tip"> · {t("terminal.experimental")}</i>}{" "}
                <kbd>G {m.key.toUpperCase()}</kbd>
              </span>
            </Link>
          ))}
          <span className="sh-rbtn soon" aria-disabled="true">
            <Scale />
            <span className="sh-tip">{t("shell.curationSoon")}</span>
          </span>
          <span className="sh-grow" />
          <Link
            to={SETTINGS.to}
            className={`sh-rbtn${current.to === SETTINGS.to ? " on" : ""}`}
            aria-label={t("shell.settings")}
          >
            <SETTINGS.icon />
            <span className="sh-tip">
              {t("shell.settings")} <kbd>G S</kbd>
            </span>
          </Link>
          <Link
            to={ABOUT.to}
            className={`sh-rbtn${current.to === ABOUT.to ? " on" : ""}`}
            aria-label={t("shell.about")}
          >
            <ABOUT.icon />
            <span className="sh-tip">
              {t("shell.about")} <kbd>G I</kbd>
            </span>
          </Link>
          <button
            type="button"
            className="sh-rbtn"
            onClick={() => setSideOff(!sideOff)}
            aria-label={t("shell.sidebar")}
          >
            <PanelLeft />
            <span className="sh-tip">
              {t("shell.sidebar")} <kbd>[</kbd>
            </span>
          </button>
        </nav>
        <aside className="sh-mod">
          <PersonaSwitcher open={menu} setOpen={setMenu} />
          <ModuleBarSlot />
        </aside>
        <TopBar module={current} onPalette={() => setPalette(true)} />
        <main className="sh-main">{children}</main>
        <StatusBar restart={restart} stop={stop} />
        {palette && <Palette onClose={() => setPalette(false)} onRestart={restart.ask} onStop={stop.ask} />}
        {stop.state === "stopped" && (
          <div className="sh-stopped" role="alert">
            <div>
              <b>{t("shell.stopped")}</b>
              <p>{t("shell.stoppedHint")}</p>
            </div>
          </div>
        )}
      </div>
    </ModuleBarProvider>
  );
}

function TopBar({ module, onPalette }: { module: Module; onPalette: () => void }) {
  const { crumbs } = useCurrentHeading();
  const { t } = useTranslation();
  const label = t(`shell.${module.label}`);
  const trail = [label, ...crumbs.map((c) => c.label).filter((c) => c !== module.page && c !== label)];
  return (
    <header className="sh-top">
      <div className="sh-crumb">
        {trail.map((label, i) => (
          <span key={label} className={i === trail.length - 1 ? "cur" : undefined}>
            {i > 0 && " › "}
            {label}
          </span>
        ))}
        <span className="sh-caret">▌</span>
      </div>
      <button type="button" className="sh-kbtn" onClick={onPalette}>
        <Search />
        <span>{t("shell.search")}</span>
        <kbd>⌘K</kbd>
      </button>
    </header>
  );
}

function StatusBar({
  restart,
  stop,
}: {
  restart: { state: RestartState; error: string | null; ask: () => void };
  stop: { state: StopState; ask: () => void };
}) {
  const { source } = useCurrentHeading();
  const { persona } = usePersona();
  const { data: health } = useQuery({ ...getHealthOptions(), staleTime: Number.POSITIVE_INFINITY });
  const { t } = useTranslation();
  const { language, setLanguage } = useLanguage();
  return (
    <footer className="sh-status">
      <span className="online">{t("shell.online")}</span>
      {health && (
        <span>
          {health.instance} · v{health.version}
          {health.commit && ` · ${health.commit}`}
        </span>
      )}
      <button
        type="button"
        className={`sh-restart ${restart.state}`}
        title={restart.error ? `${t("shell.restartBuildFailed")}\n\n${restart.error}` : t("shell.restart")}
        disabled={restart.state === "restarting"}
        onClick={restart.ask}
      >
        ↻{" "}
        {restart.state === "restarting"
          ? t("shell.restarting")
          : restart.state === "failed"
            ? t(restart.error ? "shell.buildFailedShort" : "shell.restartFailed")
            : t("shell.restartShort")}
      </button>
      <button
        type="button"
        className={`sh-restart ${stop.state}`}
        title={t("shell.stop")}
        disabled={stop.state === "stopping" || stop.state === "stopped"}
        onClick={stop.ask}
      >
        ⏻{" "}
        {stop.state === "stopping"
          ? t("shell.stopping")
          : stop.state === "failed"
            ? t("shell.stopFailed")
            : t("shell.stopShort")}
      </button>
      {source && (
        <span className="src" title={source}>
          {source}
        </span>
      )}
      <span className="sh-grow" />
      <span className="sh-lang">
        {LANGUAGES.map((code) => (
          <button
            type="button"
            key={code}
            className={`sh-lang-btn${code === language ? " on" : ""}`}
            title={t(`languages.${code}`)}
            onClick={() => setLanguage(code)}
          >
            {code.toUpperCase()}
          </button>
        ))}
      </span>
      <span>
        {t("shell.persona")} <b>{persona}</b>
      </span>
      <span>
        <kbd>⌘K</kbd> {t("shell.commands")}
      </span>
      <span>
        <kbd>P</kbd> {t("shell.persona")}
      </span>
      <span>
        <kbd>[</kbd> {t("shell.sidebar").toLowerCase()}
      </span>
    </footer>
  );
}

function useIdentities(): string[] {
  const summaries = useIdentitySummaries();
  const counts = useMemoryCounts();
  return summaries ? summaries.map((who) => who.id) : Object.keys(counts);
}

/** Choosing a persona: kept as the last one in the preferences, and written into the URL when the page names one
    there, since the URL's choice wins. */
function useChoose(): (identity: string) => void {
  const { choose } = usePersona();
  const navigate = useNavigate();
  const hasUrlIdentity = useRouterState({
    select: (s) => typeof (s.location.search as Record<string, unknown>).identity === "string",
  });
  return (identity) => {
    choose(identity);
    if (hasUrlIdentity) {
      navigate({
        to: ".",
        search: ((prev: Record<string, unknown>) => ({ ...prev, identity })) as never,
      });
    }
  };
}

function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  return <span className={`sh-av ${size}`}>{name[0]?.toUpperCase()}</span>;
}

function PersonaSwitcher({ open, setOpen }: { open: boolean; setOpen: (open: boolean) => void }) {
  const { persona } = usePersona();
  const choose = useChoose();
  const identities = useIdentities();
  const counts = useMemoryCounts();
  const { t } = useTranslation();
  if (!persona) return null;
  return (
    <div className="sh-who">
      <button type="button" className="sh-who-btn" onClick={() => setOpen(!open)} title={t("shell.switchPersona")}>
        <Avatar name={persona} />
        <b>{persona}</b>
        <span className="chev">▾</span>
        <span className="n">{counts[persona] ?? ""}</span>
      </button>
      {open && (
        <div className="sh-menu" role="menu">
          <div className="hd">Persona</div>
          {identities.map((id) => (
            <button
              type="button"
              key={id}
              className={id === persona ? "on" : undefined}
              onClick={() => {
                choose(id);
                setOpen(false);
              }}
            >
              <Avatar name={id} />
              {id}
              <span className="c">{counts[id] ?? 0}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FirstIdentity() {
  const { t } = useTranslation();
  return (
    <div className="sh-gate">
      <div className="kick">
        <i>■</i> {t("shell.gateKicker")}
      </div>
      <h2>{t("identities.firstTitle")}</h2>
      <p className="hint">{t("identities.firstNote")}</p>
      <CreateIdentity />
    </div>
  );
}

type Command = { kind: string; label: string; sub?: string; run: () => void };

function Palette({ onClose, onRestart, onStop }: { onClose: () => void; onRestart: () => void; onStop: () => void }) {
  const navigate = useNavigate();
  const choose = useChoose();
  const identities = useIdentities();
  const { persona } = usePersona();
  const curation = useStartCuration();
  const { data: browse } = useQuery(browseMemoriesOptions());
  const memories = (browse?.find((who) => who.identity === persona)?.layers ?? []).flatMap((l) => l.memories);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const { t } = useTranslation();
  const { language, setLanguage } = useLanguage();
  useEffect(() => input.current?.focus(), []);
  const commands: Command[] = [
    ...[...MODULES, SETTINGS, ABOUT].map((m) => ({
      kind: t("shell.kindModule"),
      label: t(`shell.${m.label}`),
      run: () => navigate({ to: m.to }),
    })),
    ...LANGUAGES.filter((code) => code !== language).map((code) => ({
      kind: t("shell.kindLanguage"),
      label: t("shell.switchLanguage", { name: t(`languages.${code}`) }),
      run: () => setLanguage(code),
    })),
    { kind: t("shell.kindServer"), label: t("shell.restart"), run: onRestart },
    { kind: t("shell.kindServer"), label: t("shell.stop"), run: onStop },
    ...(curation.can ? [{ kind: t("shell.kindModule"), label: t("curation.start"), run: curation.start }] : []),
    ...identities.map((id) => ({ kind: t("shell.kindPersona"), label: id, run: () => choose(id) })),
    ...memories.map((m) => ({
      kind: m.frontmatter.type ?? t("shell.kindMemory"),
      label: m.frontmatter.description ?? m.path,
      sub: m.path,
      run: () => navigate({ to: "/memory", search: { m: m.path } }),
    })),
  ];
  const needle = query.trim().toLowerCase();
  const hits = commands.filter((c) => `${c.label} ${c.sub ?? ""}`.toLowerCase().includes(needle)).slice(0, 40);
  const pick = (i: number) => {
    const hit = hits[i];
    if (!hit) return;
    hit.run();
    onClose();
  };
  return (
    <div className="sh-veil">
      <button type="button" className="sh-veil-bg" aria-label={t("shell.close")} onClick={onClose} />
      <div className="sh-pal" role="dialog" aria-label={t("shell.paletteLabel")}>
        <input
          ref={input}
          value={query}
          placeholder={t("shell.palettePlaceholder")}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowDown") setActive(Math.min(active + 1, hits.length - 1));
            else if (e.key === "ArrowUp") setActive(Math.max(active - 1, 0));
            else if (e.key === "Enter") pick(active);
          }}
        />
        <ul>
          {hits.map((hit, i) => (
            <li key={`${hit.kind}:${hit.label}`} className={i === active ? "act" : undefined}>
              <button type="button" onClick={() => pick(i)} onMouseEnter={() => setActive(i)}>
                <span className={`k ${hit.kind}`}>{hit.kind}</span>
                <span className="l">{hit.label}</span>
                {hit.sub && <span className="s">{hit.sub}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
