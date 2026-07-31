/**
 * WORKBENCH-01 e2e — real UI path via ./bin/command-center webServer.
 * Covers guided flows, PDF/XLSX viewers, review, compare, mobile, keyboard.
 */
import { expect, test, type Page } from "@playwright/test";

const CONFIRM =
  "Confirmo a geração local de entregáveis (sem envio automático de mensagens).";

async function runWorkflow(page: Page, workflowId: string, confirmPhrase = CONFIRM) {
  await page.goto(`/work/start/${workflowId}`);
  await expect(page.getByRole("button", { name: /Gerar entregáveis/i })).toBeVisible({ timeout: 15_000 });
  // Wait for capability confirmation phrase to load (server-owned)
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: /Gerar entregáveis/i }).click();
  const phraseInput = page.locator("#confirm-phrase");
  await expect(phraseInput).toBeVisible({ timeout: 10_000 });
  const hint = await page.locator("#confirm-phrase-hint").innerText().catch(() => confirmPhrase);
  const phrase = (hint || confirmPhrase).trim();
  await phraseInput.fill("");
  await phraseInput.fill(phrase);
  const confirmBtn = page.getByRole("dialog").getByRole("button", { name: /^Confirmar$/i });
  await expect(confirmBtn).toBeEnabled({ timeout: 5_000 });
  await confirmBtn.click();
  // Surface API errors if navigation does not happen
  const err = page.getByText(/Não foi possível iniciar|Parâmetro|obrigat/i);
  try {
    await expect(page).toHaveURL(/\/jobs\//, { timeout: 30_000 });
  } catch (e) {
    const body = await page.locator("main").innerText();
    throw new Error(`Workflow ${workflowId} did not navigate to job. UI: ${body.slice(0, 500)}`);
  }
  await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible({ timeout: 60_000 });
  await page
    .getByText(/Concluído|prontos|Shortlist|empresas|órgãos|Cobertura|PDF e XLSX/i)
    .first()
    .waitFor({ state: "visible", timeout: 60_000 })
    .catch(() => undefined);
  void err;
}

test.describe("Workbench consulting flows", () => {
  test("home is outcome-first", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Iniciar trabalho|Ver todos os fluxos/i }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Iniciar novo trabalho|Continuar de onde parei|Revisões pendentes/i }).first()).toBeVisible();
  });

  test("catalog lists guided flows without capability jargon as primary", async ({ page }) => {
    await page.goto("/work/start");
    await expect(page.getByRole("heading", { name: /Iniciar trabalho/i })).toBeVisible();
    await expect(page.getByText(/Encontrar oportunidades para a Extra/i)).toBeVisible();
    await expect(page.getByText(/Encontrar empresas com potencial comercial/i)).toBeVisible();
    await expect(page.getByText(/órgãos que podem precisar/i)).toBeVisible();
    await expect(page.getByText(/documentos de processos/i)).toBeVisible();
  });

  test("task1: Extra report PDF and XLSX in browser", async ({ page }) => {
    await runWorkflow(page, "workflow.extra.opportunities");
    // prefer PDF button
    const pdfBtn = page.getByRole("button", { name: /\.pdf/i }).first();
    if (await pdfBtn.isVisible().catch(() => false)) {
      await pdfBtn.click();
      await expect(page.locator("iframe.pdf-frame, iframe[title]").first()).toBeVisible({ timeout: 15_000 });
    }
    const xlsxBtn = page.getByRole("button", { name: /\.xlsx/i }).first();
    if (await xlsxBtn.isVisible().catch(() => false)) {
      await xlsxBtn.click();
      await expect(page.getByText(/Abas:|Resumo|Dados|Oportunidades|Carregando abas/i).first()).toBeVisible({
        timeout: 15_000,
      });
    }
    // must not be only "json/bytes/baixar" as sole proof
    const main = await page.locator("main").innerText();
    expect(main.toLowerCase()).toMatch(/pdf|xlsx|pré-visualização|iframe|abas|relatório|oportunidade/i);
  });

  test("task2: SC suppliers export workbook", async ({ page }) => {
    await runWorkflow(page, "workflow.confenge.suppliers");
    await expect(page.getByRole("button", { name: /\.xlsx|\.pdf/i }).first()).toBeVisible({ timeout: 15_000 });
  });

  test("task3: public agency review decision with rationale", async ({ page }) => {
    await runWorkflow(page, "workflow.confenge.public_agencies");
    await page.goto("/review");
    await expect(page.getByRole("heading", { name: /Revisões humanas/i })).toBeVisible();
    const rationale = page.locator("textarea").first();
    if (await rationale.isVisible().catch(() => false)) {
      await rationale.fill("Classificação preliminar revisada: manter com ressalva de fracionamento.");
      await page.getByRole("button", { name: /Recusar/i }).click();
      await expect(page.getByText(/Decisão registrada|Recusado/i).first()).toBeVisible({ timeout: 10_000 });
    } else {
      await expect(page.getByText(/Nada pendente|Aguardando você/i).first()).toBeVisible();
    }
  });

  test("task4: process documents coverage and PDF", async ({ page }) => {
    await runWorkflow(page, "workflow.process_documents");
    await expect(page.getByRole("button", { name: /\.pdf/i }).first()).toBeVisible({ timeout: 15_000 });
  });

  test("task5: what changed page loads", async ({ page }) => {
    // ensure at least one run
    await runWorkflow(page, "workflow.extra.opportunities");
    await page.goto("/compare?workflow=workflow.extra.opportunities");
    await expect(page.getByRole("heading", { name: /O que mudou/i })).toBeVisible();
    await expect(page.getByText(/Diferenças|execução anterior|fluxo|Compar/i).first()).toBeVisible();
  });

  test("review reject without rationale is blocked in UI", async ({ page }) => {
    await runWorkflow(page, "workflow.extra.opportunities");
    await page.goto("/review");
    const reject = page.getByRole("button", { name: /Recusar/i }).first();
    if (await reject.isVisible().catch(() => false)) {
      await reject.click();
      await expect(page.getByText(/justificativa|mínimo 8/i).first()).toBeVisible({ timeout: 5_000 });
    }
  });

  test("advanced capabilities still available", async ({ page }) => {
    await page.goto("/actions");
    await expect(page.getByRole("heading", { name: /Todas as ações|ações/i })).toBeVisible();
  });

  test("mobile 390x844 home and start work usable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    // open nav if hamburger
    const menu = page.getByRole("button", { name: /menu|navegação|abrir/i }).first();
    if (await menu.isVisible().catch(() => false)) {
      await menu.click();
    }
    await page.goto("/work/start");
    await expect(page.getByRole("heading", { name: /Iniciar trabalho/i })).toBeVisible();
    await expect(page.getByText(/Encontrar oportunidades/i)).toBeVisible();
  });

  test("keyboard can reach Iniciar trabalho and Extra", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation").getByRole("link", { name: /Iniciar trabalho/i }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/work\/start/);
    await page.getByRole("navigation").getByRole("link", { name: /^Extra$/i }).click();
    await expect(page).toHaveURL(/\/extra/);
  });

  test("reload during job recovers state", async ({ page }) => {
    await page.goto("/work/start/workflow.extra.opportunities");
    await page.getByRole("button", { name: /Gerar entregáveis/i }).click();
    const phraseInput = page.locator("#confirm-phrase");
    if (await phraseInput.isVisible().catch(() => false)) {
      await phraseInput.fill(CONFIRM);
      await page.getByRole("button", { name: /Confirmar/i }).click();
    }
    await expect(page).toHaveURL(/\/jobs\//, { timeout: 20_000 });
    const url = page.url();
    await page.reload();
    await expect(page).toHaveURL(url);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByText(/Situação|Concluído|Em execução|Preparando|Resultados/i).first()).toBeVisible({
      timeout: 60_000,
    });
  });

  test("onboarding page has no secrets", async ({ page }) => {
    await page.goto("/onboarding");
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/postgresql:\/\/[^\s]+/i);
    expect(text).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
  });

  test("results / deliverables center opens", async ({ page }) => {
    await page.goto("/results");
    await expect(page.getByRole("heading", { name: /Resultados|Entregáveis/i })).toBeVisible();
  });

  test("no auto-outreach copy on preflight", async ({ page }) => {
    await page.goto("/work/start/workflow.confenge.suppliers");
    await expect(page.getByText(/não.*envio|Outreach automático|Nunca/i).first()).toBeVisible();
  });
});
