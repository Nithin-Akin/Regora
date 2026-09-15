import { test, expect } from "@playwright/test";

test("landing page imports and mobile layout", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Understand unfamiliar codebases visually.",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Analyze Repository" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Upload ZIP" }).click();
  await expect(page.getByText("Drop your repository here")).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/landing.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Analyze Repository" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("real graph, search, source citations and impact", async ({
  page,
  request,
}) => {
  const repos = await (await request.get("/api/repositories")).json();
  const repo = repos.find(
    (r: { name: string; status: string }) =>
      r.name === "Northstar Commerce" && r.status === "READY",
  );
  test.skip(
    !repo,
    "Run the demo evaluation first to index the included repository",
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/repository/" + repo.id);
  await expect(
    page.getByRole("button", { name: "Architecture", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".cy-container canvas").first()).toBeVisible();
  await expect(page.locator(".graph-status")).toContainText("nodes");
  await page.screenshot({
    path: "../docs/screenshots/workspace.png",
    fullPage: true,
  });
  await page
    .getByRole("textbox", { name: "Search repository" })
    .fill("verify_token");
  await page
    .getByRole("combobox", { name: "Search mode" })
    .selectOption("symbol");
  await page.getByRole("button", { name: "Run search" }).click();
  await page
    .locator(".search-result")
    .filter({ hasText: "verify_token" })
    .first()
    .click();
  await expect(page.locator(".inspector h2")).toHaveText("verify_token");
  await page.getByRole("button", { name: "Open source", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator('[data-line="8"]')).toContainText(
    "def verify_token",
  );
  await page.getByRole("button", { name: "Close source" }).click();
  await page
    .getByRole("button", { name: "Analyze Impact", exact: true })
    .click();
  await expect(page.locator(".risk-score")).toBeVisible();
  await expect(page.locator(".impact-panel")).toContainText("api/routes.py");
  await page.screenshot({
    path: "../docs/screenshots/impact.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
