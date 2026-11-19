import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    browserName: "chromium",
    baseURL: process.env.DESK_TEST_APP_URL ?? "http://127.0.0.1:18765",
    viewport: { width: 1440, height: 990 },
    trace: "retain-on-failure",
    launchOptions: { executablePath: process.env.DESK_CHROMIUM_EXECUTABLE },
  },
});
