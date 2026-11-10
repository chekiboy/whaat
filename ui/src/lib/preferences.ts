import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import type { PreferencesPatch } from "@/client";
import {
  getPreferencesOptions,
  getPreferencesQueryKey,
  updatePreferencesMutation,
} from "@/client/@tanstack/react-query.gen";

/** The preferences the server keeps for this instance (language, the identity it opens with, terminal command, theme,
    saved folders). */
export function usePreferences() {
  const queryClient = useQueryClient();
  const query = useQuery({ ...getPreferencesOptions(), staleTime: 30_000 });
  const mutation = useMutation({
    ...updatePreferencesMutation(),
    onSuccess: (data) => queryClient.setQueryData(getPreferencesQueryKey(), data),
  });
  const { mutateAsync } = mutation;
  const update = useCallback((patch: PreferencesPatch) => mutateAsync({ body: patch }), [mutateAsync]);
  return { preferences: query.data, update, saving: mutation.isPending };
}
