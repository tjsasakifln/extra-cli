import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "1280", width: 1280, height: 800 },
  { name: "1024", width: 1024, height: 768 },
  { name: "768", width: 768, height: 1024 },
  { name: "390", width: 390, height: 844 },
] as const;

async function axeSerious(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) => ["critical", "serious"].includes(v.impact || ""));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test.describe("visual + a11y matrix", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
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
      await page.screenshot({ path: `test-results/visual-home-${theme}.png`, fullPage: true });
      await axeSerious(page);
    });
  }

  for (const vp of VIEWPORTS) {
    test(`home responsive ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await expect(page.locator("#conteudo-principal")).toBeVisible();
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
      await page.screenshot({ path: `test-results/visual-home-${vp.name}.png` });
    });
  }

  test("command palette opens and traps focus", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible({
      timeout: 15000,
    });
    await page.getByRole("button", { name: /Ações rápidas/i }).click();
    const dialog = page.locator(".palette[role='dialog']");
    await expect(dialog).toBeVisible();
    await expect(page.getByPlaceholder(/Buscar ou executar/i)).toBeVisible();
    await page.screenshot({ path: "test-results/visual-command-palette.png" });
    await axeSerious(page);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`component matrix ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.addInitScript((t) => {
        localStorage.setItem("cc-theme", t);
      }, theme);
      await page.goto("/__visual_matrix", { waitUntil: "networkidle" });
      await expect(page.getByTestId("visual-matrix")).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole("heading", { name: /Matriz visual/i })).toBeVisible();
      // All status kinds rendered
      for (const label of [
        "Saudável",
        "Em andamento",
        "Atenção",
        "Aguardando decisão humana",
        "Bloqueio técnico",
        "Bloqueio externo",
        "Parcial",
        "Sem dados",
        "Comprovado",
        "Status desconhecido",
      ]) {
        await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
      }
      await page.screenshot({ path: `test-results/visual-matrix-${theme}.png`, fullPage: true });
      await axeSerious(page);

      // Dialog dynamic state + axe
      await page.getByRole("button", { name: /Abrir dialog/i }).click();
      const demoDialog = page.getByRole("dialog", { name: /Dialog de exemplo/i });
      await expect(demoDialog).toBeVisible();
      await page.screenshot({ path: `test-results/visual-dialog-${theme}.png` });
      await axeSerious(page);
      // Programmatic click so backdrop does not intercept Playwright pointer
      await demoDialog.getByRole("button", { name: /^Fechar$/i }).evaluate((el: HTMLElement) => el.click());
      await expect(demoDialog).toHaveCount(0);
    });
  }

  test("review queue screenshot", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/review", { waitUntil: "networkidle" });
    await expect(page.locator("#conteudo-principal")).toBeVisible();
    await page.screenshot({ path: "test-results/visual-review-queue.png", fullPage: true });
    await axeSerious(page);
  });

  test("FIXTURE workflow banner", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/work/start/workflow.extra.opportunities", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: /MODO DEMONSTRAÇÃO|MODO REAL/i })).toBeVisible({
      timeout: 15000,
    });
    await page.screenshot({ path: "test-results/visual-fixture-workflow.png", fullPage: true });
    await axeSerious(page);
  });

  test("REAL blocked preflight honesty", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/work/start/workflow.extra.opportunities", { waitUntil: "domcontentloaded" });
    const pf = await page.request.get(
      "/api/workflows/workflow.extra.opportunities/preflight?data_mode=REAL",
    );
    expect(pf.ok()).toBeTruthy();
    const body = await pf.json();
    if (!body.safe_to_run) {
      expect(String(body.status)).toMatch(/^BLOCKED_/);
    }
    await page.screenshot({ path: "test-results/visual-real-blocked.png", fullPage: true });
  });

  test("error state on visual matrix", async ({ page }) => {
    await page.goto("/__visual_matrix", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("alert").filter({ hasText: /Falha de exemplo/i })).toBeVisible({
      timeout: 10000,
    });
    await page.screenshot({ path: "test-results/visual-error-state.png" });
  });
});

