import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  browseFoldersOptions,
  forgetProjectMutation,
  listProjectsOptions,
  listProjectsQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { useTranslation } from "@/i18n";

const home = (path: string, root: string | null) =>
  root && path.startsWith(root) ? `~${path.slice(root.length)}` : path;

const join = (parent: string, name: string) => `${parent === "/" ? "" : parent}/${name}`;

/** Where a new session starts, picked as in a file browser: one click selects a folder, a double click (or Enter)
    opens it; the home folder, or the folder given as `start`, is selected at first. The folders sessions were started in sit beside it as favourites,
    saved by the server when a session starts. A browser cannot hand over a folder's path, so the
    browsing runs on the server's disk. */
export function ProjectPicker({
  command,
  start: startAt = "~",
  starting,
  onStart,
  onCancel,
}: {
  command: string;
  start?: string;
  starting: boolean;
  onStart: (cwd: string) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [path, setPath] = useState(startAt);
  const [chosen, setChosen] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const projects = useQuery(listProjectsOptions());
  const folders = useQuery(browseFoldersOptions({ query: { path, hidden } }));
  const root = useQuery(browseFoldersOptions({ query: { path: "~" } })).data?.path ?? null;
  const forget = useMutation({
    ...forgetProjectMutation(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listProjectsQueryKey() }),
  });
  const here = folders.data?.path ?? null;
  const selected = chosen ?? here;
  const saved = (projects.data?.projects ?? []).filter((project) => project.path !== root);
  const go = (to: string) => {
    setPath(to);
    setChosen(null);
  };
  const start = () => selected && onStart(selected);
  return (
    <div className="pp">
      <nav className="pp-favs" aria-label={t("terminal.picker.favourites")}>
        <h2>{t("terminal.picker.favourites")}</h2>
        {root && (
          <button
            type="button"
            className={`pp-fav${here === root && !chosen ? " on" : ""}`}
            onClick={() => go(root)}
            onDoubleClick={() => onStart(root)}
          >
            <b>~</b>
            <span>{t("terminal.picker.home")}</span>
          </button>
        )}
        {saved.length > 0 && <h3>{t("terminal.picker.earlier")}</h3>}
        {saved.map((project) => (
          <div key={project.path} className={`pp-fav-row${project.exists ? "" : " gone"}`}>
            <button
              type="button"
              className={`pp-fav${here === project.path && !chosen ? " on" : ""}`}
              disabled={!project.exists}
              title={project.exists ? project.path : t("terminal.picker.missing", { path: project.path })}
              onClick={() => go(project.path)}
              onDoubleClick={() => onStart(project.path)}
            >
              <b>{project.path.split("/").pop()}</b>
              <span>{home(project.path, root)}</span>
            </button>
            <button
              type="button"
              className="pp-x"
              title={t("terminal.picker.forget")}
              onClick={() => forget.mutate({ query: { path: project.path } })}
            >
              ✕
            </button>
          </div>
        ))}
      </nav>
      <section className="pp-browse">
        <div className="pp-bar">
          <button
            type="button"
            className="dv-btn"
            disabled={!folders.data?.parent}
            onClick={() => folders.data?.parent && go(folders.data.parent)}
            title={t("terminal.picker.up")}
          >
            ↑
          </button>
          <code className="pp-path" title={here ?? ""}>
            {here ? home(here, root) : "…"}
          </code>
          <label className="pp-hidden">
            <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />{" "}
            {t("terminal.picker.hidden")}
          </label>
        </div>
        <div className="pp-list">
          {folders.error && <p className="pp-none">{t("terminal.picker.unreadable")}</p>}
          {folders.data?.folders.length === 0 && <p className="pp-none">{t("terminal.picker.empty")}</p>}
          {here &&
            folders.data?.folders.map((f) => {
              const target = join(here, f.name);
              return (
                <button
                  type="button"
                  key={f.name}
                  className={`pp-dir${chosen === target ? " on" : ""}`}
                  title={t("terminal.picker.dirTitle")}
                  onClick={() => setChosen(target)}
                  onDoubleClick={() => go(target)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      go(target);
                    }
                  }}
                >
                  <span className="ic">▸</span>
                  {f.name}
                  {f.repo && <span className="pp-repo">git</span>}
                </button>
              );
            })}
        </div>
        <div className="pp-foot">
          <code title={selected ?? ""}>
            cd {selected ? home(selected, root) : "…"} && {command}
          </code>
          <span className="grow" />
          <button type="button" className="dv-btn" onClick={onCancel}>
            {t("terminal.picker.cancel")}
          </button>
          <button type="button" className="dv-btn on" disabled={!selected || starting} onClick={start}>
            {t("terminal.picker.startHere")}
          </button>
        </div>
      </section>
    </div>
  );
}
