import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Dashboard } from "./dashboard";
import * as api from "@/lib/api-client";
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof api>()),
  readDashboard: vi.fn(),
}));
function renderDashboard() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Dashboard />
    </QueryClientProvider>,
  );
}
it("shows real DTO state and keeps AI explicitly uninspected", async () => {
  vi.mocked(api.readDashboard).mockResolvedValue({
    health: { status: "ok", api_version: "v1", instance_id: "test" },
    status: {
      api_version: "v1",
      local_only: true,
      readiness: "degraded",
      tools: { ffmpeg: false, ffprobe: false, subtitles: "unavailable" },
      database: { configured: false, schema_status: "not_inspected" },
      models: "not_inspected",
    },
  });
  renderDashboard();
  expect(await screen.findByText("Backend đang online")).toBeInTheDocument();
  expect(screen.getByTestId("schema-status")).toHaveTextContent(
    "not_inspected",
  );
  expect(screen.getByText("Chưa khả dụng trong W1")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /OCR|render|tải video/i }),
  ).not.toBeInTheDocument();
});
it("shows offline state instead of fabricated healthy status", async () => {
  vi.mocked(api.readDashboard).mockRejectedValue(new api.ApiError("OFFLINE"));
  renderDashboard();
  expect(
    await screen.findByText("Chưa kết nối được backend"),
  ).toBeInTheDocument();
});
it("renders honest loading state", () => {
  vi.mocked(api.readDashboard).mockReturnValue(new Promise(() => {}));
  renderDashboard();
  expect(screen.getByText("Đang kết nối API cục bộ…")).toBeInTheDocument();
});
