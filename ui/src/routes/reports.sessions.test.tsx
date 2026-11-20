import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { client } from "@/client/client.gen";
import { ReportsModuleBar } from "@/components/reports-module-bar";
import { SessionDecisionPages } from "@/components/session-report-view";
import { ModuleBarProvider, ModuleBarSlot } from "@/components/shell/module-bar";
import { listing, summary } from "@/lib/reports-fixture.test-util";
import { Route } from "./reports.sessions";

const sessions = Array.from({ length: 25 }, (_, i) =>
  summary(`${String(i).padStart(8, "0")}`, "journal", `2026-11-${String(10 + (i % 9)).padStart(2, "0")}T09:00:00Z`),
);
const waiting = summary("00000003", "decisions", "2026-11-13T10:00:00Z", "waiting");

function renderIn(component: () => React.ReactNode) {
  client.setConfig({ baseUrl: "http://localhost" });
  const router = createRouter({ routeTree: createRootRoute({ component }), history: createMemoryHistory() });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ModuleBarProvider>
        <ModuleBarSlot />
        <RouterProvider router={router} />
      </ModuleBarProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Sessions page", () => {
  it("pages twenty sessions at a time and filters the waiting ones", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(listing([...sessions, waiting]));
    const Page = Route.options.component as () => React.ReactNode;
    renderIn(() => <Page />);

    expect(await screen.findByText("1–20 / 25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "›" }));
    expect(screen.getByText("21–25 / 25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^waiting/ }));
    expect(screen.getByText("1–1 / 1")).toBeInTheDocument();
  });

  it("lists the open report's session in the module bar", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(listing([...sessions, waiting]));
    renderIn(() => <ReportsModuleBar session="00000003" />);

    expect(await screen.findByText("This session")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /decisions 00000003/ })).toBeInTheDocument();
  });

  it("links a session report to the session's decisions pages", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(listing([waiting]));
    renderIn(() => <SessionDecisionPages session="00000003" />);

    expect(await screen.findByRole("link", { name: "decisions 00000003" })).toBeInTheDocument();
    expect(screen.getByText(/waiting/)).toBeInTheDocument();
  });
});
