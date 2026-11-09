import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes, randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

const root = resolve("../..");
const python =
  process.env.FASHION_WEB_PYTHON ??
  (process.platform === "win32"
    ? resolve(root, ".venv-web/Scripts/python.exe")
    : "python");
const profile = mkdtempSync(
  resolve(process.env.FASHION_WEB_QA_ROOT ?? tmpdir(), "fashion-web-e2e-"),
);
const sentinel = resolve(profile, "do-not-open.db");
writeFileSync(sentinel, "isolated profile must remain unchanged");
let backend: ChildProcess;
let frontend: ChildProcess;
let secret: string;
let apiInstance: string;
const origin = "http://127.0.0.1:3000";
const api = "http://127.0.0.1:8000/api/v1";

function startApi() {
  secret = randomBytes(32).toString("base64url");
  apiInstance = randomUUID();
  backend = spawn(python, ["-m", "fashion_api.serve"], {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: resolve(root, "apps/api"),
      PYTHONNOUSERSITE: "1",
    },
    stdio: ["pipe", "ignore", "ignore"],
    windowsHide: true,
  });
  backend.stdin!.end(
    JSON.stringify({
      config: {
        profile,
        runtime_dir: resolve(profile, "web-runtime"),
        repository: root,
        database_path: sentinel,
        ffmpeg: process.env.FASHION_WEB_FFMPEG ?? "ffmpeg",
        ffprobe: process.env.FASHION_WEB_FFPROBE ?? "ffprobe",
      },
      secret,
      instance_id: apiInstance,
    }) + "\n",
  );
}
async function ready(url: string) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
      if (response.ok && (!url.endsWith("/health") || (await response.json()).instance_id === apiInstance)) return;
    } catch {
      /* bounded startup */
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error("Real service readiness timeout");
}
async function stop(process?: ChildProcess) {
  if (process && process.exitCode === null && process.signalCode === null) {
    await new Promise<void>((resolve) => {
      process.once("exit", () => resolve());
      process.kill();
    });
  }
}
test.beforeAll(async () => {
  startApi();
  await ready(api + "/health");
  frontend = spawn(
    process.execPath,
    [
      resolve("node_modules/next/dist/bin/next"),
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      "3000",
    ],
    {
      cwd: process.cwd(),
      env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
      stdio: "ignore",
      windowsHide: true,
    },
  );
  await ready(origin + "/dashboard");
});
test.afterAll(async () => {
  await stop(frontend);
  await stop(backend);
  expect(readFileSync(sentinel, "utf8")).toBe(
    "isolated profile must remain unchanged",
  );
});
test("real authenticated dashboard, contract and preserved data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await expect(page.getByText("Backend đang online")).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");
  const state = await page.evaluate(
    async (api) =>
      (await fetch(api + "/system/status", { credentials: "include" })).json(),
    api,
  );
  expect(state.database).toEqual({
    configured: true,
    schema_status: "not_inspected",
  });
  expect(state.models).toBe("not_inspected");
  await expect(page.getByTestId("schema-status")).toHaveText("not_inspected");
  await expect(page.getByText("Các bước AI chưa khả dụng")).toBeVisible();
  expect(
    await page.getByRole("button", { name: /OCR|render|tải video/i }).count(),
  ).toBe(0);
  await page.getByRole("link", { name: /^Dự án$/ }).click();
  await expect(
    page.getByRole("heading", { name: "Dự án video" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Tổng quan", exact: true }).click();
  await expect(page.getByText("Backend đang online")).toBeVisible();
  expect(errors).toEqual([]);
  mkdirSync(resolve(root, ".web-local"), { recursive: true });
  await page.screenshot({
    path: resolve(root, ".web-local/w1-dashboard.png"),
    fullPage: true,
  });
});
test("missing session, untrusted origins and frontend Host are rejected", async ({
  page,
  request,
}) => {
  await page.goto(origin + "/dashboard");
  await expect(page.getByText("Cần mở liên kết khởi động mới")).toBeVisible();
  expect((await request.get(api + "/system/status")).status()).toBe(401);
  expect(
    (
      await request.get(api + "/health", {
        headers: { Origin: "http://evil.example" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.get(origin + "/dashboard", {
        headers: { Host: "evil.example" },
      })
    ).status(),
  ).toBe(400);
  expect(
    (
      await request.get(api + "/health", {
        headers: { Host: "evil.example:8000" },
      })
    ).status(),
  ).toBe(400);
});
test("bootstrap replay is rejected on the real API", async ({ request }) => {
  await stop(backend);
  startApi();
  await ready(api + "/health");
  const first = await request.post(api + "/session/bootstrap", {
    headers: { Origin: origin }, data: { bootstrap_secret: secret },
  });
  expect(first.status()).toBe(200);
  const replay = await request.post(api + "/session/bootstrap", {
    headers: { Origin: origin },
    data: { bootstrap_secret: secret },
  });
  expect(replay.status()).toBe(401);
});
test("restart invalidates old session and a new link reconnects", async ({
  page,
}) => {
  await stop(backend);
  startApi();
  await ready(api + "/health");
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await stop(backend);
  startApi();
  await ready(api + "/health");
  await page.reload();
  await expect(page.getByText("Cần mở liên kết khởi động mới")).toBeVisible();
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await page.reload();
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await page.getByRole("button", { name: "Kết thúc phiên" }).click();
  await expect(page.getByText("Cần mở liên kết khởi động mới")).toBeVisible();
});
test("real backend disconnect shows offline and recovers", async ({ page }) => {
  await stop(backend);
  startApi();
  await ready(api + "/health");
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await stop(backend);
  await page.getByRole("button", { name: "Kiểm tra lại" }).click();
  await expect(page.getByText("Chưa kết nối được backend")).toBeVisible();
  startApi();
  await ready(api + "/health");
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await page.reload();
  await expect(page.getByText("Backend đang online")).toBeVisible();
});
test("small viewport stays within width and keyboard navigation works", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(origin + "/dashboard");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Đến nội dung chính" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await page.getByRole("button", { name: "Mở hoặc đóng điều hướng" }).click();
  await expect(page.getByRole("link", { name: /^Dự án$/ })).toBeVisible();
});
