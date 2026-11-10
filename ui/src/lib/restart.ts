import { useState } from "react";
import { getHealth, restartServer, stopServer } from "@/client";

export type StopState = "idle" | "stopping" | "stopped" | "failed";

/** Stop the server and say so once it no longer answers. It starts again only from outside: the app or `whaat serve`. */
export function useStop(): { state: StopState; stop: () => Promise<void> } {
  const [state, setState] = useState<StopState>("idle");
  const stop = async () => {
    setState("stopping");
    const asked = await stopServer();
    if (asked.error) {
      setState("failed");
      return;
    }
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      try {
        await getHealth({ throwOnError: true });
      } catch {
        setState("stopped");
        return;
      }
    }
    setState("failed");
  };
  return { state, stop };
}

export type RestartState = "idle" | "restarting" | "failed";
const WAIT_MS = 30000;
const STEP_MS = 500;

/** Restart the server and reload once a new process answers (its `started` changes). The server builds the checkout's
    UI first and refuses when the build fails, with the end of its output. Terminal sessions live in tmux and keep
    running through it. */
export function useRestart(): { state: RestartState; error: string | null; restart: () => Promise<void> } {
  const [state, setState] = useState<RestartState>("idle");
  const [error, setError] = useState<string | null>(null);
  const restart = async () => {
    setState("restarting");
    setError(null);
    const before = (await getHealth()).data?.started;
    const asked = await restartServer();
    if (asked.error || before == null) {
      const detail = (asked.error as { detail?: unknown } | undefined)?.detail;
      setError(typeof detail === "string" ? detail : null);
      setState("failed");
      return;
    }
    const deadline = Date.now() + WAIT_MS;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, STEP_MS));
      try {
        const now = (await getHealth()).data?.started;
        if (now != null && now !== before) {
          window.location.reload();
          return;
        }
      } catch {
        /* the server is between processes */
      }
    }
    setState("failed");
  };
  return { state, error, restart };
}
