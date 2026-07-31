import { expect, test } from "@playwright/test";

test.describe("Command Center critical flows", () => {
  test("opens app, shows capabilities, runs fixture job", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Visão Geral" })).toBeVisible();
    await page.getByRole("link", { name: "Capabilities" }).click();
    await expect(page.getByRole("heading", { name: "Capabilities" })).toBeVisible();
    await page.getByRole("link", { name: "Abrir" }).first().click();
    // Navigate directly to fixture for determinism
    await page.goto("/capabilities/cc.fixture.echo");
    await expect(page.getByRole("heading", { name: /Fixture/i })).toBeVisible();
    await page.getByRole("button", { name: "Executar" }).click();
    await expect(page).toHaveURL(/\/jobs\//);
    await expect(page.getByText(/FIXTURE_DONE|Command Center fixture|Concluído|Em execução/i)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("theme toggle and keyboard palette", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Visão Geral" })).toBeVisible();
    // Button is reliable across OS keyboard maps; Ctrl+K also wired in AppShell.
    await page.getByRole("button", { name: /Comandos/i }).click();
    await expect(page.getByPlaceholder(/Buscar ou executar/i)).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Tema" }).click();
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme === "light" || theme === "dark").toBeTruthy();
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
});
