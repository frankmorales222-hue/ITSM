import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    // There's no route at "/" in this app (only /login, /tickets, etc.),
    // and Playwright's readiness poll wants a 2xx — a 404 there kept it
    // waiting forever, so point it at a page that actually exists.
    url: `${BASE_URL}/login`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    env: {
      PORT: String(PORT),
      // Separate build dir so this doesn't collide with a `next dev`
      // you're already running for manual testing — see next.config.mjs.
      NEXT_DIST_DIR: ".next-e2e",
      DATABASE_URL: "postgresql://postgres:dev@localhost:5432/itsm_e2e",
      SESSION_SECRET: "e2e-test-session-secret-not-for-real-use",
      EMAIL_WEBHOOK_SECRET: "e2e-test-webhook-secret-not-for-real-use",
      // Separate logical Redis DB (index 1, not the default 0) so login
      // rate-limit counters here can't trip — or get tripped by — a dev
      // server's real usage sharing the same loopback IP.
      REDIS_URL: "redis://localhost:6379/1",
      S3_ENDPOINT: "http://localhost:9000",
      S3_BUCKET: "itsm-attachments-e2e",
      S3_ACCESS_KEY: "minioadmin",
      S3_SECRET_KEY: "minioadmin",
      ADMIN_SETTINGS_ENCRYPTION_KEY:
        "a01270e325f288629bccc7cf4cdc24f36658271e1b1eacd10af12724a14fd510",
      NEXT_PUBLIC_APP_URL: BASE_URL,
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
