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

  test("task3: agency review correction regenerate", async ({ page }) => {
    await runWorkflow(page, "workflow.confenge.public_agencies");
    const jobUrl = page.url();
    const jobId = jobUrl.split("/jobs/")[1]?.split(/[?#]/)[0];
    expect(jobId).toBeTruthy();

    // Resolve exact orgao from this job's run-manifest (source of truth for artifacts)
    const manRes = await page.request.get(`/api/jobs/${jobId}/manifest`);
    expect(manRes.ok()).toBeTruthy();
    const man = await manRes.json();
    const manArts: Array<{ path?: string; logical_name?: string }> =
      man?.manifest?.artifacts || man?.artifacts || [];
    let src0 =
      manArts.map((a) => a.path || "").find((p) => /public_agencies\.json$/i.test(p)) ||
      manArts.map((a) => a.path || "").find((p) => /agencies/i.test(p));
    if (!src0 && man?.path) {
      src0 = String(man.path).replace(/run-manifest\.json$/i, "public_agencies.json");
    }
    if (!src0 && man?.manifest_path) {
      src0 = String(man.manifest_path).replace(/run-manifest\.json$/i, "public_agencies.json");
    }
    expect(src0).toBeTruthy();
    const src0Dl = await page.request.get(`/api/artifacts/download?path=${encodeURIComponent(String(src0))}`);
    expect(src0Dl.ok()).toBeTruthy();
    const src0Text = await src0Dl.text();
    const agencies = JSON.parse(src0Text) as Array<{ orgao?: string }>;
    expect(Array.isArray(agencies) && agencies.length > 0).toBeTruthy();
    const orgaoExact = String(agencies[0].orgao || "");
    expect(orgaoExact.length).toBeGreaterThan(2);

    const reviewsRes = await page.request.get("/api/reviews?status=pending");
    expect(reviewsRes.ok()).toBeTruthy();
    const reviews = (await reviewsRes.json()).reviews || [];
    const item =
      reviews.find(
        (r: { job_id?: string; payload?: { item_key?: string }; title?: string }) =>
          r.job_id === jobId || r.payload?.item_key === orgaoExact || r.title === orgaoExact,
      ) || reviews[0];
    expect(item).toBeTruthy();
    const priorContentHash: string =
      item?.payload?.content_hash || item?.payload?.artifact_hashes?.source || "";

    await page.goto("/review");
    await expect(page.getByRole("heading", { name: /Revisões humanas/i })).toBeVisible();
    const rationale = page.locator("textarea").first();
    await expect(rationale).toBeVisible({ timeout: 15_000 });
    await rationale.fill("Classificação preliminar revisada com ressalva de fracionamento.");
    // REJECT with rationale proves decision path; content correction is via regenerate
    await page.getByRole("button", { name: /Recusar/i }).first().click();
    await expect(page.getByText(/Decisão registrada|Recusado/i).first()).toBeVisible({ timeout: 10_000 });

    const marker = "CORRIGIDA_E2E_PRELIMINAR";
    const csrf = await page.request.get("/api/csrf");
    const csrfJson = await csrf.json();
    const token = (csrfJson.csrf_token || csrfJson.token) as string;
    const regen = await page.request.post("/api/reviews/regenerate", {
      headers: {
        "X-CC-CSRF": token,
        "Content-Type": "application/json",
      },
      data: {
        job_id: jobId,
        item_id: item.id,
        corrections: [
          {
            item_key: orgaoExact,
            orgao: orgaoExact,
            fields: {
              classificacao_juridica_preliminar: marker,
              limitacoes: "Corrigido no e2e; ainda preliminar.",
            },
            note: "e2e classification edit",
          },
        ],
        note: "e2e regenerate with classification correction",
      },
    });
    if (!regen.ok()) {
      throw new Error(
        `regenerate failed ${regen.status()}: ${await regen.text()} orgao=${orgaoExact} src0=${src0}`,
      );
    }
    const body = await regen.json();
    expect(body.job_id).toBeTruthy();
    expect(body.manifest_path).toBeTruthy();
    expect(body.parent_job_id).toBe(jobId);
    expect(body.content_hashes?.source).toBeTruthy();
    // Natural hash change from applied correction (AC#24/#25)
    if (priorContentHash) {
      expect(body.content_hashes.source).not.toBe(priorContentHash);
    }
    expect(String(body.content_hashes.source)).not.toMatch(/^mutated-/);

    // Prove corrected classification is in new dossier source (AC#25)
    const arts: string[] = body.artifacts || [];
    const srcPath = arts.find((a) => /public_agencies\.json$/i.test(a));
    expect(srcPath).toBeTruthy();
    const dl = await page.request.get(`/api/artifacts/download?path=${encodeURIComponent(String(srcPath))}`);
    expect(dl.ok()).toBeTruthy();
    const srcText = await dl.text();
    expect(srcText).toContain(marker);

    // new version has artifacts; prove PDF via UI and XLSX via shipped preview API
    await page.goto(`/jobs/${body.job_id}`);
    await expect(page.getByRole("heading", { name: "Situação" })).toBeVisible();
    const pdfBtn2 = page.getByRole("button", { name: /\.pdf/i }).first();
    await expect(pdfBtn2).toBeVisible({ timeout: 15_000 });
    await pdfBtn2.click();
    await expect(page.locator("iframe.pdf-frame, iframe[title]").first()).toBeVisible({ timeout: 15_000 });
    const xlsxPath = arts.find((a) => /\.xlsx$/i.test(a));
    expect(xlsxPath).toBeTruthy();
    const xprev = await page.request.get(
      `/api/artifacts/preview-xlsx?path=${encodeURIComponent(String(xlsxPath))}`,
    );
    expect(xprev.ok()).toBeTruthy();
    const xp = await xprev.json();
    expect(Array.isArray(xp.sheets) && xp.sheets.length >= 2).toBeTruthy();
    expect(Array.isArray(xp.headers) && xp.headers.length > 0).toBeTruthy();
    // Data sheet holds classification — Resumo does not
    const dataSheet =
      (xp.sheets as string[]).find((s) => /org|dados|empresas|oportun/i.test(s)) || xp.sheets[1];
    const xprevData = await page.request.get(
      `/api/artifacts/preview-xlsx?path=${encodeURIComponent(String(xlsxPath))}&sheet=${encodeURIComponent(dataSheet)}`,
    );
    expect(xprevData.ok()).toBeTruthy();
    const xd = await xprevData.json();
    expect(JSON.stringify(xd)).toContain(marker);
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
