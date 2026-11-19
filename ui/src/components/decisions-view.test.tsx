import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DecisionsBody } from "@/client";
import { client } from "@/client/client.gen";
import { DecisionsView } from "./decisions-view";

const body: DecisionsBody = {
  title: "ABC-101 · phase 3 gate",
  summary: "What to know first.",
  rows: [1, 2].map((n) => ({
    n,
    title: `Question ${n}`,
    explain: "Why it matters.",
    options: [
      { value: "apply", label: "Apply it", recommended: true },
      { value: "skip", label: "Skip it" },
    ],
  })),
};

async function renderView() {
  client.setConfig({ baseUrl: "http://localhost" });
  const rootRoute = createRootRoute({ component: () => <DecisionsView body={body} reportId="r:decisions/x.json" /> });
  const router = createRouter({ routeTree: rootRoute, history: createMemoryHistory() });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return screen.findByRole("button", { name: /Send/ });
}

const option = (label: RegExp, row: number) => screen.getAllByRole("button", { name: label })[row] as HTMLElement;
const note = (row: number, value: string) =>
  fireEvent.change(screen.getAllByRole("textbox")[row] as HTMLElement, { target: { value } });

afterEach(() => vi.restoreAllMocks());

describe("DecisionsView", () => {
  it("keeps Send disabled while a row has a note but no option, and says which row", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    const send = await renderView();

    fireEvent.click(option(/Apply it/, 0));
    note(1, "neither: rename it instead");

    expect(send).toBeDisabled();
    expect(screen.getByText(/D-2/, { selector: "p" })).toBeInTheDocument();
    fireEvent.click(send);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not block on a blank note, and sends the note once its row has an option", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    const send = await renderView();

    fireEvent.click(option(/Apply it/, 0));
    note(1, "  ");
    expect(send).toBeEnabled();

    note(1, "rename it instead");
    fireEvent.click(option(/Skip it/, 1));
    fireEvent.click(send);

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(JSON.parse(await request.text()).rows).toEqual([
      { n: 1, choice: "apply", note: null },
      { n: 2, choice: "skip", note: "rename it instead" },
    ]);
  });

  it("offers Let's discuss it on every row and sends it with its note", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    const send = await renderView();

    expect(screen.getAllByRole("button", { name: /Let's discuss it/ })).toHaveLength(2);
    fireEvent.click(option(/Let's discuss it/, 1));
    note(1, "why not both?");
    fireEvent.click(send);

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(JSON.parse(await request.text()).rows).toEqual([{ n: 2, choice: "discuss", note: "why not both?" }]);
  });

  it("clears a pick when its option is clicked again", async () => {
    const send = await renderView();

    fireEvent.click(option(/Apply it/, 0));
    expect(send).toBeEnabled();
    fireEvent.click(option(/Apply it/, 0));
    expect(send).toBeDisabled();
  });

  it("shows a sent page read-only, with no Send", async () => {
    client.setConfig({ baseUrl: "http://localhost" });
    const sent = { ...body, sent_at: "2026-11-19 11:42", rows: body.rows.map((row) => ({ ...row, choice: "apply" })) };
    const rootRoute = createRootRoute({ component: () => <DecisionsView body={sent} reportId="r:decisions/x.json" /> });
    const router = createRouter({ routeTree: rootRoute, history: createMemoryHistory() });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await screen.findAllByRole("button", { name: /Apply it/ });
    expect(screen.queryByRole("button", { name: /Send/ })).toBeNull();
    for (const button of screen.getAllByRole("button", { name: /Apply it|Skip it|discuss/ }))
      expect(button).toBeDisabled();
  });

  it("goes back to where the user came from after Send", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    client.setConfig({ baseUrl: "http://localhost" });
    const rootRoute = createRootRoute({ component: () => <DecisionsView body={body} reportId="r:decisions/x.json" /> });
    const history = createMemoryHistory({ initialEntries: ["/sessions", "/page"], initialIndex: 1 });
    const router = createRouter({ routeTree: rootRoute, history });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await screen.findAllByRole("button", { name: /Apply it/ });
    fireEvent.click(option(/Apply it/, 0));
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/sessions"));
  });
});
