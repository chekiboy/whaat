/** The About page's structure: the order of its parts and how each looks. Their words are in the dictionaries
    (src/i18n, the "about" keys). */

export const SPOTLIGHT = ["identity", "curator", "decisions"] as const;

export const TODAY = [
  ["reports", "var(--stripe-blue)"],
  ["journal", "var(--stripe-violet)"],
  ["kept", "var(--stripe-teal)"],
  ["private", "var(--stripe-red)"],
  ["local", "var(--stripe-orange)"],
  ["plugs", "var(--stripe-yellow)"],
] as const;

export type StageStatus = "done" | "now" | "next" | "later";

export const ROADMAP: readonly (readonly [
  "foundation" | "structured" | "oneScreen" | "decide" | "colleagues" | "memory",
  StageStatus,
])[] = [
  ["foundation", "done"],
  ["structured", "now"],
  ["oneScreen", "now"],
  ["decide", "later"],
  ["colleagues", "later"],
  ["memory", "now"],
];
