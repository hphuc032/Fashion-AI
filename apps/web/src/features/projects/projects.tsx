"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  API_BASE,
  ApiError,
  readProject,
  readProjects,
  readStorage,
  uploadProject,
  updateProject,
  type Project,
  type SourceMetadata,
} from "@/lib/api-client";
import { Button } from "@/components/ui/button";

export const projectKeys = {
  all: ["projects"] as const,
  page: (search: string, cursor?: string) =>
    ["projects", "page", search, cursor ?? ""] as const,
  detail: (id: string) => ["projects", "detail", id] as const,
};
const bytes = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MiB`;
const date = (s: string) => new Date(s).toLocaleString("vi-VN");
export function Failure({ error }: { error: unknown }) {
  const code = error instanceof ApiError ? error.code : "REQUEST_REJECTED";
  const messages: Record<string, string> = {
    PROFILE_REQUIRED:
      "Chưa cấu hình database và kho video. Hãy chọn profile trong cấu hình khởi động.",
    PROFILE_UNAVAILABLE: "Profile đã cấu hình không truy cập được.",
    SESSION_REQUIRED: "Phiên đã hết hạn. Mở liên kết khởi động mới.",
    OFFLINE: "Không kết nối được API cục bộ.",
    ABORTED:
      "Đã hủy chờ upload. Nếu server đã nhận đủ video, dự án có thể đã được lưu; kiểm tra thư viện hoặc thử lại cùng yêu cầu.",
    UPLOAD_TOO_LARGE: "Video vượt giới hạn dung lượng.",
    VALIDATION_ERROR:
      "Video hoặc metadata không hợp lệ. Kiểm tra định dạng, thời lượng và quyền sử dụng.",
    INSUFFICIENT_STORAGE: "Không đủ dung lượng trống.",
    UNSUPPORTED_MEDIA: "Chỉ hỗ trợ video MP4, MOV hoặc MKV hợp lệ.",
    REVISION_CONFLICT: "Dự án đã thay đổi. Tải lại trước khi lưu.",
    IDEMPOTENCY_CONFLICT:
      "Yêu cầu trước đã lưu nội dung khác. Kiểm tra thư viện trước khi tạo yêu cầu mới.",
    IMPORT_BUSY: "Đang có upload khác. Đợi và thử lại.",
    TIMEOUT: "Hết thời gian chờ. Kiểm tra thư viện rồi thử lại cùng yêu cầu.",
  };
  return (
    <p role="alert" className="project-error">
      {messages[code] ?? `Không hoàn tất yêu cầu (${code}).`}
    </p>
  );
}
function Cards({ items }: { items: Project[] }) {
  return (
    <div className="project-grid">
      {items.map((p) => (
        <Link
          className="panel project-card"
          href={`/projects/${p.id}`}
          key={p.id}
        >
          <span className="eyebrow">
            {p.status} · {p.processing_status}
          </span>
          <h2>{p.original_filename}</h2>
          <p>
            {p.duration.toFixed(1)} giây · {bytes(p.file_size)} · {p.width} ×{" "}
            {p.height}
          </p>
          <small>{date(p.created_at)}</small>
          {p.creator_name && <p>{p.creator_name}</p>}
        </Link>
      ))}
    </div>
  );
}
export function ProjectLibrary() {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];
  const q = useQuery({
    queryKey: projectKeys.page(search, cursor),
    queryFn: ({ signal }) => readProjects(search, cursor, signal),
  });
  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">THƯ VIỆN CỤC BỘ</span>
          <h1>Dự án video</h1>
          <p>Video gốc và thông tin nguồn trong profile đã chọn.</p>
        </div>
        <Link className="button" href="/projects/new">
          Tạo dự án
        </Link>
      </div>
      <form
        className="project-search"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(input);
          setCursors([undefined]);
        }}
      >
        <label htmlFor="project-search">Tên video hoặc tác giả</label>
        <input
          id="project-search"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={255}
        />
        <Button type="submit">Tìm kiếm</Button>
      </form>
      <p>Sắp xếp: mới nhất trước</p>
      {q.isPending ? (
        <p role="status">Đang tải dự án…</p>
      ) : q.isError ? (
        <Failure error={q.error} />
      ) : (
        <>
          <p>{q.data.total} dự án phù hợp</p>
          {q.data.items.length ? (
            <Cards items={q.data.items} />
          ) : (
            <section className="panel">
              <h2>Chưa có dự án phù hợp</h2>
              <p>Chọn video được phép sử dụng để tạo dự án đầu tiên.</p>
            </section>
          )}
          <div className="project-actions">
            <Button
              disabled={cursors.length === 1}
              onClick={() => setCursors((c) => c.slice(0, -1))}
            >
              Trang trước
            </Button>
            <span>Trang {cursors.length}</span>
            <Button
              disabled={!q.data.next_cursor}
              onClick={() => setCursors((c) => [...c, q.data.next_cursor!])}
            >
              Trang tiếp
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
export function ProjectOverview() {
  const q = useQuery({
    queryKey: projectKeys.page(""),
    queryFn: ({ signal }) => readProjects("", undefined, signal),
  });
  const storage = useQuery({
    queryKey: ["storage"],
    queryFn: ({ signal }) => readStorage(signal),
  });
  return (
    <section className="panel project-overview">
      <div className="panel-heading">
        <h2>Dự án & kho video</h2>
        <Link href="/projects/new">Tạo dự án</Link>
      </div>
      {q.isPending ? (
        <p>Đang đọc dữ liệu dự án…</p>
      ) : q.isError ? (
        <Failure error={q.error} />
      ) : (
        <>
          <p>
            <strong>{q.data.total}</strong> dự án ·{" "}
            <strong>{q.data.completed ?? "Chưa có dữ liệu"}</strong> đã có bản
            xuất
          </p>
          {q.data.items.length ? (
            <>
              <h3>Dự án gần đây</h3>
              <ul>
                {q.data.items.slice(0, 4).map((p) => (
                  <li key={p.id}>
                    <Link href={`/projects/${p.id}`}>
                      {p.original_filename}
                    </Link>{" "}
                    · {p.status} / {p.processing_status} · {date(p.updated_at)}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p>Chưa có dự án. Nhập video đầu tiên để bắt đầu.</p>
          )}
        </>
      )}
      {storage.isError ? (
        <Failure error={storage.error} />
      ) : storage.data ? (
        <p>
          Kho video:{" "}
          {storage.data.ready ? "Sẵn sàng" : "Cần cấu hình hoặc kiểm tra"} ·
          Giới hạn {bytes(storage.data.max_upload_bytes)} /{" "}
          {storage.data.max_video_seconds} giây
          {storage.data.disk_free_bytes !== null
            ? ` · Trống ${bytes(storage.data.disk_free_bytes)}`
            : ""}
        </p>
      ) : (
        <p>Đang kiểm tra kho video…</p>
      )}
    </section>
  );
}
function MetadataFields({
  value,
  change,
}: {
  value: SourceMetadata;
  change: (v: SourceMetadata) => void;
}) {
  return (
    <div className="project-fields">
      <label>
        URL nguồn (chỉ lưu thông tin)
        <input
          type="url"
          value={value.source_url ?? ""}
          maxLength={2048}
          onChange={(e) =>
            change({ ...value, source_url: e.target.value || null })
          }
        />
      </label>
      <label>
        Tác giả
        <input
          value={value.creator_name ?? ""}
          maxLength={255}
          onChange={(e) =>
            change({ ...value, creator_name: e.target.value || null })
          }
        />
      </label>
      <label>
        Quyền sử dụng
        <select
          aria-label="Quyền sử dụng"
          value={value.rights_status}
          onChange={(e) =>
            change({
              ...value,
              rights_status: e.target.value as SourceMetadata["rights_status"],
            })
          }
        >
          <option value="unknown">Chưa rõ</option>
          <option value="owned">Sở hữu</option>
          <option value="licensed">Được cấp phép</option>
          <option value="permission_granted">Đã được cho phép</option>
        </select>
      </label>
      <label>
        Ghi chú quyền sử dụng
        <textarea
          value={value.rights_notes ?? ""}
          maxLength={4000}
          onChange={(e) =>
            change({ ...value, rights_notes: e.target.value || null })
          }
        />
      </label>
    </div>
  );
}
export function CreateProject() {
  const router = useRouter();
  const cache = useQueryClient();
  const [file, setFile] = useState<File>();
  const [url, setUrl] = useState("");
  const [step, setStep] = useState(1);
  const [metadata, setMetadata] = useState<SourceMetadata>({
    rights_status: "unknown",
  });
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<unknown>();
  const [preview, setPreview] = useState("");
  const key = useRef("");
  const controller = useRef<AbortController | null>(null);
  const [drag, setDrag] = useState(false);
  const storage = useQuery({
    queryKey: ["storage"],
    queryFn: ({ signal }) => readStorage(signal),
  });
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    const leave = (e: MouseEvent) => {
      const anchor =
        e.target instanceof Element ? e.target.closest("a[href]") : null;
      if (
        anchor &&
        !window.confirm("Upload đang chạy. Rời trang và hủy chờ?")
      ) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", leave, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", leave, true);
    };
  }, [busy]);
  useEffect(() => () => controller.current?.abort(), []);
  function choose(f?: File) {
    if (!f || busy) return;
    if (
      !/\.(mp4|mov|mkv)$/i.test(f.name) ||
      !f.size ||
      f.size > (storage.data?.max_upload_bytes ?? 500 * 1024 * 1024)
    ) {
      setError(new ApiError("VALIDATION_ERROR"));
      return;
    }
    setFile(f);
    setUrl(URL.createObjectURL(f));
    key.current = crypto.randomUUID();
    setError(undefined);
    setStep(2);
  }
  async function submit() {
    if (!file || busy || !confirmed) return;
    setBusy(true);
    setProgress(0);
    setError(undefined);
    setStep(4);
    controller.current = new AbortController();
    try {
      const project = await uploadProject(
        file,
        metadata,
        key.current,
        controller.current.signal,
        setProgress,
      );
      cache.setQueryData(projectKeys.detail(project.id), project);
      await cache.invalidateQueries({ queryKey: projectKeys.all });
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">NHẬP VIDEO · W2</span>
          <h1>Tạo dự án</h1>
          <p>Chọn video trên máy. URL nguồn không được tự tải xuống.</p>
        </div>
      </div>
      <ol className="project-steps">
        {["Chọn video", "Xem trước", "Nguồn & quyền", "Upload", "Mở dự án"].map(
          (s, i) => (
            <li key={s} aria-current={step === i + 1 ? "step" : undefined}>
              {i + 1}. {s}
            </li>
          ),
        )}
      </ol>
      {storage.data && !storage.data.ready && (
        <p role="alert">
          Kho video chưa sẵn sàng. Cấu hình profile trước khi upload.
        </p>
      )}
      <section className="panel project-editor">
        {step === 1 ? (
          <div
            className={`drop-zone ${drag ? "drag-active" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              choose(e.dataTransfer.files[0]);
            }}
          >
            <h2>Kéo video vào đây</h2>
            <label>
              Hoặc chọn video
              <input
                type="file"
                accept=".mp4,.mov,.mkv"
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </label>
            <p>
              MP4, MOV, MKV · Tối đa{" "}
              {bytes(storage.data?.max_upload_bytes ?? 500 * 1024 * 1024)} /{" "}
              {storage.data?.max_video_seconds ?? 180} giây
            </p>
          </div>
        ) : (
          <>
            <h2>{file?.name}</h2>
            {step === 2 && (
              <>
                <video
                  className="project-video"
                  controls
                  src={url}
                  onLoadedMetadata={(e) => {
                    const v = e.currentTarget;
                    setPreview(
                      `${v.duration.toFixed(1)} giây · ${v.videoWidth} × ${v.videoHeight}`,
                    );
                  }}
                  onError={() =>
                    setPreview(
                      "Trình duyệt không xem trước được định dạng này. Server sẽ kiểm tra bằng FFprobe.",
                    )
                  }
                />
                <p>
                  {file && bytes(file.size)} · {preview}
                </p>
                <p>
                  Thông tin xem trước từ trình duyệt; metadata chính thức được
                  kiểm tra ở server.
                </p>
                <div className="project-actions">
                  <Button onClick={() => setStep(1)}>Chọn lại</Button>
                  <Button onClick={() => setStep(3)}>Tiếp tục</Button>
                </div>
              </>
            )}
            {step === 3 && (
              <>
                <MetadataFields value={metadata} change={setMetadata} />
                <label>
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />{" "}
                  Tôi xác nhận trạng thái quyền ở trên và được phép tải video
                  này lên kho cục bộ.
                </label>
                <div className="project-actions">
                  <Button onClick={() => setStep(2)}>Quay lại</Button>
                  <Button
                    disabled={!confirmed || !storage.data?.ready}
                    onClick={submit}
                  >
                    Upload & tạo dự án
                  </Button>
                </div>
              </>
            )}
            {step === 4 && (
              <>
                <label htmlFor="upload-progress">
                  {progress < 100
                    ? `Đang tải ${progress}%`
                    : "Đã gửi video · Đang kiểm tra và lưu"}
                </label>
                <progress id="upload-progress" max={100} value={progress} />
                {busy ? (
                  <Button onClick={() => controller.current?.abort()}>
                    Hủy upload
                  </Button>
                ) : (
                  <Button onClick={submit}>Thử lại cùng yêu cầu</Button>
                )}
                <p>
                  Nếu đã gửi đủ video, việc hủy chờ không xóa dự án đã lưu. Thử
                  lại giữ nguyên mã yêu cầu để tránh tạo trùng.
                </p>
              </>
            )}
          </>
        )}
        {error !== undefined && <Failure error={error} />}
      </section>
      <Link href="/projects">Về thư viện</Link>
    </div>
  );
}
export function ProjectDetail({ id }: { id: string }) {
  const cache = useQueryClient();
  const q = useQuery({
    queryKey: projectKeys.detail(id),
    queryFn: ({ signal }) => readProject(id, signal),
  });
  const [editing, setEditing] = useState(false);
  const [metadata, setMetadata] = useState<SourceMetadata>({
    rights_status: "unknown",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [videoError, setVideoError] = useState(false);
  const [loading, setLoading] = useState(true);
  if (q.isPending)
    return (
      <div className="dashboard" role="status">
        Đang tải dự án…
      </div>
    );
  if (q.isError)
    return (
      <div className="dashboard">
        <Failure error={q.error} />
      </div>
    );
  const p = q.data;
  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      const updated = await updateProject(p, metadata);
      cache.setQueryData(projectKeys.detail(id), updated);
      await cache.invalidateQueries({ queryKey: projectKeys.all });
      setEditing(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            VIDEO GỐC · {p.status} · {p.processing_status}
          </span>
          <h1>{p.original_filename}</h1>
          <p>
            Tạo {date(p.created_at)} · Cập nhật {date(p.updated_at)}
          </p>
        </div>
        <Link href="/projects">Thư viện</Link>
      </div>
      <section className="panel project-editor">
        {loading && !videoError && <p role="status">Đang tải video…</p>}
        <video
          className="project-video"
          controls
          preload="metadata"
          crossOrigin="use-credentials"
          src={`${API_BASE}/projects/${p.id}/source`}
          onLoadedMetadata={() => setLoading(false)}
          onError={() => {
            setVideoError(true);
            setLoading(false);
          }}
        />
        {videoError && (
          <p role="alert">
            Không phát được video. Kiểm tra phiên, file nguồn hoặc codec trình
            duyệt; MP4 H.264 được hỗ trợ rộng rãi hơn.
          </p>
        )}
        <dl className="project-metadata">
          {Object.entries({
            "Dung lượng": bytes(p.file_size),
            "Thời lượng": `${p.duration.toFixed(2)} giây`,
            "Kích thước": `${p.width} × ${p.height}`,
            FPS: p.fps,
            "Video codec": p.video_codec,
            "Audio codec": p.audio_codec ?? "Không có",
            "Tỷ lệ": p.aspect_ratio,
            "Tác giả": p.creator_name ?? "—",
            Quyền: p.rights_status,
            "Ghi chú": p.rights_notes ?? "—",
            "URL nguồn": p.source_url ?? "—",
          }).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        {editing ? (
          <>
            <MetadataFields value={metadata} change={setMetadata} />
            <Button disabled={busy} onClick={save}>
              Lưu metadata
            </Button>
            <Button disabled={busy} onClick={() => setEditing(false)}>
              Đóng
            </Button>
          </>
        ) : (
          <Button
            onClick={() => {
              setMetadata({
                source_url: p.source_url,
                creator_name: p.creator_name,
                rights_status: p.rights_status,
                rights_notes: p.rights_notes,
              });
              setEditing(true);
            }}
          >
            Sửa thông tin nguồn
          </Button>
        )}
        {error !== undefined && (
          <>
            <Failure error={error} />
            <Button
              onClick={() => {
                setEditing(false);
                q.refetch();
              }}
            >
              Tải lại dự án
            </Button>
          </>
        )}
      </section>
      <section className="panel">
        <h2>Các bước tiếp theo</h2>
        <ul>
          {[
            "OCR & Translation — W3",
            "Video Text Editor — W4",
            "AI Dubbing — W5",
            "Final Rendering — W6",
          ].map((s) => (
            <li key={s}>{s} · Chưa khả dụng</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
