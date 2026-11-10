import type { JournalBlock } from "@/client";
import { Lines, Panel, Text } from "@/components/report-frame";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <span>{label}</span>
      <div>{children}</div>
    </div>
  );
}

function Entry({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div id={id} className="jentry">
      {children}
    </div>
  );
}

function Reflection({ block }: { block: JournalBlock }) {
  return (
    <>
      <Field label="About">
        <Text value={block.about} />
      </Field>
      <Field label="Mistakes">
        <Lines items={block.mistakes} none="None noticed." />
      </Field>
      <Field label="Corrections">
        <Lines items={block.corrections} none="None." />
      </Field>
      <Field label="Learned">
        <Text value={block.learned} />
      </Field>
      <Field label="Feelings">
        {block.feelings == null ? (
          <p className="muted">Not recorded.</p>
        ) : block.feelings.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <ul>
            {block.feelings.map((item) => (
              <li key={`${item.part}:${item.feeling}`}>
                <strong>{item.part}:</strong> {item.feeling}
              </li>
            ))}
          </ul>
        )}
      </Field>
      <h4>Own words</h4>
      {block.own_words == null ? (
        <p className="muted">Not recorded.</p>
      ) : block.own_words.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        block.own_words.map((moment, momentIndex) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: quotes can repeat
          <div key={momentIndex} className="moment">
            {moment.answering && (
              <Field label="Asked">
                <p className="context">„{moment.answering}”</p>
              </Field>
            )}
            <Field label={`I said${moment.answering ? "" : ", unprompted"}${moment.at ? ` · ${moment.at}` : ""}`}>
              <p className="said">„{moment.quote}”</p>
            </Field>
            {moment.reaction && (
              <Field label="Reaction">
                <p className="context">„{moment.reaction}”</p>
              </Field>
            )}
            {moment.how_taken && (
              <Field label="How I took it">
                <p className="taken">{moment.how_taken}</p>
              </Field>
            )}
          </div>
        ))
      )}
    </>
  );
}

/** The narrative and the structured reflection in boxes of their own. */
export function JournalBlocks({
  blocks,
  idPrefix = "block",
  collapsible = false,
  open = true,
}: {
  blocks: JournalBlock[];
  idPrefix?: string;
  collapsible?: boolean;
  open?: boolean;
}) {
  const narrated = blocks.map((block, index) => ({ block, index })).filter(({ block }) => block.narrative);
  return (
    <>
      {narrated.length > 0 && (
        <Panel id={`${idPrefix}-narrative`} title="Narrative" collapsible={collapsible} open={open}>
          {narrated.map(({ block, index }) => (
            <Entry key={index} id={`${idPrefix}-${index + 1}-narrative`}>
              <p className="narrative">{block.narrative}</p>
            </Entry>
          ))}
        </Panel>
      )}
      <Panel id={`${idPrefix}-reflection`} title="Reflection" collapsible={collapsible} open={open}>
        {blocks.map((block, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: blocks are append-only, so the position is their identity
          <Entry key={index} id={`${idPrefix}-${index + 1}`}>
            <Reflection block={block} />
          </Entry>
        ))}
      </Panel>
    </>
  );
}
