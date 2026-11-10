import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { startCurationMutation } from "@/client/@tanstack/react-query.gen";
import { usePersona } from "@/lib/persona";

/** Start memory-curation's report for the chosen persona and open its terminal session; a running one is opened instead of a second. */
export function useStartCuration(): { start: () => void; pending: boolean; error: string | null; can: boolean } {
  const { persona } = usePersona();
  const navigate = useNavigate();
  const mutation = useMutation({
    ...startCurationMutation(),
    onSuccess: (started) => navigate({ to: "/terminal", search: { s: started.session.name } }),
  });
  const detail = (mutation.error as { detail?: unknown } | null)?.detail;
  return {
    start: () => {
      if (persona) mutation.mutate({ body: { identity: persona } });
    },
    pending: mutation.isPending,
    error: mutation.error ? (typeof detail === "string" ? detail : JSON.stringify(mutation.error)) : null,
    can: persona !== null,
  };
}
