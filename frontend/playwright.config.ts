import { defineConfig } from "@playwright/test";

/**
 * Test end-to-end dell'interfaccia contro un'istanza già avviata (API + worker + build).
 * E2E_URL indica l'indirizzo (predefinito: http://127.0.0.1:8765). Usa Microsoft Edge già
 * installato in Windows: nessun browser da scaricare.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_URL ?? "http://127.0.0.1:8765",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
});
