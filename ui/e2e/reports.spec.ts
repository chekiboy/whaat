import { expect, test } from "@playwright/test";

test("the list shows reports, filters by kind and opens one", async ({ page }) => {
  await page.goto("/reports");
  const cards = page.getByRole("list", { name: "Reports" }).getByRole("link");
  await expect(cards.first()).toBeVisible();
  const total = await cards.count();
  expect(total).toBeGreaterThan(0);

  const allTile = page.getByRole("navigation", { name: "Filter by kind" }).getByRole("link").first();
  await expect(allTile).toContainText(String(total));

  await page
    .getByRole("navigation", { name: "Filter by kind" })
    .getByRole("link", { name: /Review/ })
    .click();
  await expect(page).toHaveURL(/kind=review/);
  const reviews = await cards.count();
  expect(reviews).toBeGreaterThan(0);
  expect(reviews).toBeLessThan(total);

  const title = (await cards.first().getByRole("heading").textContent()) ?? "";
  await cards.first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
  await expect(page).toHaveURL(/\/reports\/[0-9a-f]{16}$/);
  await expect(page.getByText("Could not load")).toHaveCount(0);
});

test("the API refuses a request without the token", async ({ request }) => {
  const response = await request.get("/api/v1/reports");
  expect(response.status()).toBe(401);
});
