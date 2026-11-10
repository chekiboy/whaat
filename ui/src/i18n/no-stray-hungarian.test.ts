import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(import.meta.dirname, "..");
const SKIP = ["i18n", "client", "routeTree.gen.ts"];
const ACCENTED = /[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]/;
// A line that matches data written in Hungarian (a verdict, a phrase in the distillate) says so with this marker.
const CONTENT = "i18n-content";

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (SKIP.includes(relative(SRC, path))) return [];
    if (statSync(path).isDirectory()) return files(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

function strayLines(text: string): number[] {
  return text
    .split("\n")
    .map((line, i) => [line, i + 1] as const)
    .filter(([line]) => ACCENTED.test(line) && !line.includes(CONTENT) && !/^\s*(\/\/|\/?\*)/.test(line))
    .map(([, n]) => n);
}

describe("UI texts live in the dictionaries", () => {
  it("finds an accented text outside a comment, and lets a marked data line through", () => {
    expect(strayLines('const a = "Bezár";\n// Bezár\nconst b = /élő/; // i18n-content')).toEqual([1]);
  });

  it("has no Hungarian text outside src/i18n", () => {
    const found = files(SRC).flatMap((path) =>
      strayLines(readFileSync(path, "utf8")).map((line) => `${relative(SRC, path)}:${line}`),
    );
    expect(found).toEqual([]);
  });
});
