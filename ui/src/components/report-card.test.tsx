import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReportSummary } from "@/client";
import { ReportCard } from "./report-card";

const report: ReportSummary = {
  id: "private-claude:session-reports/2026-10-28_session-report_4c2f638a_abc-102.md",
  key: "3f9a0c1d2e4b5a69",
  root: "private-claude",
  path: "session-reports/2026-10-28_session-report_4c2f638a_abc-102.md",
  envelope: {
    v: 1,
    kind: "session-report",
    title: "Session — ABC-102 end to end",
    created_date: "2026-10-28",
    session: "4c2f638a",
    repo: "acme/tools",
    ticket: "ABC-102",
    writer: "self-model-journal",
    identity: "claude",
  },
  envelope_source: "derived",
  private: true,
  state: "done",
  warnings: [],
};

async function renderCard(summary: ReportSummary) {
  const rootRoute = createRootRoute({ component: () => <ReportCard report={summary} /> });
  const router = createRouter({ routeTree: rootRoute, history: createMemoryHistory() });
  render(<RouterProvider router={router} />);
  return screen.findByRole("link");
}

describe("ReportCard", () => {
  it("shows the title, the meta line and the private badge, and links to the report", async () => {
    const link = await renderCard(report);

    expect(screen.getByRole("heading", { name: "Session — ABC-102 end to end" })).toBeInTheDocument();
    expect(screen.getByText("2026-10-28 · claude · acme/tools · ABC-102")).toBeInTheDocument();
    expect(screen.getByText("private")).toBeInTheDocument();
    expect(screen.getByText("Session report")).toHaveAttribute(
      "title",
      "What one working session did, decided and learned.",
    );
    expect(link).toHaveAttribute("href", "/reports/3f9a0c1d2e4b5a69");
  });

  it("leaves out the private badge for a shareable report", async () => {
    await renderCard({ ...report, private: false });

    expect(screen.queryByText("private")).not.toBeInTheDocument();
  });
});
