import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, it, vi, beforeEach } from "vitest";
import {
  ProjectLibrary,
  ProjectOverview,
  CreateProject,
  ProjectDetail,
} from "./projects";
import * as api from "@/lib/api-client";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof api>()),
  readProjects: vi.fn(),
  readStorage: vi.fn(),
  readProject: vi.fn(),
  uploadProject: vi.fn(),
}));
const project: api.Project = {
  id: "00000000-0000-4000-8000-000000000001",
  original_filename: "fixture.mp4",
  rights_status: "owned",
  file_size: 2048,
  duration: 12,
  width: 320,
  height: 240,
  fps: 24,
  video_codec: "h264",
  audio_codec: null,
  aspect_ratio: "4:3",
  status: "imported",
  processing_status: "idle",
  created_at: "2026-11-09T00:00:00Z",
  updated_at: "2026-11-09T00:00:00Z",
  revision: "revision",
};
function mount(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.readStorage).mockResolvedValue({
    ready: true,
    profile_status: "ready",
    writable: true,
    disk_free_bytes: 1000000000,
    disk_total_bytes: 2000000000,
    max_upload_bytes: 524288000,
    max_video_seconds: 180,
    checks: [],
  });
  vi.mocked(api.readProjects).mockResolvedValue({
    items: [],
    next_cursor: null,
    total: 0,
    completed: 0,
  });
  URL.createObjectURL = vi.fn(() => "blob:fixture");
  URL.revokeObjectURL = vi.fn();
});
it("renders real project empty state and storage limits", async () => {
  mount(<ProjectOverview />);
  expect(
    await screen.findByText("Chưa có dự án. Nhập video đầu tiên để bắt đầu."),
  ).toBeVisible();
  expect(screen.getByText(/Kho video: Sẵn sàng/)).toBeVisible();
});
it("searches and paginates server records without accumulating all projects", async () => {
  vi.mocked(api.readProjects)
    .mockResolvedValueOnce({
      items: [project],
      next_cursor: "next",
      total: 21,
      completed: 0,
    })
    .mockResolvedValue({
      items: [],
      next_cursor: null,
      total: 0,
      completed: 0,
    });
  mount(<ProjectLibrary />);
  expect(
    await screen.findByRole("heading", { name: "fixture.mp4" }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Trang tiếp" }));
  await waitFor(() =>
    expect(api.readProjects).toHaveBeenCalledWith(
      "",
      "next",
      expect.any(AbortSignal),
    ),
  );
  fireEvent.change(screen.getByLabelText("Tên video hoặc tác giả"), {
    target: { value: "coat" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Tìm kiếm" }));
  await waitFor(() =>
    expect(api.readProjects).toHaveBeenCalledWith(
      "coat",
      undefined,
      expect.any(AbortSignal),
    ),
  );
});
it("shows profile/offline errors without fabricated counts", async () => {
  vi.mocked(api.readProjects).mockRejectedValue(
    new api.ApiError("PROFILE_REQUIRED", 503),
  );
  mount(<ProjectLibrary />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Chưa cấu hình database",
  );
});
it("requires rights confirmation, shows upload progress and preserves safe error", async () => {
  vi.mocked(api.uploadProject).mockImplementation(
    async (_f, _m, _k, _s, progress) => {
      progress(42);
      throw new api.ApiError("INSUFFICIENT_STORAGE", 507);
    },
  );
  mount(<CreateProject />);
  fireEvent.change(screen.getByLabelText("Hoặc chọn video"), {
    target: { files: [new File(["fixture"], "fixture.mp4")] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Tiếp tục" }));
  expect(
    screen.getByRole("button", { name: "Upload & tạo dự án" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Upload & tạo dự án" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Upload & tạo dự án" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Không đủ dung lượng",
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "42");
  fireEvent.click(screen.getByRole("button", { name: "Thử lại cùng yêu cầu" }));
  await waitFor(() => expect(api.uploadProject).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.uploadProject).mock.calls[0][2]).toBe(
    vi.mocked(api.uploadProject).mock.calls[1][2],
  );
});
it("rejects invalid local selection before uploading", () => {
  mount(<CreateProject />);
  fireEvent.change(screen.getByLabelText("Hoặc chọn video"), {
    target: { files: [new File(["text"], "script.exe")] },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("không hợp lệ");
  expect(api.uploadProject).not.toHaveBeenCalled();
});
it("renders authenticated source and unavailable AI stages, handles playback error", async () => {
  vi.mocked(api.readProject).mockResolvedValue(project);
  const { container } = mount(<ProjectDetail id={project.id} />);
  expect(
    await screen.findByRole("heading", { name: "fixture.mp4" }),
  ).toBeVisible();
  const video = container.querySelector("video")!;
  expect(video.src).toBe(api.API_BASE + "/projects/" + project.id + "/source");
  expect(video.crossOrigin).toBe("use-credentials");
  expect(
    screen.getByText("OCR & Translation — W3 · Chưa khả dụng"),
  ).toBeVisible();
  fireEvent.error(video);
  expect(screen.getByRole("alert")).toHaveTextContent("Không phát được video");
});

it("cancels an active upload and warns before internal navigation", async () => {
  vi.mocked(api.uploadProject).mockImplementation(
    (_f, _m, _k, signal, progress) =>
      new Promise((_resolve, reject) => {
        progress(12);
        signal.addEventListener("abort", () =>
          reject(new api.ApiError("ABORTED")),
        );
      }),
  );
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  mount(<CreateProject />);
  fireEvent.change(screen.getByLabelText("Hoặc chọn video"), {
    target: { files: [new File(["fixture"], "fixture.mp4")] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Tiếp tục" }));
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Upload & tạo dự án" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Upload & tạo dự án" }));
  await screen.findByRole("button", { name: "Hủy upload" });
  fireEvent.click(screen.getByRole("link", { name: "Về thư viện" }));
  expect(confirm).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Hủy upload" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Đã hủy chờ upload",
  );
  expect(vi.mocked(api.uploadProject).mock.calls[0][3].aborted).toBe(true);
  confirm.mockRestore();
});
