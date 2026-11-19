import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCanGoBack, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import type { DecisionsBody } from "@/client";
import { answerDecisionsMutation } from "@/client/@tanstack/react-query.gen";
import { Markdown } from "@/components/curation/markdown";
import { Panel } from "@/components/report-frame";
import { useTranslation } from "@/i18n";

type Row = DecisionsBody["rows"][number];
type RowAnswer = { choice?: string; note?: string };
type Tile = "q" | "du" | "df" | "all";
type Kind = Exclude<Tile, "all">;

/** The option whaat adds to every row: talk it over before anything is decided. */
const DISCUSS = "discuss";

/** A row's state: open, decided as recommended (a row with no recommendation counts here), or anything else. */
function kindOf(row: Row, answer: RowAnswer): Kind {
  const choice = answer.choice ?? row.choice;
  if (!choice) return "q";
  const recommended = row.options.find((option) => option.recommended);
  return !recommended || recommended.value === choice ? "du" : "df";
}

/** The decisions page: the summary, then one card per question. Once sent the page is read-only; the waiting session
    reads the answer itself, and the page goes back to where the user came from. */
export function DecisionsView({ body, reportId }: { body: DecisionsBody; reportId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const router = useRouter();
  const canGoBack = useCanGoBack();
  const [answers, setAnswers] = useState<Record<number, RowAnswer>>({});
  const [tile, setTile] = useState<Tile>("all");
  const send = useMutation({ ...answerDecisionsMutation() });
  const sent = Boolean(body.sent_at);
  const answerOf = (row: Row): RowAnswer => answers[row.n] ?? {};
  const set = (n: number, answer: RowAnswer) => setAnswers((all) => ({ ...all, [n]: { ...all[n], ...answer } }));

  const kinds = new Map(body.rows.map((row) => [row.n, kindOf(row, answerOf(row))]));
  const counts = { q: 0, du: 0, df: 0 };
  for (const kind of kinds.values()) counts[kind]++;
  const tiles: [Kind, string][] = [
    ["q", t("curation.bar.open")],
    ["du", t("decisions.asRecommended")],
    ["df", t("decisions.offRecommended")],
  ];
  const chosen = body.rows.filter((row) => answerOf(row).choice);
  const noteOnly = body.rows
    .filter((row) => !answerOf(row).choice && answerOf(row).note?.trim())
    .map((row) => `D-${row.n}`);

  const allRecommended = () =>
    setAnswers((all) => {
      const next = { ...all };
      for (const row of body.rows) {
        const recommended = row.options.find((option) => option.recommended);
        if (!next[row.n]?.choice && recommended) next[row.n] = { ...next[row.n], choice: recommended.value };
      }
      return next;
    });

  const submit = () =>
    send.mutate(
      {
        path: { report_id: reportId },
        body: {
          rows: chosen.map((row) => ({
            n: row.n,
            choice: answerOf(row).choice ?? "",
            note: answerOf(row).note ?? null,
          })),
        },
      },
      {
        onSuccess: () => {
          void queryClient.invalidateQueries();
          if (canGoBack) router.history.back();
        },
      },
    );

  const stateLine = sent ? t("decisions.sentLine", { at: body.sent_at ?? "" }) : t("decisions.waitingLine");
  const failure = send.error as { detail?: unknown } | null;

  return (
    <>
      <nav className="toc">
        <a href="#summary">{t("decisions.summary")}</a>
        <a href="#decisions">{t("decisions.title")}</a>
      </nav>
      <div className={`verdict sh-paper ${sent ? "v-green" : "v-amber"}`}>
        <div className="vhead">
          <span className="vlabel">{t("decisions.stateLabel")}</span>
          <span className="vtext">{sent ? t("decisions.sent") : t("decisions.waiting")}</span>
          <span className="vsub">{stateLine}</span>
        </div>
        {failure && (
          <p>
            {t("decisions.sendFailed", {
              error: typeof failure.detail === "string" ? failure.detail : t("decisions.sendFailedUnknown"),
            })}
          </p>
        )}
      </div>
      <div className="dash">
        <div className="tiles">
          {tiles.map(([kind, label]) => (
            <button
              key={kind}
              type="button"
              className={`tile k-${kind}${tile === kind ? " active" : ""}`}
              onClick={() => setTile(tile === kind ? "all" : kind)}
            >
              <b>{counts[kind]}</b> {label}
            </button>
          ))}
          <button type="button" className={`tile all${tile === "all" ? " active" : ""}`} onClick={() => setTile("all")}>
            <b>{body.rows.length}</b> {t("reports.all")}
          </button>
        </div>
        {!sent && (
          <div className="tools">
            <button type="button" onClick={allRecommended}>
              ✔ {t("decisions.allRecommended")}
            </button>
            <button
              type="button"
              disabled={chosen.length === 0 || noteOnly.length > 0 || send.isPending}
              onClick={submit}
            >
              → {t("curation.bar.send")}
            </button>
          </div>
        )}
        {!sent && noteOnly.length > 0 && <p>{t("decisions.noteWithoutChoice", { rows: noteOnly.join(", ") })}</p>}
      </div>
      <Panel id="summary" title={t("decisions.summary")} collapsible open>
        <Markdown text={body.summary} />
      </Panel>
      <Panel id="decisions" title={t("decisions.title")}>
        <div className="cards">
          {body.rows
            .filter((row) => tile === "all" || kinds.get(row.n) === tile)
            .map((row) => (
              <DecisionCard
                key={row.n}
                row={row}
                answer={answerOf(row)}
                kind={kinds.get(row.n) ?? "q"}
                readOnly={sent}
                onAnswer={(answer) => set(row.n, answer)}
              />
            ))}
        </div>
      </Panel>
    </>
  );
}

function DecisionCard({
  row,
  answer,
  kind,
  readOnly,
  onAnswer,
}: {
  row: Row;
  answer: RowAnswer;
  kind: Kind;
  readOnly: boolean;
  onAnswer: (answer: RowAnswer) => void;
}) {
  const { t } = useTranslation();
  const choice = answer.choice ?? row.choice;
  // open only at first: picking an option must not hide the note field
  const [openAtFirst] = useState(!choice);
  const options = [...row.options, { value: DISCUSS, label: t("decisions.discuss"), recommended: false, why: null }];
  const chosen = options.find((option) => option.value === choice);
  return (
    <details className={`card k-${kind}`} open={openAtFirst}>
      <summary>
        <span className="sev">D-{row.n}</span>
        <span className="ctitle">{row.title}</span>
        <span className="tagline">{chosen ? chosen.label : t("decisions.noDecision")}</span>
        <span className="chev" />
      </summary>
      <div className="cbody">
        <Markdown text={row.explain} />
        <h4>{t("decisions.options")}</h4>
        <ul className="options">
          {options.map((option) => (
            <li key={option.value} className={choice && option.value !== choice ? "lost" : ""}>
              <button
                type="button"
                className="dc-option"
                disabled={readOnly}
                onClick={() => onAnswer({ choice: option.value })}
              >
                <span>{option.value === choice ? "✔" : "·"}</span>
                <span>
                  {option.label}
                  {option.recommended && (
                    <em>
                      {" "}
                      — {t("decisions.recommended")}
                      {option.why ? ` · ${option.why}` : ""}
                    </em>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <h4>{t("curation.card.note")}</h4>
        <textarea
          className="sh-search dc-note"
          rows={2}
          placeholder={t("decisions.optional")}
          disabled={readOnly}
          value={answer.note ?? row.note ?? ""}
          onChange={(event) => onAnswer({ note: event.target.value })}
        />
      </div>
    </details>
  );
}
