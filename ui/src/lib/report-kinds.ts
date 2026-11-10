import { useTranslation } from "@/i18n";

export type KindInfo = {
  label: string;
  description: string;
  stripe: string;
};

const KINDS: Record<string, string> = {
  review: "bg-stripe-red",
  development: "bg-stripe-orange",
  investigation: "bg-stripe-yellow",
  "memory-curation": "bg-stripe-teal",
  "session-report": "bg-stripe-blue",
  journal: "bg-stripe-violet",
};
const KNOWN = ["review", "development", "investigation", "memory-curation", "session-report", "journal"] as const;

/** A report kind's colour, and its name and description in the chosen language; a kind we do not know shows as it is. */
export function useKindInfo(): (kind: string) => KindInfo {
  const { t } = useTranslation();
  return (kind) =>
    (KNOWN as readonly string[]).includes(kind)
      ? {
          label: t(`reports.kinds.${kind as (typeof KNOWN)[number]}.label`),
          description: t(`reports.kinds.${kind as (typeof KNOWN)[number]}.description`),
          stripe: KINDS[kind] ?? "bg-muted-foreground",
        }
      : { label: kind, description: "", stripe: "bg-muted-foreground" };
}

export const KIND_ORDER = Object.keys(KINDS);
