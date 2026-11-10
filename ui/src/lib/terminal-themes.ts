import { useQuery } from "@tanstack/react-query";
import type { ITheme } from "@xterm/xterm";
import type { TerminalTheme } from "@/client";
import { listThemesOptions } from "@/client/@tanstack/react-query.gen";

export type BuiltInTheme = "whaat" | "solarized-dark" | "dracula" | "light";

/** The terminal's colour themes, picked in the settings; "whaat" is the app's own dark one. */
export const TERMINAL_THEMES: Record<BuiltInTheme, ITheme> = {
  whaat: {
    background: "#0d0b09",
    foreground: "#e8dfc9",
    cursor: "#f2c230",
    selectionBackground: "#5a4a2a",
    black: "#1b1814",
    red: "#e0442b",
    green: "#3aa58c",
    yellow: "#f2c230",
    blue: "#2e78c2",
    magenta: "#9b72d0",
    cyan: "#5a9e8c",
    white: "#d9cfba",
    brightBlack: "#6b6252",
    brightRed: "#ff6a4d",
    brightGreen: "#5cc7aa",
    brightYellow: "#ffd95a",
    brightBlue: "#5a9ee8",
    brightMagenta: "#b996ea",
    brightCyan: "#7cc4b0",
    brightWhite: "#f3ead6",
  },
  "solarized-dark": {
    background: "#002b36",
    foreground: "#839496",
    cursor: "#93a1a1",
    selectionBackground: "#073642",
    black: "#073642",
    red: "#dc322f",
    green: "#859900",
    yellow: "#b58900",
    blue: "#268bd2",
    magenta: "#d33682",
    cyan: "#2aa198",
    white: "#eee8d5",
    brightBlack: "#586e75",
    brightRed: "#cb4b16",
    brightGreen: "#586e75",
    brightYellow: "#657b83",
    brightBlue: "#839496",
    brightMagenta: "#6c71c4",
    brightCyan: "#93a1a1",
    brightWhite: "#fdf6e3",
  },
  dracula: {
    background: "#282a36",
    foreground: "#f8f8f2",
    cursor: "#f8f8f2",
    selectionBackground: "#44475a",
    black: "#21222c",
    red: "#ff5555",
    green: "#50fa7b",
    yellow: "#f1fa8c",
    blue: "#bd93f9",
    magenta: "#ff79c6",
    cyan: "#8be9fd",
    white: "#f8f8f2",
    brightBlack: "#6272a4",
    brightRed: "#ff6e6e",
    brightGreen: "#69ff94",
    brightYellow: "#ffffa5",
    brightBlue: "#d6acff",
    brightMagenta: "#ff92df",
    brightCyan: "#a4ffff",
    brightWhite: "#ffffff",
  },
  light: {
    background: "#f6f1e4",
    foreground: "#2b2720",
    cursor: "#c2410c",
    selectionBackground: "#e6d9b8",
    black: "#2b2720",
    red: "#c0392b",
    green: "#2f7d5f",
    yellow: "#a46d00",
    blue: "#1f5f9e",
    magenta: "#7c4fb0",
    cyan: "#2c7a74",
    white: "#d9cfba",
    brightBlack: "#6b6252",
    brightRed: "#e0442b",
    brightGreen: "#3aa58c",
    brightYellow: "#c98a06",
    brightBlue: "#2e78c2",
    brightMagenta: "#9b72d0",
    brightCyan: "#3a9c95",
    brightWhite: "#1b1814",
  },
};

export const THEME_NAMES = Object.keys(TERMINAL_THEMES) as BuiltInTheme[];

/** The themes this machine's terminal apps have (Terminal, iTerm2), read by the server. */
export function useMachineThemes(): TerminalTheme[] {
  return useQuery({ ...listThemesOptions(), staleTime: 60_000 }).data?.themes ?? [];
}

/** How the embedded terminal looks and behaves under a saved profile: the app's colours, font, cursor and Option key;
    whaat's own when the profile is gone. */
export type Profile = {
  theme: ITheme;
  fontFamily: string;
  fontSize: number;
  cursorStyle: "block" | "underline" | "bar";
  cursorBlink: boolean;
  macOptionIsMeta: boolean;
};

export function profileOf(name: string | undefined, machine: TerminalTheme[] = []): Profile {
  const found = machine.find((theme) => theme.id === name);
  const style = found?.cursor.style;
  return {
    theme: themeOf(name, machine),
    fontFamily: `${found?.font.family ?? "IBM Plex Mono"}, ui-monospace, Menlo, monospace`,
    fontSize: found?.font.size ?? 13,
    cursorStyle: style === "underline" || style === "bar" ? style : "block",
    cursorBlink: found?.cursor.blink ?? true,
    macOptionIsMeta: found?.optionIsMeta ?? false,
  };
}

/** A theme by its saved name: a built-in one, one read from this machine, or whaat's when it is gone. */
export function themeOf(name: string | undefined, machine: TerminalTheme[] = []): ITheme {
  if (name && name in TERMINAL_THEMES) return TERMINAL_THEMES[name as BuiltInTheme];
  const found = machine.find((theme) => theme.id === name);
  return found ? (found.colors as ITheme) : TERMINAL_THEMES.whaat;
}
