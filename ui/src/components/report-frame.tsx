import type { ReactNode } from "react";
import type { Envelope } from "@/client";
import { type Crumb, usePageHeading } from "@/lib/breadcrumb";
import "@/styles/report.css";

export function ReportFrame({
  crumbs,
  title,
  source,
  children,
}: {
  crumbs: Crumb[];
  title: string;
  source?: string;
  children: ReactNode;
}) {
  usePageHeading(title, crumbs, source);
  return <div className="rp">{children}</div>;
}

export function Pins({
  envelope,
  path,
  extra = [],
}: {
  envelope: Envelope;
  path: string;
  extra?: [string, string | null | undefined][];
}) {
  const rows: [string, string | null | undefined][] = [
    ["Date", envelope.created_date],
    ["Identity", envelope.identity],
    ["Session", envelope.session],
    ["Repo", envelope.repo],
    ...extra,
    ["Tags", envelope.tags?.join(", ")],
    ["Path", path],
  ];
  return (
    <div className="pins">
      {rows
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <div key={label} className="pin">
            <span>{label}</span>
            <div>{value}</div>
          </div>
        ))}
    </div>
  );
}

export function Panel({
  id,
  title,
  children,
  collapsible = false,
  open = true,
}: {
  id: string;
  title: string;
  children: ReactNode;
  collapsible?: boolean;
  open?: boolean;
}) {
  if (!collapsible) {
    return (
      <section id={id} className="panel sh-paper">
        <h2>{title}</h2>
        {children}
      </section>
    );
  }
  return (
    <details id={id} className="panel sh-paper" open={open}>
      <summary>
        <h2>{title}</h2>
        <span className="chev" />
      </summary>
      <div className="pbody">{children}</div>
    </details>
  );
}

export function Lines({ items, none }: { items: string[] | null | undefined; none: string }) {
  if (items == null) return <p className="muted">Not recorded.</p>;
  if (items.length === 0) return <p className="muted">{none}</p>;
  return (
    <ul>
      {items.map((item, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: lines are plain text that can repeat
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

export function Text({ value }: { value: string | null | undefined }) {
  return value == null ? <p className="muted">Not recorded.</p> : <p>{value}</p>;
}
