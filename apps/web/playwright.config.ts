import { defineConfig, devices } from "@playwright/test";

/**
 * playwright.config.ts — Track B 端到端验收（杀手锏溯源流）。
 *
 * - testDir "e2e"：与 vitest（src/**.test.ts）零重叠，互不干扰。
 * - webServer：自动起 vite dev（默认 5173，可用 E2E_PORT 覆盖），reuseExistingServer 便于本地反复跑。
 *   ⚠️ reuseExistingServer 会复用端口上已有的任何服务——若 5173 被其他项目占用，
 *   请用 `E2E_PORT=<空闲端口> pnpm e2e` 运行，避免对着别的应用跑测试。
 * - 全程用 page.route 注入契约 fixture，不依赖后端在线（联调只在 F6）。
 */
const E2E_PORT = Number(process.env.E2E_PORT || 5173);

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // 容器内以 root 运行需 --no-sandbox，否则 chromium 拒绝启动
        launchOptions: { args: ["--no-sandbox", "--disable-dev-shm-usage"] },
      },
    },
  ],
  webServer: {
    command: `pnpm exec vite --port ${E2E_PORT} --strictPort`,
    url: `http://localhost:${E2E_PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
