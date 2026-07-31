import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const ROUTES = ["/", "/work/start", "/review", "/results", "/compare", "/onboarding", "/extra"];

test.describe("Accessibility axe (main routes)", () => {
  for (const route of ROUTES) {
    test(`axe no critical/serious on ${route}`, async ({ page }) => {
      await page.goto(route);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const bad = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
      if (bad.length) {
        const summary = bad.map((v) => `${v.id}(${v.impact}): ${v.help} nodes=${v.nodes.length}`).join("\n");
        expect(bad, summary).toEqual([]);
      }
    });
  }
});
