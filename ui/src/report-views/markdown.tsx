import type { ReportBody } from "@/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function MarkdownView({ body }: { body: ReportBody }) {
  return (
    <>
      {body.pins.length > 0 && (
        <ul className="mb-6 list-disc pl-5 text-sm text-foreground/90">
          {body.pins.map((pin) => (
            <li key={pin}>{pin}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-5">
        {withKeys(body.sections).map(({ key, section }) => (
          <Card key={key} className="sh-paper rounded-sm border-0 shadow-hard">
            <CardHeader>
              <CardTitle className="font-heading text-2xl uppercase tracking-wide">{section.heading}</CardTitle>
            </CardHeader>
            <CardContent className="whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]">
              {section.markdown}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

function withKeys<T extends { heading: string }>(sections: T[]): { key: string; section: T }[] {
  const seen = new Map<string, number>();
  return sections.map((section) => {
    const count = (seen.get(section.heading) ?? 0) + 1;
    seen.set(section.heading, count);
    return { key: `${section.heading}#${count}`, section };
  });
}
