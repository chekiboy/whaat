import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { CurationReportBody, CurationRow, DecisionsSent, RowFigure } from "@/client";
import {
  curationPageOptions,
  listTerminalsOptions,
  runStateOptions,
  sendDecisionsMutation,
  sendDoneMutation,
  sendRevertMutation,
} from "@/client/@tanstack/react-query.gen";
import { Diagram } from "@/components/curation/diagram";
import { inline, Markdown } from "@/components/curation/markdown";
import { ACTIONS, MemoryMap } from "@/components/curation/memory-map";
import { Panel } from "@/components/report-frame";
import { useTranslation } from "@/i18n";
import "@/styles/curation.css";

/* The curation report page: the memory map, the
   proposals as cards with their diagrams, the filter and selection toolbar, Send / Revert / Done into the curation
   session. Two things are whaat's own: a row can be discarded, and the user's word per row is kept in
   the report's JSON instead of side files. */

const RISKY = new Set(["delete", "merge", "move"]);
type Draft = { sel: number[]; disc: number[]; notes: Record<string, string> };

const isApplied = (row: CurationRow) => Boolean((row.applied ?? "").replace(/[\s—]/g, ""));
const plain = (text: string) => text.replace(/[`*]/g, "");

function loadDraft(key: string): Draft {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw) return { sel: [], disc: [], notes: {}, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable: start empty */
  }
  return { sel: [], disc: [], notes: {} };
}

export function CurationReportView({
  report,
  reportId,
  identity,
}: {
  report: CurationReportBody;
  reportId: string;
  identity: string | null | undefined;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const storageKey = `whaat-curation:${reportId}`;
  const view = useQuery(curationPageOptions({ query: { report_id: reportId } }));
  const terminals = useQuery({
    ...listTerminalsOptions({ query: identity ? { persona: identity } : {} }),
    enabled: Boolean(identity),
  });
  const session = terminals.data?.sessions.find((s) => s.label === "memory-curation" && !s.gone) ?? null;

  const [draft, setDraft] = useState<Draft>(() => loadDraft(storageKey));
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(draft));
    } catch {
      /* storage unavailable: the draft lives only on this page */
    }
  }, [draft, storageKey]);
  const selected = new Set(draft.sel);
  const discarding = new Set(draft.disc);

  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [flash, setFlash] = useState<number | null>(null);
  const [modal, setModal] = useState<ReactNode>(null);
  const cardRefs = useRef<Record<number, HTMLDetailsElement | null>>({});

  const figures = useMemo(() => new Map<number, RowFigure>((view.data?.rows ?? []).map((f) => [f.n, f])), [view.data]);
  const rows = report.rows;
  const discarded = (row: CurationRow) =>
    discarding.has(row.n) || (row.decision === "reject" && !discarding.has(-row.n));
  const openRow = (row: CurationRow) => !isApplied(row) && !row.sent_at && !discarded(row);
  const sentFiles = new Set(
    rows.filter((row) => row.sent_at && !isApplied(row)).flatMap((row) => figures.get(row.n)?.files ?? []),
  );

  const visible = (row: CurationRow) => {
    const byFilter =
      filter === "all" ||
      (filter === "open" && !isApplied(row)) ||
      (filter === "applied" && isApplied(row)) ||
      (filter === "sent" && Boolean(row.sent_at)) ||
      (filter === "unsent" && !row.sent_at) ||
      (filter === "discarded" && discarded(row)) ||
      row.actions.includes(filter as CurationRow["actions"][number]);
    const text = [row.n, row.file, row.actions.join(" "), row.target, row.reason, row.evidence, row.applied, row.note]
      .join(" ")
      .toLowerCase();
    return byFilter && (!query || text.includes(query.toLowerCase()));
  };

  const counts = new Map<string, number>();
  const sentCounts = new Map<string, number>();
  // a row with several actions counts under each, so every chip finds it
  for (const row of rows) {
    for (const action of row.actions) {
      counts.set(action, (counts.get(action) ?? 0) + 1);
      if (row.sent_at) sentCounts.set(action, (sentCounts.get(action) ?? 0) + 1);
    }
  }
  const actionOrder = [
    ...ACTIONS.filter((a) => counts.has(a)),
    ...[...counts.keys()].filter((a) => !(ACTIONS as readonly string[]).includes(a)).sort(),
  ];
  const onlyFix = (row: CurationRow) => row.actions.length === 1 && row.actions[0] === "fix";
  const fixRows = rows.filter(onlyFix);
  const others = rows.filter((row) => !onlyFix(row));
  const grouped = fixRows.length > 1;

  const setSel = (numbers: number[], on: boolean) =>
    setDraft((d) => {
      const sel = new Set(d.sel);
      for (const n of numbers) {
        if (on) sel.add(n);
        else sel.delete(n);
      }
      return { ...d, sel: [...sel].sort((a, b) => a - b) };
    });
  const toggleDiscard = (row: CurationRow) =>
    setDraft((d) => {
      const disc = new Set(d.disc);
      // a saved discard is taken back by marking it with its negative number until the next send
      const key = row.decision === "reject" ? -row.n : row.n;
      if (disc.has(key)) disc.delete(key);
      else disc.add(key);
      return { ...d, disc: [...disc], sel: d.sel.filter((n) => n !== row.n) };
    });
  const setNote = (n: number, text: string) =>
    setDraft((d) => {
      const notes = { ...d.notes };
      if (text.trim()) notes[n] = text;
      else delete notes[n];
      return { ...d, notes };
    });

  const decisions = useMutation({ ...sendDecisionsMutation() });
  const revert = useMutation({ ...sendRevertMutation() });
  const done = useMutation({ ...sendDoneMutation() });
  const refresh = () => {
    void queryClient.invalidateQueries();
  };
  const close = () => setModal(null);
  const kicker = t("curation.modal.kicker", { session: session?.name ?? "—" });
  const openSession = () => {
    if (session) void navigate({ to: "/terminal", search: { s: session.name } });
  };

  const jump = (file: string) => {
    const row = [...others, ...fixRows].find((r) => figures.get(r.n)?.files.includes(file));
    if (!row) return;
    setFilter("all");
    setOpen((o) => ({ ...o, [row.n]: true, ...(onlyFix(row) && grouped ? { fix: true } : {}) }));
    setFlash(row.n);
    window.setTimeout(() => cardRefs.current[row.n]?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    window.setTimeout(() => setFlash(null), 1200);
  };

  const send = () => {
    const apply = rows.filter((row) => selected.has(row.n));
    const newDiscards = rows.filter((row) => discarding.has(row.n));
    const takenBack = rows.filter((row) => discarding.has(-row.n));
    if (apply.length === 0 && newDiscards.length === 0 && takenBack.length === 0) {
      setModal(
        <Modal title={t("curation.modal.nothingTitle")} onClose={close}>
          <p>{t("curation.modal.nothingText")}</p>
          <div className="cur-actions">
            <button type="button" onClick={close}>
              {t("curation.modal.ok")}
            </button>
          </div>
        </Modal>,
      );
      return;
    }
    const risky = apply.filter((row) => row.actions.some((action) => RISKY.has(action))).length;
    const call = `/whaat:memory-curation apply-rows report=${reportId} confirmed=report-page`;
    const note = (row: CurationRow) => draft.notes[row.n]?.trim() || null;
    const body = {
      report_id: reportId,
      rows: [
        ...apply.map((row) => ({ n: row.n, decision: "apply" as const, note: note(row) })),
        ...newDiscards.map((row) => ({ n: row.n, decision: "reject" as const, note: note(row) })),
        ...takenBack.map((row) => ({ n: row.n, decision: null, note: row.note ?? null })),
      ],
    };
    const sentNumbers = new Set(body.rows.map((row) => String(row.n)));
    const submit = (setError: (error: string) => void) =>
      decisions.mutate(
        { body },
        {
          onSuccess: (result) => {
            setDraft((d) => ({
              sel: d.sel.filter((n) => !apply.some((row) => row.n === n)),
              disc: [],
              notes: Object.fromEntries(Object.entries(d.notes).filter(([n]) => !sentNumbers.has(n))),
            }));
            refresh();
            setModal(<SentModal result={result} applied={apply.length} onClose={close} onOpen={openSession} />);
          },
          onError: (error) => setError(errorText(error)),
        },
      );
    setModal(
      <ConfirmModal
        kicker={kicker}
        title={apply.length ? t("curation.modal.sendTitle", { count: apply.length }) : t("curation.bar.saveDiscards")}
        confirm={t("curation.modal.sendIt")}
        onClose={close}
        onConfirm={submit}
        pending={decisions.isPending}
      >
        {risky > 0 && <p className="cur-warn">{t("curation.modal.risky", { count: risky })}</p>}
        {newDiscards.length > 0 && <p>{t("curation.modal.discarding", { count: newDiscards.length })}</p>}
        <ul className="cur-sendlist">
          {[...apply, ...newDiscards].map((row) => (
            <li key={row.n}>
              <span className="num">{row.n}</span>
              {discarding.has(row.n) ? <span className="cur-badge">✕</span> : <Badges actions={row.actions} />}
              <code>{plain(row.file)}</code>
              {note(row) && <em>“{note(row)}”</em>}
            </li>
          ))}
        </ul>
        {apply.length > 0 && <pre>{call}</pre>}
      </ConfirmModal>,
    );
  };

  const askRevert = (row: CurationRow) => {
    const call = `/whaat:memory-curation revert-applied-rows report=${reportId} rows=${row.n} confirmed=report-page`;
    setModal(
      <ConfirmModal
        kicker={kicker}
        title={t("curation.modal.revertTitle", { n: row.n })}
        confirm={t("curation.modal.sendIt")}
        onClose={close}
        pending={revert.isPending}
        onConfirm={(setError) =>
          revert.mutate(
            { body: { report_id: reportId, n: row.n } },
            {
              onSuccess: (result) => {
                refresh();
                setModal(
                  result.typed ? (
                    <Modal title={t("curation.modal.sentTitle")} onClose={close}>
                      <p>{t("curation.modal.revertSentText", { call: result.command })}</p>
                      <div className="cur-actions">
                        <button type="button" onClick={close}>
                          {t("curation.modal.close")}
                        </button>
                      </div>
                    </Modal>
                  ) : (
                    <SentModal result={result} applied={1} onClose={close} onOpen={openSession} />
                  ),
                );
              },
              onError: (error) => setError(errorText(error)),
            },
          )
        }
      >
        <p>{t("curation.modal.revertText")}</p>
        <p>
          <Inline text={row.applied ?? ""} />
        </p>
        <pre>{call}</pre>
      </ConfirmModal>,
    );
  };

  const askDone = () => {
    const unsent = rows.filter((row) => selected.has(row.n)).length;
    setModal(
      <ConfirmModal
        kicker={kicker}
        title={t("curation.modal.doneTitle")}
        confirm={t("curation.modal.doneSend")}
        onClose={close}
        pending={done.isPending}
        onConfirm={(setError) =>
          done.mutate(
            { body: { identity: identity ?? "" } },
            {
              onSuccess: (result) =>
                result.typed
                  ? setModal(<DoneModal identity={identity ?? ""} onClose={close} onOpen={openSession} />)
                  : setError(result.detail ?? "not typed"),
              onError: (error) => setError(errorText(error)),
            },
          )
        }
      >
        <p>{t("curation.modal.doneText")}</p>
        {unsent > 0 && <p className="cur-warn">{t("curation.modal.doneUnsent", { count: unsent })}</p>}
        <pre>/whaat:session-end steps=none confirmed=report-page</pre>
      </ConfirmModal>,
    );
  };

  const card = (row: CurationRow, inGroup = false) => {
    if (!visible(row)) return null;
    const applied = isApplied(row);
    const isDiscarded = discarded(row);
    const target = row.target && row.target !== "—" ? row.target : "";
    const gist = plain(target || row.reason);
    const fields: [string, string | null | undefined][] = [
      [t("curation.card.Applied"), row.applied],
      [t("curation.card.Target"), row.target],
      [t("curation.card.Reason"), row.reason],
      [t("curation.card.Evidence"), row.evidence],
    ];
    const classes = [
      "cur-prop",
      applied && "applied",
      row.sent_at && !applied && "sent",
      isDiscarded && "discarded",
      selected.has(row.n) && "picked",
      flash === row.n && "flash",
    ];
    return (
      <details
        key={row.n}
        ref={(element) => {
          cardRefs.current[row.n] = element;
        }}
        className={classes.filter(Boolean).join(" ")}
        data-action={row.actions[0]}
        open={open[row.n] ?? false}
        onToggle={(event) => {
          const isOpen = (event.target as HTMLDetailsElement).open;
          setOpen((o) => (o[row.n] === isOpen ? o : { ...o, [row.n]: isOpen }));
        }}
      >
        <summary>
          <input
            type="checkbox"
            className={inGroup ? "cur-member" : ""}
            checked={selected.has(row.n)}
            disabled={!openRow(row)}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => setSel([row.n], event.target.checked)}
          />
          <span className="num">{row.n}</span>
          <Badges actions={row.actions} />
          {row.sent_at && !applied && (
            <span className="cur-tag sent" title={t("curation.card.sentTitle", { at: row.sent_at })}>
              {t("curation.card.sent", { time: row.sent_at.slice(11, 16) })}
            </span>
          )}
          {applied && <span className="cur-tag">{t("curation.card.applied")}</span>}
          {isDiscarded && <span className="cur-tag gone">{t("curation.card.discarded")}</span>}
          <span className="cur-file" title={plain(row.file)}>
            <Inline text={row.file} />
          </span>
          <span className="cur-gist" title={gist}>
            {gist}
          </span>
          <span className="chev" />
        </summary>
        <div className="cur-body">
          <div className="cur-viz">
            <Diagram row={row} figure={figures.get(row.n)} />
          </div>
          <div className="cur-fields">
            {fields
              .filter(([, value]) => value && value !== "—")
              .map(([label, value]) => (
                <div key={label} className="cur-field">
                  <span className="label">{label}</span>
                  <div>
                    <Inline text={value ?? ""} />
                  </div>
                </div>
              ))}
            {applied ? (
              <div className="cur-field">
                <span className="label">{t("curation.card.undo")}</span>
                <div>
                  <button type="button" className="cur-revert" onClick={() => askRevert(row)}>
                    {t("curation.card.revert", { n: row.n })}
                  </button>
                </div>
              </div>
            ) : (
              <div className="cur-field">
                <span className="label">{t("curation.card.note")}</span>
                <div>
                  <textarea
                    rows={2}
                    disabled={Boolean(row.sent_at)}
                    placeholder={row.sent_at ? t("curation.card.noNoteSent") : t("curation.card.notePlaceholder")}
                    value={
                      row.sent_at ? (row.note ?? "") : (draft.notes[row.n] ?? (row.decision ? (row.note ?? "") : ""))
                    }
                    onChange={(event) => setNote(row.n, event.target.value)}
                  />
                  {!row.sent_at && (
                    <button type="button" className="cur-discard" onClick={() => toggleDiscard(row)}>
                      {isDiscarded ? t("curation.card.keep") : t("curation.card.discard")}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </details>
    );
  };

  const fixOpen = fixRows.filter(openRow).map((row) => row.n);
  const fixPicked = fixOpen.filter((n) => selected.has(n)).length;
  const shownOpen = rows.filter((row) => visible(row) && openRow(row)).map((row) => row.n);
  const sentTotal = rows.filter((row) => row.sent_at).length;
  const chipTitle = (total: number, sent: number) =>
    sent > 0 ? t("curation.bar.chipSent", { done: sent, total }) : t("curation.bar.chipTotal", { total });
  const chip = (id: string, label: string, count: number, title?: string, sent?: number) => (
    <button
      type="button"
      key={id}
      className={`cur-chip a-${id}${filter === id ? " active" : ""}`}
      title={title}
      onClick={() => setFilter(id)}
    >
      <i />
      {label}{" "}
      <b>
        {sent ? (
          <>
            <span className="done">{sent}</span>/{count}
          </>
        ) : (
          count
        )}
      </b>
    </button>
  );

  return (
    <div className="cur-page">
      {view.data?.map && <MemoryMap map={view.data.map} sentFiles={sentFiles} onPick={jump} />}
      <Panel id="lint" title="Lint">
        <Markdown text={report.lint_summary} />
      </Panel>
      <section id="proposals" className="cur-proposals">
        <div className="cur-toolbar sh-paper">
          <div className="group">
            {chip("all", t("curation.bar.all"), rows.length, chipTitle(rows.length, sentTotal), sentTotal)}
            {actionOrder.map((action) =>
              chip(
                action,
                action,
                counts.get(action) ?? 0,
                chipTitle(counts.get(action) ?? 0, sentCounts.get(action) ?? 0),
                sentCounts.get(action) ?? 0,
              ),
            )}
            {chip("open", t("curation.bar.open"), rows.filter((row) => !isApplied(row)).length)}
            {chip("applied", t("curation.bar.applied"), rows.filter(isApplied).length)}
            {sentTotal > 0 && chip("sent", t("curation.bar.sent"), sentTotal)}
            {chip("unsent", t("curation.bar.unsent"), rows.length - sentTotal)}
            {rows.some(discarded) && chip("discarded", t("curation.bar.discarded"), rows.filter(discarded).length)}
          </div>
          <div className="group">
            <input
              type="search"
              placeholder={t("curation.bar.search")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button
              type="button"
              title={t("curation.bar.expandTitle")}
              onClick={() =>
                setOpen(Object.fromEntries([...rows.filter(visible).map((row) => [row.n, true]), ["fix", true]]))
              }
            >
              {t("curation.bar.expandAll")}
            </button>
            <button type="button" title={t("curation.bar.collapseTitle")} onClick={() => setOpen({})}>
              {t("curation.bar.collapseAll")}
            </button>
            <button type="button" title={t("curation.bar.selectShownTitle")} onClick={() => setSel(shownOpen, true)}>
              {t("curation.bar.selectShown")}
            </button>
            <button type="button" onClick={() => setDraft((d) => ({ ...d, sel: [] }))}>
              {t("curation.bar.clear")}
            </button>
            <span className="cur-selcount">{t("curation.bar.selected", { count: selected.size })}</span>
            <button type="button" className="primary" onClick={send}>
              {t("curation.bar.send")}
            </button>
            {session && (
              <button type="button" title={t("curation.bar.doneTitle")} onClick={askDone}>
                {t("curation.bar.done")}
              </button>
            )}
          </div>
        </div>
        <div className="cur-props">
          {others.map((row) => card(row))}
          {grouped
            ? fixRows.some(visible) && (
                <details
                  className={`cur-group${fixOpen.length > 0 && fixPicked === fixOpen.length ? " picked" : ""}`}
                  open={open.fix ?? false}
                  onToggle={(event) => {
                    const isOpen = (event.target as HTMLDetailsElement).open;
                    setOpen((o) => (o.fix === isOpen ? o : { ...o, fix: isOpen }));
                  }}
                >
                  <summary>
                    <input
                      type="checkbox"
                      checked={fixOpen.length > 0 && fixPicked === fixOpen.length}
                      ref={(element) => {
                        if (element) element.indeterminate = fixPicked > 0 && fixPicked < fixOpen.length;
                      }}
                      disabled={fixOpen.length === 0}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => setSel(fixOpen, event.target.checked)}
                    />
                    <span className="num">{fixRows.length}</span>
                    <span className="cur-badge a-fix">fix</span>
                    <span className="cur-gist">{t("curation.card.fixGroup", { count: fixRows.length })}</span>
                    <span className="chev" />
                  </summary>
                  <div className="cur-members">{fixRows.map((row) => card(row, true))}</div>
                </details>
              )
            : fixRows.map((row) => card(row))}
        </div>
      </section>
      {report.sections?.map((section) => (
        <Panel key={section.heading} id={section.heading} title={section.heading}>
          <Markdown text={section.markdown} />
        </Panel>
      ))}
      <Panel id="unchecked" title="Not checked">
        <Markdown text={report.unchecked} />
      </Panel>
      {modal}
    </div>
  );
}

function errorText(error: unknown): string {
  const detail = (error as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : JSON.stringify(error);
}

function Inline({ text }: { text: string }) {
  return <>{inline(text)}</>;
}

function Modal({
  title,
  kicker,
  onClose,
  children,
}: {
  title: string;
  kicker?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="cur-modal" role="dialog" aria-modal="true">
      <button type="button" className="cur-backdrop" aria-label="close" onClick={onClose} />
      <div className="cur-box">
        {kicker && <div className="cur-kicker">{kicker}</div>}
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

function ConfirmModal({
  kicker,
  title,
  confirm,
  onClose,
  onConfirm,
  pending,
  children,
}: {
  kicker: string;
  title: string;
  confirm: string;
  onClose: () => void;
  onConfirm: (setError: (error: string) => void) => void;
  pending: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<string[]>([]);
  return (
    <Modal title={title} kicker={kicker} onClose={onClose}>
      {children}
      {errors.map((error, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: failures stack in the order they came
        <p key={index} className="cur-warn">
          {t("curation.modal.notSent", { error })}
        </p>
      ))}
      <div className="cur-actions">
        <button type="button" onClick={onClose}>
          {t("curation.modal.cancel")}
        </button>
        <button
          type="button"
          className="primary"
          disabled={pending}
          onClick={() => onConfirm((error) => setErrors((list) => [...list, error]))}
        >
          {pending ? t("curation.modal.sending") : errors.length ? t("curation.modal.retry") : confirm}
        </button>
      </div>
    </Modal>
  );
}

function SentModal({
  result,
  applied,
  onClose,
  onOpen,
}: {
  result: DecisionsSent;
  applied: number;
  onClose: () => void;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  if (result.typed)
    return (
      <Modal title={t("curation.modal.sentTitle")} onClose={onClose}>
        <p>{t("curation.modal.sentText", { call: result.command })}</p>
        <div className="cur-actions">
          <button type="button" onClick={onClose}>
            {t("curation.modal.close")}
          </button>
          <button type="button" onClick={onOpen}>
            {t("curation.modal.openSession")}
          </button>
        </div>
      </Modal>
    );
  if (applied === 0)
    return (
      <Modal title={t("curation.modal.savedTitle")} onClose={onClose}>
        <p>{t("curation.modal.savedText")}</p>
        <div className="cur-actions">
          <button type="button" onClick={onClose}>
            {t("curation.modal.close")}
          </button>
        </div>
      </Modal>
    );
  return (
    <Modal title={t("curation.modal.savedTitle")} onClose={onClose}>
      <p>{t("curation.modal.notTyped", { detail: result.detail ?? "" })}</p>
      <pre>{result.command}</pre>
      <div className="cur-actions">
        <button
          type="button"
          onClick={() =>
            navigator.clipboard
              .writeText(result.command)
              .then(() => setCopied(true))
              .catch(() => window.prompt("Copy:", result.command))
          }
        >
          {copied ? t("curation.modal.copied") : t("curation.modal.copy")}
        </button>
        <button type="button" onClick={onClose}>
          {t("curation.modal.close")}
        </button>
      </div>
    </Modal>
  );
}

function DoneModal({ identity, onClose, onOpen }: { identity: string; onClose: () => void; onOpen: () => void }) {
  const { t } = useTranslation();
  const state = useQuery({
    ...runStateOptions({ query: { identity } }),
    refetchInterval: (query) => (query.state.data?.state === "exited" ? false : 3000),
  });
  // a failed poll counts as exited
  const now = state.isError ? "exited" : (state.data?.state ?? "waiting");
  const line =
    now === "waiting"
      ? t("curation.modal.waiting")
      : now === "asked"
        ? t("curation.modal.asked")
        : now === "exited"
          ? t("curation.modal.exited")
          : now;
  return (
    <Modal title={now === "exited" ? t("curation.modal.ended") : t("curation.modal.finishing")} onClose={onClose}>
      <p>{line}</p>
      <div className="cur-actions">
        <button type="button" onClick={onClose}>
          {t("curation.modal.close")}
        </button>
        <button type="button" onClick={onOpen}>
          {t("curation.modal.openSession")}
        </button>
      </div>
    </Modal>
  );
}

/** A row's actions in the order they run, each in its colour. */
function Badges({ actions }: { actions: CurationRow["actions"] }) {
  return actions.map((action, i) => (
    <Fragment key={action}>
      {i > 0 && <span className="cur-then">→</span>}
      <span className={`cur-badge a-${action}`}>{action}</span>
    </Fragment>
  ));
}
