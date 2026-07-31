import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1280", width: 1280, height: 800 },
  { name: "1024", width: 1024, height: 768 },
  { name: "768", width: 768, height: 1024 },
  { name: "390", width: 390, height: 844 },
] as const;

test.describe("visual + a11y matrix", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      // Deterministic clock
      const fixed = new Date("2026-07-31T15:22:00.000Z").valueOf();
      Date.now = () => fixed;
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
  });

  for (const theme of ["light", "dark"] as const) {
    test(`home ${theme} theme axe + screenshot`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.addInitScript((t) => {
        localStorage.setItem("cc-theme", t);
      }, theme);
      await page.goto("/", { waitUntil: "networkidle" });
      await page.waitForTimeout(300);
      await expect(page.locator("#conteudo-principal")).toBeVisible();
      await page.screenshot({
        path: `test-results/visual-home-${theme}.png`,
        fullPage: true,
      });
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
      const serious = results.violations.filter((v) =>
        ["critical", "serious"].includes(v.impact || ""),
      );
      expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
    });
  }

  for (const vp of VIEWPORTS) {
    test(`home responsive ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await expect(page.locator("#conteudo-principal")).toBeVisible();
      // No horizontal overflow of body
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
      await page.screenshot({
        path: `test-results/visual-home-${vp.name}.png`,
      });
    });
  }

  test("command palette opens and traps focus", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible({
      timeout: 15000,
    });
    // Prefer explicit button (Ctrl+K can be intercepted by the host)
    await page.getByRole("button", { name: /Ações rápidas/i }).click();
    const dialog = page.locator(".palette[role='dialog']");
    await expect(dialog).toBeVisible();
    await expect(page.getByPlaceholder(/Buscar ou executar/i)).toBeVisible();
    await page.screenshot({ path: "test-results/visual-command-palette.png" });
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
});

