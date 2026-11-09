"use client";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  CircleHelp,
  Cpu,
  Database,
  Film,
  Languages,
  LockKeyhole,
  RefreshCw,
  Server,
  ShieldCheck,
  Subtitles,
  Workflow,
  X,
} from "lucide-react";
import { readDashboard, ApiError, revokeSession } from "@/lib/api-client";
import { Button } from "@/components/ui/button";

const stages = [
  { title: "Nhập video", text: "Quản lý dự án", icon: Film, milestone: "W2" },
  {
    title: "OCR & bản dịch",
    text: "Nhận diện và duyệt",
    icon: Languages,
    milestone: "W3",
  },
  {
    title: "Thay chữ",
    text: "Xem trước & xử lý",
    icon: Workflow,
    milestone: "W4",
  },
  {
    title: "Lồng tiếng",
    text: "Giọng Việt & đồng bộ",
    icon: AudioLines,
    milestone: "W5",
  },
  {
    title: "Xuất video",
    text: "Phụ đề & MP4",
    icon: Subtitles,
    milestone: "W6",
  },
];
function State({
  available,
  unknown = false,
}: {
  available: boolean;
  unknown?: boolean;
}) {
  return (
    <span
      className={`state ${unknown ? "state-unknown" : available ? "state-ok" : "state-warn"}`}
    >
      {unknown ? (
        <CircleHelp size={13} />
      ) : available ? (
        <Check size={13} />
      ) : (
        <X size={13} />
      )}
      {unknown ? "Chưa kiểm tra" : available ? "Khả dụng" : "Chưa tìm thấy"}
    </span>
  );
}
export function Dashboard() {
  const query = useQuery({
    queryKey: ["system"],
    queryFn: ({ signal }) => readDashboard(signal),
    refetchInterval: 30000,
  });
  const health = query.data?.health,
    status = query.data?.status;
  const online = Boolean(health) && !query.isError;
  const sessionError =
    query.error instanceof ApiError && query.error.status === 401;
  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FASHION AI / LOCAL STUDIO</span>
          <h1>
            Không gian sáng tạo của bạn<span className="heading-dot">.</span>
          </h1>
          <p>Nền tảng Web cho quy trình bản địa hóa video thời trang.</p>
        </div>
        <Button onClick={() => query.refetch()} disabled={query.isFetching}>
          <RefreshCw size={15} className={query.isFetching ? "spin" : ""} />
          {query.isFetching ? "Đang kiểm tra" : "Kiểm tra lại"}
        </Button>
      </div>
      <section
        className={`connection-banner ${query.isError ? "banner-error" : ""}`}
        aria-live="polite"
        aria-label="Kết nối backend"
      >
        <div className="connection-icon">
          <Server size={23} />
        </div>
        <div>
          <div className="connection-title">
            <span className={`status-dot ${online ? "online" : ""}`} />
            {query.isPending
              ? "Đang kết nối API cục bộ…"
              : online
                ? "Backend đang online"
                : sessionError
                  ? "Cần mở liên kết khởi động mới"
                  : "Chưa kết nối được backend"}
          </div>
          <p>
            {query.isPending
              ? "Đang xác thực phiên và đọc trạng thái thực tế từ FastAPI."
              : online
                ? `API ${health?.api_version} · Chỉ loopback · Cập nhật mỗi 30 giây`
                : sessionError
                  ? "Phiên chưa có hoặc đã hết hạn. Khởi động lại Web runtime để mở liên kết có hiệu lực."
                  : "Kiểm tra Web runtime rồi chọn Kiểm tra lại. Không hiển thị dữ liệu cũ như trạng thái hiện tại."}
          </p>
        </div>
        <span className="banner-tag">
          WEB FOUNDATION <b>W1</b>
        </span>
      </section>
      <div className="section-heading">
        <h2>Tình trạng hệ thống</h2>
        <span>
          <Activity size={14} /> Dữ liệu trực tiếp từ Local API
        </span>
      </div>
      <div className="status-grid">
        <article className="status-card">
          <span className="card-icon cyan">
            <Cpu size={21} />
          </span>
          <span className="card-overline">LOCAL API</span>
          <h3>
            {query.isPending
              ? "Đang kiểm tra"
              : online
                ? "Đã kết nối"
                : "Chưa kết nối"}
          </h3>
          <p>
            {online
              ? `Phiên bản ${health?.api_version} · Chạy trên máy này`
              : "Cần phiên cục bộ hợp lệ"}
          </p>
          <div className="card-foot">
            <span className="subtle-dot" />
            {online ? "Kết nối được xác thực" : "Chưa có trạng thái xác thực"}
          </div>
        </article>
        <article className="status-card">
          <span className="card-icon violet">
            <Film size={21} />
          </span>
          <span className="card-overline">MEDIA TOOLS</span>
          <h3>
            {online
              ? status?.readiness === "ready"
                ? "Công cụ khả dụng"
                : "Cần kiểm tra công cụ"
              : "Chưa kiểm tra"}
          </h3>
          <p>FFmpeg, FFprobe và bộ lọc phụ đề</p>
          <div className="card-foot">
            {online ? "Chỉ kiểm tra công cụ, chưa render" : "Đang chờ backend"}
          </div>
        </article>
        <article className="status-card">
          <span className="card-icon amber">
            <Database size={21} />
          </span>
          <span className="card-overline">DATABASE & MODELS</span>
          <h3>
            {online && status?.database.configured
              ? "Đã khai báo DB"
              : online
                ? "Chưa chọn database"
                : "Chưa kiểm tra"}
          </h3>
          <p>Schema và model chưa được kiểm tra</p>
          <div className="card-foot">
            <LockKeyhole size={13} /> Không mở DB · Không nạp model
          </div>
        </article>
      </div>
      <div className="detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Kiểm tra môi trường</h2>
              <p>Khả dụng của công cụ không đồng nghĩa AI đã sẵn sàng.</p>
            </div>
            <span className="small-icon">
              <Activity size={18} />
            </span>
          </div>
          <div className="tool-list">
            {[
              {
                name: "FFmpeg",
                detail: "Công cụ xử lý media",
                available: status?.tools.ffmpeg,
              },
              {
                name: "FFprobe",
                detail: "Kiểm tra metadata video",
                available: status?.tools.ffprobe,
              },
              {
                name: "Phụ đề ASS",
                detail: "Bộ lọc libass / subtitles",
                available: status?.tools.subtitles === "available",
              },
            ].map((tool) => (
              <div className="tool-row" key={tool.name}>
                <span className="tool-symbol">
                  <ChevronRight size={16} />
                </span>
                <div>
                  <strong>{tool.name}</strong>
                  <small>{tool.detail}</small>
                </div>
                <State available={Boolean(tool.available)} unknown={!online} />
              </div>
            ))}
            <div className="tool-row">
              <span className="tool-symbol">
                <Cpu size={16} />
              </span>
              <div>
                <strong>Model AI</strong>
                <small>Chưa kiểm tra tệp hoặc chạy inference</small>
              </div>
              <State available={false} unknown />
            </div>
            <div className="tool-row">
              <span className="tool-symbol">
                <Database size={16} />
              </span>
              <div>
                <strong>Schema database</strong>
                <small data-testid="schema-status">
                  {online
                    ? status?.database.schema_status
                    : "Chưa nhận trạng thái"}
                </small>
              </div>
              <State available={false} unknown />
            </div>
          </div>
        </section>
        <section className="panel intro-panel">
          <span className="eyebrow">MỘT KHÔNG GIAN MỚI</span>
          <h2>
            Trải nghiệm Web.
            <br />
            Engine AI hiện có.
          </h2>
          <p>
            Giao diện mới sẽ kết nối từng bước với quy trình Python đã có. Bản
            W1 tập trung vào nền tảng và kết nối an toàn.
          </p>
          <div className="preservation">
            <ShieldCheck size={20} />
            <div>
              <strong>Dữ liệu hiện tại được giữ nguyên</strong>
              <span>
                Không chọn kho dữ liệu, tải model hoặc thay đổi dự án ở giai
                đoạn này.
              </span>
            </div>
          </div>
          <div className="intro-bottom">
            <span className="release-label">W1 / NỀN TẢNG</span>
            <span>
              Đang phát triển <ArrowRight size={15} />
            </span>
          </div>
        </section>
      </div>
      <section className="workflow-section">
        <div className="section-heading">
          <h2>Quy trình sắp được kết nối</h2>
          <span>Chưa khả dụng trong W1</span>
        </div>
        <div className="workflow-grid">
          {stages.map(({ title, text, icon: Icon, milestone }, i) => (
            <article className="workflow-card" key={title}>
              <div className="workflow-top">
                <span>{String(i + 1).padStart(2, "0")}</span>
                <LockKeyhole size={13} />
              </div>
              <Icon size={21} />
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="milestone">{milestone} · Sắp có</span>
            </article>
          ))}
        </div>
      </section>
      <footer className="dashboard-footer">
        <span>
          <ShieldCheck size={13} />
          Local-first · Không có tác vụ AI chạy từ trang này
        </span>
        {online && (
          <button
            className="text-link"
            onClick={async () => {
              await revokeSession();
              await query.refetch();
            }}
          >
            Kết thúc phiên
          </button>
        )}
      </footer>
    </div>
  );
}
