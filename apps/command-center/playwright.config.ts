import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.CC_BASE_URL || "http://127.0.0.1:8765",
    headless: true,
  },
  webServer: process.env.CC_E2E_NO_WEBSERVER
    ? undefined
    : {
        command: "cd ../.. && CC_OPEN_BROWSER=0 ./bin/command-center",
        url: "http://127.0.0.1:8765/api/health",
        reuseExistingServer: true,
        timeout: 180_000,
      },
});
