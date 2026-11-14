import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: process.env.SENTRIX_URL ?? "http://127.0.0.1:8131",
    viewport: { width: 1500, height: 950 },
    video: process.env.SENTRIX_VIDEO ? "on" : "off",
  },
});
