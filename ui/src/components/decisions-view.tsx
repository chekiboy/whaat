import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCanGoBack, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import type { DecisionsBody } from "@/client";
import { answerDecisionsMutation } from "@/client/@tanstack/react-query.gen";
import { Markdown } from "@/components/curation/markdown";
import { Panel } from "@/components/report-frame";
import { useTranslation } from "@/i18n";

type Row = DecisionsBody["rows"][number];
type Pick = { choice?: string; note?: string };
type Tile = "q" | "du" | "df" | "all";

/** A row's state: open, decided as recommended, or decided against the recommendation (a row with none is "as"). */
function kindOf(row: Row, pick: Pick): Exclude<Tile, "all"> {
  const choice = pick.choice ?? row.choice;
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
  const [picks, setPicks] = useState<Record<number, Pick>>({});
  const [tile, setTile] = useState<Tile>("all");
  const send = useMutation({ ...answerDecisionsMutation() });
  const sent = Boolean(body.sent_at);
  const pickOf = (row: Row): Pick => picks[row.n] ?? {};
  const set = (n: number, pick: Pick) => setPicks((all) => ({ ...all, [n]: { ...all[n], ...pick } }));

  const counts = { q: 0, du: 0, df: 0 };
  for (const row of body.rows) counts[kindOf(row, pickOf(row))]++;
  const tiles: [Exclude<Tile, "all">, string][] = [
    ["q", t("curation.bar.open")],
    ["du", t("decisions.asRecommended")],
    ["df", t("decisions.offRecommended")],
  ];
  const chosen = body.rows.filter((row) => pickOf(row).choice);

  const allRecommended = () =>
    setPicks((all) => {
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
          rows: chosen.map((row) => ({ n: row.n, choice: pickOf(row).choice ?? "", note: pickOf(row).note ?? null })),
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

  return (
    <>
      <nav className="toc">
        <a href="#summary">{t("decisions.summary")}</a>
        <a href="#decisions">{t("decisions.title")}</a>
      </nav>
      <div className={`verdict sh-paper ${sent ? "v-green" : "v-amber"}`}>
        <div className="vhead">
          <span className="vlabel">{t("decisions.state")}</span>
          <span className="vtext">{sent ? t("decisions.sent") : t("decisions.waiting")}</span>
          <span className="vsub">{stateLine}</span>
        </div>
        {body.asked_by && <p className="muted">{body.asked_by}</p>}
        {send.error && <p>{t("decisions.sendFailed", { error: JSON.stringify(send.error) })}</p>}
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
            <button type="button" disabled={chosen.length === 0 || send.isPending} onClick={submit}>
              → {t("curation.bar.send")}
            </button>
          </div>
        )}
      </div>
      <Panel id="summary" title={t("decisions.summary")} collapsible open>
        <Markdown text={body.summary} />
      </Panel>
      <Panel id="decisions" title={t("decisions.title")}>
        <div className="cards">
          {body.rows
            .filter((row) => tile === "all" || kindOf(row, pickOf(row)) === tile)
            .map((row) => (
              <DecisionCard
                key={row.n}
                row={row}
                pick={pickOf(row)}
                kind={kindOf(row, pickOf(row))}
                readOnly={sent}
                onPick={(pick) => set(row.n, pick)}
              />
            ))}
        </div>
      </Panel>
    </>
  );
}

function DecisionCard({
  row,
  pick,
  kind,
  readOnly,
  onPick,
}: {
  row: Row;
  pick: Pick;
  kind: Exclude<Tile, "all">;
  readOnly: boolean;
  onPick: (pick: Pick) => void;
}) {
  const { t } = useTranslation();
  const choice = pick.choice ?? row.choice;
  const chosen = row.options.find((option) => option.value === choice);
  return (
    <details className={`card k-${kind}`} open={!choice}>
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
          {row.options.map((option) => (
            <li key={option.value} className={choice && option.value !== choice ? "lost" : ""}>
              <button
                type="button"
                className="dc-option"
                disabled={readOnly}
                onClick={() => onPick({ choice: option.value })}
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
          value={pick.note ?? row.note ?? ""}
          onChange={(event) => onPick({ note: event.target.value })}
        />
      </div>
    </details>
  );
}
