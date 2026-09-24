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
  const lightTheme = page.getByRole("button", { name: "Light" });
  await lightTheme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(lightTheme).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(200);
  await page.screenshot({
    path: "../docs/screenshots/theme-light.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const amoledTheme = page.getByRole("button", { name: "AMOLED" });
  await amoledTheme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "amoled");
  await expect(amoledTheme).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(200);
  await page.screenshot({
    path: "../docs/screenshots/theme-amoled.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Dark" }).click();
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
  await page.getByRole("button", { name: "PR Impact" }).click();
  await expect(
    page.getByRole("textbox", { name: "GitHub pull request URL" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Assistant", exact: true })
    .click();
  await page.getByRole("button", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator(".cy-container canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "AMOLED" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "amoled");
  await expect(page.locator(".cy-container canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "Dark" }).click();
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

test("exports a pull request impact report", async ({
  page,
  request,
  context,
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
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/repositories/*/pull-request-impact", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        pull_request: {
          number: 42,
          title: "Change authentication",
          url: "https://github.com/acme/shop/pull/42",
          state: "open",
          base: "main",
          head: "auth-change",
        },
        summary: {
          files_changed: 1,
          symbols_changed: 1,
          affected_files: 3,
          affected_endpoints: 1,
          score: 47,
          risk: "MEDIUM",
        },
        files: [
          {
            path: "services/auth.py",
            status: "modified",
            additions: 8,
            deletions: 3,
            symbols: [],
          },
        ],
        impacts: [],
        unmatched_files: [],
        graph: { nodes: [], edges: [] },
        truncated: false,
        caveat: "Potential impact is based on static dependencies.",
      }),
    });
  });

  await page.goto("/repository/" + repo.id);
  await page.getByRole("button", { name: "PR Impact" }).click();
  await page
    .getByRole("textbox", { name: "GitHub pull request URL" })
    .fill("https://github.com/acme/shop/pull/42");
  await page.getByRole("button", { name: "Analyze pull request" }).click();
  await expect(page.locator(".risk-score.compact")).toContainText("47");

  await page.getByRole("button", { name: "Copy Markdown" }).click();
  await expect(page.getByRole("status")).toHaveText("Markdown report copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "Highest risk: MEDIUM (47/100)",
  );

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("regora-pr-42-impact.md");
});
