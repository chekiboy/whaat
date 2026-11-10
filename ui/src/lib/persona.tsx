import { useRouterState } from "@tanstack/react-router";
import { createContext, type ReactNode, useCallback, useContext, useState } from "react";
import type { IdentitySummary, Preferences } from "@/client";
import { useIdentitySummaries } from "@/lib/identities";
import { usePreferences } from "@/lib/preferences";

export type PersonaStatus = "loading" | "empty" | "ready";

type PersonaState = { chosen: string | null; choose: (identity: string) => void };

const PersonaContext = createContext<PersonaState>({ chosen: null, choose: () => {} });

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const { update } = usePreferences();
  const choose = useCallback(
    (identity: string) => {
      setChosen(identity);
      void update({ identity: { last: identity } });
    },
    [update],
  );
  return <PersonaContext value={{ chosen, choose }}>{children}</PersonaContext>;
}

/** The identity the app opens with: the fixed one of the settings, or the
    one chosen last; the server's default when that is gone or not set; else the first. */
export function startIdentity(preferences: Preferences, identities: IdentitySummary[]): string | null {
  const ids = identities.map((who) => who.id);
  const { open_with = "last", last = null } = preferences.identity ?? {};
  const wanted = open_with === "last" ? last : open_with;
  if (wanted && ids.includes(wanted)) return wanted;
  return identities.find((who) => who.default)?.id ?? ids[0] ?? null;
}

/** The persona the app works with: the URL's `identity` wins, so a link opens what it names; then the one chosen in
    this window; then the one it opens with. */
export function usePersona(): { persona: string | null; status: PersonaStatus; choose: (identity: string) => void } {
  const { chosen, choose } = useContext(PersonaContext);
  const { preferences } = usePreferences();
  const identities = useIdentitySummaries();
  const fromUrl = useRouterState({
    select: (state) => {
      const identity = (state.location.search as Record<string, unknown>).identity;
      return typeof identity === "string" ? identity : null;
    },
  });
  if (!preferences || !identities) return { persona: fromUrl, status: fromUrl ? "ready" : "loading", choose };
  if (identities.length === 0) return { persona: null, status: "empty", choose };
  const persona = fromUrl ?? chosen ?? startIdentity(preferences, identities);
  return { persona, status: persona ? "ready" : "empty", choose };
}
