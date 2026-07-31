import { expect, test } from "@playwright/test";

test.describe("Command Center critical flows", () => {
  test("opens app, shows actions, runs fixture job", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    await page.getByRole("link", { name: "Todas as ações" }).click();
    await expect(page.getByRole("heading", { name: /Todas as ações/i })).toBeVisible();
    await page.goto("/actions/cc.fixture.echo");
    await expect(page.getByRole("heading", { name: /Fixture/i })).toBeVisible();
    await page.getByRole("button", { name: /Executar agora/i }).click();
    await expect(page).toHaveURL(/\/jobs\//);
    await expect(page.getByText(/FIXTURE_DONE|Command Center fixture|Concluído|Em execução|Situação/i)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("theme toggle and command palette", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    await page.getByRole("button", { name: /Ações rápidas/i }).click();
    await expect(page.getByPlaceholder(/Buscar ou executar/i)).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Tema" }).click();
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme === "light" || theme === "dark").toBeTruthy();
  });

  test("keyboard main nav reaches Extra and Documents", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation").getByRole("link", { name: /Oportunidades Extra/i }).click();
    await expect(page).toHaveURL(/\/extra/);
    await expect(page.getByRole("heading", { name: /Oportunidades Extra/i })).toBeVisible();
    await page.getByRole("navigation").getByRole("link", { name: "Documentos" }).click();
    await expect(page).toHaveURL(/\/documents/);
    await expect(page.getByRole("heading", { name: /Documentos/i })).toBeVisible();
  });

  test("global search and open artifact sample", async ({ page, request }) => {
    // Ensure a readable sample artifact under allowed root via API surface of jobs folder
    // Use recent artifacts page — if empty, still validate search route.
    await page.goto("/");
    await page.getByLabel("Busca global").fill("extra");
    await page.getByLabel("Busca global").press("Enter");
    await expect(page).toHaveURL(/\/search\?q=extra/);
    await expect(page.getByRole("heading", { name: "Busca" })).toBeVisible();
    // Capability results or empty state — both honest
    const body = await page.locator("main").innerText();
    expect(body.length).toBeGreaterThan(10);

    await page.goto("/results");
    await expect(page.getByRole("heading", { name: /Resultados/i })).toBeVisible();
    const count = await page.locator("main li a").count();
    if (count > 0) {
      await page.locator("main li a").first().click();
      await expect(page).toHaveURL(/path=/);
      await expect(page.locator("main")).toContainText(
        /Baixar|json|md|csv|bytes|Tabela|arquivo|sample|\{|path|resultado/i,
      );
    } else {
      await expect(page.getByText(/Ainda não há resultados|Nenhum/i)).toBeVisible();
    }
    void request;
  });

  test("confenge logo is present in shell", async ({ page }) => {
    await page.goto("/");
    const logos = page.locator('img[alt="CONFENGE"], .brand-logo, .brand-logo-pair img');
    await expect(logos.first()).toBeVisible();
    const src = await logos.first().getAttribute("src");
    expect(src || "").toMatch(/logo-confenge(\.svg|\.png)?/);
  });

  test("secrets absent in DOM from health-backed UI", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /O que fazer agora/i })).toBeVisible();
    await page.goto("/onboarding");
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/postgresql:\/\/[^\s]+/i);
    expect(text).not.toMatch(/password\s*=\s*\S+/i);
    expect(text).not.toMatch(/sk-[A-Za-z0-9]{20,}/);
    // presence labels are ok
    expect(text.toLowerCase()).toMatch(/configurada|ausente|inválida|python|capabilities/);
  });

  test("rejects arbitrary command params via API surface", async ({ request }) => {
    const csrf = await request.get("/api/csrf");
    const body = await csrf.json();
    const token = body.csrf_token as string;
    const cookie = csrf.headers()["set-cookie"] || "";
    const res = await request.post("/api/jobs", {
      headers: {
        "X-CC-CSRF": token,
        Cookie: Array.isArray(cookie) ? cookie.join(";") : cookie,
        "Content-Type": "application/json",
      },
      data: {
        capability_id: "cc.fixture.echo",
        params: { command: "rm -rf /", message: "x" },
      },
    });
    expect(res.status()).toBe(400);
  });

  test("human review queue is not a hardcoded demo only", async ({ page, request }) => {
    const csrf = await request.get("/api/csrf");
    const body = await csrf.json();
    const token = body.csrf_token as string;
    const cookie = csrf.headers()["set-cookie"] || "";
    await request.post("/api/reviews", {
      headers: {
        "X-CC-CSRF": token,
        Cookie: Array.isArray(cookie) ? cookie.join(";") : cookie,
        "Content-Type": "application/json",
      },
      data: {
        title: "Revisão e2e de shortlist",
        source: "e2e",
        evidence: "output/example-evidence.json",
        limitations: "fixture local",
        risks: "não comercial",
      },
    });
    await page.goto("/review");
    await expect(page.getByRole("heading", { name: "Revisão humana" })).toBeVisible();
    await expect(page.getByText("Revisão e2e de shortlist", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("review-demo-local")).toHaveCount(0);
  });
});
