import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { IdentitySummary } from "@/client";
import { browseMemoriesOptions, listIdentitiesOptions } from "@/client/@tanstack/react-query.gen";

/** Memories per identity, from the memory browse, for the switcher's and the settings' counts. */
export function useMemoryCounts(): Record<string, number> {
  const { data } = useQuery(browseMemoriesOptions());
  return useMemo(
    () =>
      Object.fromEntries(
        (data ?? []).map((who) => [who.identity, who.layers.reduce((n, layer) => n + layer.memories.length, 0)]),
      ),
    [data],
  );
}

/** The identities the server knows; undefined while they load. */
export function useIdentitySummaries(): IdentitySummary[] | undefined {
  return useQuery(listIdentitiesOptions()).data;
}

/** Letters, digits and dashes from a letter; capitals allowed (wHaat), and the server refuses an id that differs from a
    known one only in case. */
export const IDENTITY_ID = /^[A-Za-z][A-Za-z0-9-]{0,31}$/;
