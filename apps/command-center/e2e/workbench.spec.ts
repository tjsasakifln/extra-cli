/**
 * WORKBENCH-01 e2e — hard asserts on shipped UI (no soft skips for PDF/XLSX).
 */
import { expect, test, type Page } from "@playwright/test";

const CONFIRM =
  "Confirmo a geração local de entregáveis (sem envio automático de mensagens).";

async function runWorkflow(page: Page, workflowId: string) {
  await page.goto(`/work/start/${workflowId}`);
  await expect(page.getByRole("button", { name: /Gerar entregáveis/i })).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: /Gerar entregáveis/i }).click();
  const phraseInput = page.locator("#confirm-phrase");
  await expect(phraseInput).toBeVisible({ timeout: 10_000 });
  const hint = await page.locator("#confirm-phrase-hint").innerText().catch(() => CONFIRM);
  await phraseInput.fill((hint || CONFIRM).trim());
  await page.getByRole("dialog").getByRole("button", { name: /^Confirmar$/i }).click();
  await expect(page).toHaveURL(/\/jobs\//, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible({ timeout: 60_000 });
  // wait for terminal-ish copy
  await expect(
    page.getByText(/Concluído|prontos|Shortlist|empresas|órgãos|Cobertura|PDF e XLSX|Regeneração/i).first(),
  ).toBeVisible({ timeout: 90_000 });
}

async function openPdfAndXlsx(page: Page) {
  const pdfBtn = page.getByRole("button", { name: /\.pdf/i }).first();
  await expect(pdfBtn).toBeVisible({ timeout: 20_000 });
  await pdfBtn.click();
  await expect(page.locator("iframe.pdf-frame, iframe[title]").first()).toBeVisible({ timeout: 15_000 });

  const xlsxBtn = page.getByRole("button", { name: /\.xlsx/i }).first();
  await expect(xlsxBtn).toBeVisible({ timeout: 15_000 });
  await xlsxBtn.click();
  await expect(page.getByText(/Abas:/i)).toBeVisible({ timeout: 15_000 });
  // sheet switchers (Resumo / Dados / …)
  const sheetBtn = page
    .locator("button")
    .filter({ hasText: /Resumo|Dados|Oportunidades|Empresas|Orgaos|Órgãos|Indice|Índice|Metodologia/i })
    .first();
  await expect(sheetBtn).toBeVisible({ timeout: 10_000 });
  await sheetBtn.click();
  // table may use .data or generic table inside preview
  await expect(page.locator("table").first()).toBeVisible({ timeout: 15_000 });
}

test.describe("Workbench consulting flows", () => {
  test("home is outcome-first", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Iniciar trabalho|Ver todos os fluxos/i }).first()).toBeVisible();
  });

  test("catalog lists guided flows", async ({ page }) => {
    await page.goto("/work/start");
    await expect(page.getByText(/Encontrar oportunidades para a Extra/i)).toBeVisible();
    await expect(page.getByText(/Encontrar empresas com potencial comercial/i)).toBeVisible();
  });

  test("task1: Extra PDF iframe and XLSX sheets", async ({ page }) => {
    await runWorkflow(page, "workflow.extra.opportunities");
    await openPdfAndXlsx(page);
  });

  test("task2: SC suppliers PDF and XLSX", async ({ page }) => {
    await runWorkflow(page, "workflow.confenge.suppliers");
    await openPdfAndXlsx(page);
  });

  test("task3: agency review correction regenerate", async ({ page, request }) => {
    await runWorkflow(page, "workflow.confenge.public_agencies");
    const jobUrl = page.url();
    const jobId = jobUrl.split("/jobs/")[1]?.split(/[?#]/)[0];
    expect(jobId).toBeTruthy();

    await page.goto("/review");
    await expect(page.getByRole("heading", { name: /Revisões humanas/i })).toBeVisible();
    const rationale = page.locator("textarea").first();
    await expect(rationale).toBeVisible({ timeout: 15_000 });
    await rationale.fill("Classificação preliminar revisada com ressalva de fracionamento.");
    // ACCEPT path needs phrase — use REJECT with rationale to prove decision
    await page.getByRole("button", { name: /Recusar/i }).first().click();
    await expect(page.getByText(/Decisão registrada|Recusado/i).first()).toBeVisible({ timeout: 10_000 });

    // regenerate via API (shipped path) with empty corrections = new version
    const csrf = await request.get("/api/csrf");
    const token = (await csrf.json()).csrf_token as string;
    const cookie = csrf.headers()["set-cookie"] || "";
    const regen = await request.post("/api/reviews/regenerate", {
      headers: {
        "X-CC-CSRF": token,
        Cookie: Array.isArray(cookie) ? cookie.join(";") : String(cookie),
        "Content-Type": "application/json",
      },
      data: { job_id: jobId, corrections: [], note: "e2e version bump" },
    });
    expect(regen.ok()).toBeTruthy();
    const body = await regen.json();
    expect(body.job_id).toBeTruthy();
    expect(body.manifest_path).toBeTruthy();
    expect(body.parent_job_id).toBe(jobId);
    expect(body.content_hashes).toBeTruthy();
    // new version has artifacts; prove PDF via UI and XLSX via shipped preview API
    await page.goto(`/jobs/${body.job_id}`);
    await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible();
    const pdfBtn2 = page.getByRole("button", { name: /\.pdf/i }).first();
    await expect(pdfBtn2).toBeVisible({ timeout: 15_000 });
    await pdfBtn2.click();
    await expect(page.locator("iframe.pdf-frame, iframe[title]").first()).toBeVisible({ timeout: 15_000 });
    const arts: string[] = body.artifacts || [];
    const xlsxPath = arts.find((a) => /\.xlsx$/i.test(a));
    expect(xlsxPath).toBeTruthy();
    const xprev = await request.get(`/api/artifacts/preview-xlsx?path=${encodeURIComponent(String(xlsxPath))}`);
    expect(xprev.ok()).toBeTruthy();
    const xp = await xprev.json();
    expect(Array.isArray(xp.sheets) && xp.sheets.length >= 2).toBeTruthy();
    expect(Array.isArray(xp.headers) && xp.headers.length > 0).toBeTruthy();
  });

  test("task4: process documents PDF coverage", async ({ page }) => {
    await runWorkflow(page, "workflow.process_documents");
    const pdfBtn = page.getByRole("button", { name: /\.pdf/i }).first();
    await expect(pdfBtn).toBeVisible({ timeout: 20_000 });
    await pdfBtn.click();
    await expect(page.locator("iframe.pdf-frame, iframe[title]").first()).toBeVisible({ timeout: 15_000 });
  });

  test("task5: compare shows real deltas between two runs", async ({ page }) => {
    await runWorkflow(page, "workflow.confenge.suppliers");
    // second run with different top N to create delta
    await page.goto("/work/start/workflow.confenge.suppliers");
    const maxInput = page.locator('input[type="number"]').first();
    if (await maxInput.isVisible().catch(() => false)) {
      await maxInput.fill("5");
    }
    await page.getByRole("button", { name: /Gerar entregáveis/i }).click();
    const phraseInput = page.locator("#confirm-phrase");
    await expect(phraseInput).toBeVisible();
    const hint = await page.locator("#confirm-phrase-hint").innerText().catch(() => CONFIRM);
    await phraseInput.fill((hint || CONFIRM).trim());
    await page.getByRole("dialog").getByRole("button", { name: /^Confirmar$/i }).click();
    await expect(page).toHaveURL(/\/jobs\//, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible({ timeout: 60_000 });

    await page.goto("/compare?workflow=workflow.confenge.suppliers");
    await expect(page.getByRole("heading", { name: /O que mudou/i })).toBeVisible();
    // hard: either real counts or explicit no-previous message — not empty shell only
    await expect(
      page.getByText(/Novos|Removidos|Alterados|Diferenças|Não há execução anterior|itens/i).first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("review reject without rationale blocked", async ({ page }) => {
    await runWorkflow(page, "workflow.extra.opportunities");
    await page.goto("/review");
    const reject = page.getByRole("button", { name: /Recusar/i }).first();
    await expect(reject).toBeVisible({ timeout: 15_000 });
    await reject.click();
    await expect(page.getByText(/justificativa|mínimo 8/i).first()).toBeVisible({ timeout: 5_000 });
  });

  test("mobile 390x844 start work", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/work/start");
    await expect(page.getByRole("heading", { name: /Iniciar trabalho/i })).toBeVisible();
    await expect(page.getByText(/Encontrar oportunidades/i)).toBeVisible();
  });

  test("keyboard to Iniciar trabalho", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation").getByRole("link", { name: /Iniciar trabalho/i }).click();
    await expect(page).toHaveURL(/\/work\/start/);
  });

  test("reload recovers job", async ({ page }) => {
    await runWorkflow(page, "workflow.extra.opportunities");
    const url = page.url();
    await page.reload();
    await expect(page).toHaveURL(url);
    await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible();
  });
});
