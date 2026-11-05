# Fashion AI Localizer — M0

Ứng dụng Windows chạy cục bộ: nhập MP4/MOV/MKV, kiểm tra bằng FFprobe, lưu bản gốc và metadata SQLite, xem trước và mở lại dự án. Giao diện tiếng Việt, giao diện tối, không cần tài khoản hoặc API trả phí. Chỉ triển khai M0; chưa có OCR, dịch, lồng tiếng, phụ đề hay xuất video đã xử lý.

## Cài đặt (PowerShell)

Cần Python 3.11 x64 và FFmpeg/FFprobe. Nếu chưa có:

```powershell
winget install --id Python.Python.3.11 --exact
winget install --id Gyan.FFmpeg --exact
```

Mở PowerShell mới sau khi cài để PATH được cập nhật. Từ thư mục dự án:

```powershell
Set-Location 'D:\tiktok\Fashion-AI'
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
ffmpeg -version
ffprobe -version
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Mở http://127.0.0.1:8501. Không cần activate venv. Không ghi đè `.env` đã có; chỉ sao chép lần đầu.

Trên máy hiện tại đã chuẩn bị Python 3.11.18 riêng trong `.venv311` và FFmpeg portable trong `.tools`; `.env` đã cấu hình đường dẫn. Để chạy lại bản đã kiểm chứng, dùng `.\.venv311\Scripts\python.exe -m streamlit run app/main.py`. Không cần cài lại. Môi trường `.venv` là môi trường thử ban đầu dùng Python 3.14, không phải môi trường nghiệm thu.

## Sử dụng

1. Chọn **Tải video**, chọn tệp local, bổ sung URL nguồn/tác giả/quyền sử dụng nếu có.
2. Nhấn **Lưu video**. Ứng dụng kiểm tra tệp, lưu bản gốc và tạo dự án UUID. Lỗi được hiển thị bằng tiếng Việt.
3. Chọn dự án ở **Video gần đây** hoặc **Thư viện**, xem metadata và video. MP4 H.264/AAC là lựa chọn phù hợp cho trình duyệt; MOV/MKV và codec khác có thể phải mở bằng trình phát trên máy. M0 không chuyển mã.
4. Đóng và mở lại ứng dụng: dữ liệu vẫn ở SQLite và thư mục storage. Không di chuyển/xóa riêng tệp media khi đang sử dụng.

Thông tin quyền ở M0 là bản ghi do người dùng cung cấp, chưa phải xác nhận quyền xuất bản. Việc có tệp không chứng minh quyền đăng lại.

## Cấu hình

Xem `.env.example`. Biến môi trường có ưu tiên hơn `.env`; đường dẫn tương đối tính từ thư mục dự án. `STORAGE_ROOT` là nơi chứa media; `DATABASE_URL` là đường dẫn SQLite độc lập (nếu đổi storage, cần đổi cả DB khi muốn di chuyển toàn bộ). Không đặt DB/media ở thư mục công khai. Mặc định 500 MiB và 180 giây; đây là giới hạn ứng dụng, không phải quy định TikTok.

`FFPROBE_PATH` và `FFMPEG_PATH` có thể là tên trên PATH hoặc đường dẫn đầy đủ trong `.env` riêng. FFmpeg dùng để tạo fixture; FFprobe dùng khi nhập video. Thiếu FFprobe sẽ báo hướng dẫn và từ chối nhập, không giả lập kết quả. Lỗi quá 30 giây sẽ được dừng.

Nếu thay `MAX_UPLOAD_SIZE_MB`, đồng thời đổi `server.maxUploadSize` trong `.streamlit/config.toml` rồi khởi động lại. Streamlit nhận upload vào RAM trước khi service sao chép theo khối 1 MiB; cân nhắc RAM khi tăng giới hạn. Không mở ứng dụng ra Internet; thiết kế cho một người dùng local.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/generate_test_video.py
```

Fixture tổng hợp ở `storage/temp/synthetic.mp4`; có thể tải lên giao diện để thử. Test tích hợp thật tự skip nếu thiếu FFmpeg/FFprobe. Test unit dùng mock chỉ kiểm tra luồng tương ứng, không chứng minh giải mã video thực.

## Cấu trúc và giới hạn

```text
app/main.py                  Entry point Streamlit
app/core/                    Settings, logging JSON
app/database/                SQLAlchemy models, SQLite sessions
app/services/                FFprobe, bounded local import, recent projects
app/ui/                      Dashboard, form, metadata and preview
app/utils/                   Validation and user-facing errors
tests/                       Unit, service integration, Streamlit AppTest
scripts/generate_test_video.py
docs/                        Plan, actual verification log, acceptance report
storage/projects/<UUID>/source/<UUID>.<ext>
```

Không sửa video gốc. DB lưu đường dẫn tương đối và metadata, không lưu BLOB video. Tên tệp người dùng chỉ lưu để hiển thị; đường dẫn dùng UUID. Một token duy nhất cho mỗi lần gửi form tránh lưu lặp khi retry/rerun; cố ý tải cùng tệp lần khác tạo dự án mới. Lỗi validation/DB xóa bản sao của lần nhập lỗi; mất điện có thể để lại tệp mồ côi, không tự dọn dữ liệu người dùng. FFprobe kiểm tra container/metadata, không giải mã kiểm tra mọi frame; tệp có lỗi sâu vẫn có thể vượt qua bước nhập. Chưa có migrations cho schema tương lai.

Dependencies ghim ở `requirements.txt`; metadata hỗ trợ Python được kiểm tra trên [Streamlit PyPI](https://pypi.org/project/streamlit/) và [pytest PyPI](https://pypi.org/project/pytest/). Python dependencies dùng giấy phép Apache/MIT/BSD theo từng gói; FFmpeg có LGPL/GPL tùy bản build, xem giấy phép kèm bản phân phối. Bản Windows portable từ gyan.dev được liên kết bởi [FFmpeg download](https://ffmpeg.org/download.html).

Kết quả thực tế và các mục chưa kiểm chứng: xem `docs/IMPLEMENTATION_LOG.md` và `docs/M0_ACCEPTANCE.md`.

Quy trình Git: xem `docs/GIT_WORKFLOW.md`. M0 đã được chủ dự án phê duyệt; [PR #1](https://github.com/hphuc032/Fashion-AI/pull/1) đã qua CI và merge vào `develop`. Bản tích hợp `main` là mục tiêu của tag chú thích `v0.1.0` đã được cho phép. Giữ nhánh `feature/m0-foundation`; chỉ bắt đầu M1 khi có phê duyệt riêng. Chi tiết kiểm chứng và phát hành nằm trong `docs/IMPLEMENTATION_LOG.md`.
