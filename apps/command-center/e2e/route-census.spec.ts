import { test, expect } from "@playwright/test";

/** Keep in sync with APP_ROUTES in src/App.tsx */
const ROUTES = [
  "/",
  "/work/start",
  "/compare",
  "/extra",
  "/confenge/suppliers",
  "/confenge/agencies",
  "/documents",
  "/ops",
  "/dod",
  "/actions",
  "/jobs",
  "/review",
  "/results",
  "/search",
  "/onboarding",
];

test.describe("route census", () => {
  for (const route of ROUTES) {
    test(`route ${route} renders main content`, async ({ page }) => {
      const pageErrors: string[] = [];
      const consoleErrors: string[] = [];
      page.on("pageerror", (err) => pageErrors.push(String(err)));
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });

      await page.goto(route, { waitUntil: "domcontentloaded" });
      await expect(page.locator("#conteudo-principal")).toBeVisible({ timeout: 15000 });
      // Wait for real content (not empty skeleton)
      await expect
        .poll(async () => (await page.locator("#conteudo-principal").innerText()).trim().length, {
          timeout: 20000,
        })
        .toBeGreaterThan(5);
      const headings = page.locator("#conteudo-principal h1, #conteudo-principal h2");
      await expect(headings.first()).toBeVisible({ timeout: 15000 });
      expect(pageErrors, `pageerror on ${route}: ${pageErrors.join("; ")}`).toEqual([]);
      const unexpected = consoleErrors.filter(
        (t) => !t.includes("favicon") && !t.includes("Download the React DevTools"),
      );
      expect(unexpected, `console.error on ${route}: ${unexpected.join("; ")}`).toEqual([]);
    });
  }

  test("invalid route shows NotFound, not silent home redirect", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-xyz", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("not-found")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("heading", { name: /não encontrada/i })).toBeVisible();
    // URL should remain the invalid path (no silent replace to /)
    expect(page.url()).toMatch(/this-route-does-not-exist-xyz/);
  });
});
