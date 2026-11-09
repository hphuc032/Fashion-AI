import { test, expect } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, readFileSync, mkdirSync } from "node:fs";
import { randomBytes, randomUUID, createHash } from "node:crypto";
import { resolve } from "node:path";
import { tmpdir } from "node:os";

const root = resolve("../..");
const python =
  process.env.FASHION_WEB_PYTHON ??
  (process.platform === "win32"
    ? resolve(root, ".venv-web/Scripts/python.exe")
    : "python");
const profile = mkdtempSync(
  resolve(process.env.FASHION_WEB_QA_ROOT ?? tmpdir(), "fashion-w2-e2e-"),
);
const storage = resolve(profile, "storage");
const database = resolve(profile, "projects.db");
const video = resolve(profile, "authorized.mp4");
const origin = "http://127.0.0.1:3000",
  api = "http://127.0.0.1:8000/api/v1";
let backend: ChildProcess,
  frontend: ChildProcess,
  secret: string,
  instance: string;
function provision() {
  mkdirSync(storage);
  const result = spawnSync(
    python,
    [
      "-c",
      "from sqlalchemy import create_engine; from app.database.models import Project; import sys; e=create_engine('sqlite:///'+sys.argv[1]); Project.__table__.create(e); e.dispose()",
      database,
    ],
    { cwd: root, windowsHide: true, encoding: "utf8" },
  );
  expect(result.status, result.stderr).toBe(0);
  const fixture = spawnSync(
    process.env.FASHION_WEB_FFMPEG ?? "ffmpeg",
    [
      "-v",
      "error",
      "-f",
      "lavfi",
      "-i",
      "testsrc2=s=320x240:r=24",
      "-t",
      "12",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      video,
    ],
    { windowsHide: true, encoding: "utf8" },
  );
  expect(fixture.status, fixture.stderr).toBe(0);
}
function startApi() {
  secret = randomBytes(32).toString("base64url");
  instance = randomUUID();
  backend = spawn(python, ["-m", "fashion_api.serve"], {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: resolve(root, "apps/api"),
      PYTHONNOUSERSITE: "1",
    },
    windowsHide: true,
    stdio: ["pipe", "ignore", "ignore"],
  });
  backend.stdin!.end(
    JSON.stringify({
      config: {
        profile,
        runtime_dir: resolve(profile, "web-runtime"),
        repository: root,
        database_path: database,
        storage_root: storage,
        ffmpeg: process.env.FASHION_WEB_FFMPEG ?? "ffmpeg",
        ffprobe: process.env.FASHION_WEB_FFPROBE ?? "ffprobe",
      },
      secret,
      instance_id: instance,
    }) + "\n",
  );
}
async function ready(url: string) {
  for (let n = 0; n < 200; n++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
      if (
        response.ok &&
        (!url.endsWith("/health") ||
          (await response.json()).instance_id === instance)
      )
        return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw Error("W2 actual service readiness timeout");
}
async function stop(child?: ChildProcess) {
  if (child && child.exitCode === null && child.signalCode === null)
    await new Promise<void>((r) => {
      child.once("exit", () => r());
      child.kill();
    });
}
test.beforeAll(async () => {
  provision();
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
      windowsHide: true,
      stdio: "ignore",
      env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
    },
  );
  await ready(origin + "/dashboard");
});
test.afterAll(async () => {
  await stop(frontend);
  await stop(backend);
});

test("real authorized upload, library, metadata, playback, range seeking and restart persistence", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await expect(
    page.getByText("Chưa có dự án. Nhập video đầu tiên để bắt đầu."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Tạo dự án", exact: true }).click();
  await page.getByLabel("Hoặc chọn video").setInputFiles(video);
  await expect(page.getByRole("button", { name: "Tiếp tục" })).toBeVisible();
  await page.getByRole("button", { name: "Tiếp tục" }).click();
  await page.getByLabel("Tác giả", { exact: true }).fill("W2 fixture creator");
  await page.getByLabel("Quyền sử dụng", { exact: true }).selectOption("owned");
  await expect(
    page.getByRole("button", { name: "Upload & tạo dự án" }),
  ).toBeDisabled();
  await page.getByRole("checkbox").check();
  const posted = page.waitForResponse(
    (r) => r.url() === api + "/projects" && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Upload & tạo dự án" }).click();
  await expect(page.getByRole("progressbar")).toBeVisible();
  const response = await posted;
  expect(response.status()).toBe(201);
  const created = await response.json();
  await page.waitForURL(origin + "/projects/" + created.id);
  await expect(
    page.getByRole("heading", { name: "authorized.mp4", exact: true }),
  ).toBeVisible();
  const player = page.locator("video");
  await expect(player).toBeVisible();
  await expect
    .poll(() => player.evaluate((v) => (v as HTMLVideoElement).readyState))
    .toBeGreaterThanOrEqual(2);
  await player.evaluate(async (v) => {
    const video = v as HTMLVideoElement;
    video.muted = true;
    await video.play();
  });
  await expect
    .poll(() => player.evaluate((v) => (v as HTMLVideoElement).currentTime))
    .toBeGreaterThan(0);
  await player.evaluate((v) => {
    (v as HTMLVideoElement).currentTime = 7;
  });
  await expect
    .poll(() => player.evaluate((v) => (v as HTMLVideoElement).currentTime))
    .toBeGreaterThanOrEqual(7);
  const range = await page.evaluate(
    async (url) => {
      const r = await fetch(url, {
        credentials: "include",
        headers: { Range: "bytes=100-299" },
      });
      return {
        status: r.status,
        range: r.headers.get("Content-Range"),
        bytes: Array.from(new Uint8Array(await r.arrayBuffer())),
      };
    },
    api + "/projects/" + created.id + "/source",
  );
  expect(range.status).toBe(206);
  expect(range.range).toContain("bytes 100-299/");
  expect(Buffer.from(range.bytes)).toEqual(
    readFileSync(video).subarray(100, 300),
  );
  await expect(
    page.getByText("OCR & Translation — W3 · Chưa khả dụng"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sửa thông tin nguồn" }).click();
  await page.getByLabel("Tác giả", { exact: true }).fill("Updated creator");
  await page.getByRole("button", { name: "Lưu metadata" }).click();
  await expect(
    page.getByText("Updated creator", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Thư viện", exact: true }).click();
  await page.getByLabel("Tên video hoặc tác giả").fill("authorized");
  await page.getByRole("button", { name: "Tìm kiếm", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "authorized.mp4" }),
  ).toBeVisible();
  await stop(backend);
  startApi();
  await ready(api + "/health");
  await page.goto(origin + "/dashboard#bootstrap=" + secret);
  // A full navigation from the library starts bootstrap immediately. Await
  // the session exchange before reloading; otherwise the reload aborts the
  // one-use exchange after the fragment has already been cleared.
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Backend đang online")).toBeVisible();
  await page.goto(origin + "/projects/" + created.id);
  await expect(
    page.getByRole("heading", { name: "authorized.mp4" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.locator("video").evaluate((v) => (v as HTMLVideoElement).readyState),
    )
    .toBeGreaterThanOrEqual(2);
  const hash = await page.evaluate(
    async (url) => {
      const r = await fetch(url, { credentials: "include" });
      return Array.from(
        new Uint8Array(
          await crypto.subtle.digest("SHA-256", await r.arrayBuffer()),
        ),
      )
        .map((v) => v.toString(16).padStart(2, "0"))
        .join("");
    },
    api + "/projects/" + created.id + "/source",
  );
  expect(hash).toBe(
    createHash("sha256").update(readFileSync(video)).digest("hex"),
  );
  expect(errors).toEqual([]);
  mkdirSync(resolve(root, ".web-local"), { recursive: true });
  await page.screenshot({
    path: resolve(root, ".web-local/w2-project-detail.png"),
    fullPage: true,
  });
});
