import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  use: {
    baseURL: process.env.APP_URL || "http://localhost:3000",
    headless: true,
    viewport: { width: 1440, height: 960 },
  },
  reporter: "list",
  outputDir: "test-results",
});
