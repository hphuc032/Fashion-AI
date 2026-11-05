# Fashion AI Localizer — M0 + M1

## Smart Auto Review (feature branch)

Trong Nhận diện & Dịch, chọn Thủ công (mặc định), Smart Auto Review (khuyên dùng), hoặc Auto Approve All. Smart đánh giá OCR và bản dịch độc lập; chỉ cụm khớp chính xác thuật ngữ đã kiểm chứng mới có đủ bằng chứng để tự duyệt. Câu neural chưa xác định được nghĩa vẫn cần kiểm tra dù OCR=1.000. Điểm là heuristic, không phải xác suất đúng.

Có duyệt các đoạn đã chọn / cả trang (tối đa 100) kèm xác nhận, chuyển về chờ duyệt, lọc cần kiểm tra và số liệu từng nhóm. Đoạn bị loại không tự được duyệt lại; chuyển về chờ duyệt trước. Sửa nội dung đã duyệt sẽ hủy duyệt cũ. Các thao tác có audit, hash nội dung và thời gian; rerun không tự lặp thao tác. Giá/số/kích thước, tên thương hiệu, chữ Trung còn sót, câu lặp, lỗi provider và claim đáng ngờ đều ngăn Smart tự duyệt. Tắt kiểm tra nghĩa không cho phép duyệt chỉ bằng OCR.

Migration review phiên bản 20 chỉ thêm bảng trạng thái/audit, có backup SQLite; trạng thái cũ pending/approved/rejected vẫn được giữ cho M1 và M2. AUTO_APPROVED và MANUALLY_APPROVED cùng ánh xạ approved. Không gọi API ngoài. Cấu hình AUTO_REVIEW_* trong .env.example. Chạy bằng `.\.venv-m1-clean\Scripts\python.exe -m streamlit run app/main.py`; test đầy đủ với M1_RUN_REAL=1. Chi tiết: docs/SMART_AUTO_REVIEW_PLAN.md.

Ứng dụng Windows chạy cục bộ: nhập MP4/MOV/MKV, giữ bản gốc, lưu SQLite, nhận diện chữ Trung bằng PaddleOCR, gom caption, dịch Việt offline và sửa/duyệt từng đoạn. Giao diện tiếng Việt, không cần tài khoản hoặc API trả phí. M0 đã được duyệt/phát hành v0.1.0; M1 nằm trên nhánh feature để review. Chưa xóa chữ, chèn chữ vào video, nhận diện giọng nói, lồng tiếng, phụ đề hay xuất video đã xử lý.

## Cài đặt (PowerShell)

Cần Python 3.11 x64 và FFmpeg/FFprobe. Nếu chưa có:

```powershell
winget install --id Python.Python.3.11 --exact
winget install --id Gyan.FFmpeg --exact
```

Mở PowerShell mới sau khi cài để PATH được cập nhật. Từ thư mục dự án:

```powershell
Set-Location 'D:\tiktok\Fashion-AI'
py -3.11 -m venv .venv-m1
.\.venv-m1\Scripts\python.exe -m pip install -r requirements-m1.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
ffmpeg -version
ffprobe -version
.\.venv-m1\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
.\.venv-m1\Scripts\python.exe -m streamlit run app/main.py
```

Mở http://127.0.0.1:8501. Không cần activate venv. Không ghi đè `.env` đã có; chỉ sao chép lần đầu.

Trên máy hiện tại, môi trường M1 được cài sạch và nghiệm thu là `.venv-m1-clean` (Python 3.11.18); FFmpeg portable ở `.tools` đã cấu hình trong `.env`. Dùng `.\.venv-m1-clean\Scripts\python.exe -m streamlit run app/main.py` để chạy bản đó; `.venv311` là môi trường M0. Bản demo M1 đang chạy riêng trên cổng 8502 với kho `storage/m1-demo`, dùng cùng các mô hình ở `storage/models`.

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
.\.venv-m1\Scripts\python.exe -m pytest -q
.\.venv-m1\Scripts\python.exe scripts/generate_test_video.py
```

Fixture tổng hợp ở `storage/temp/synthetic.mp4`; có thể tải lên giao diện để thử. Test tích hợp thật tự skip nếu thiếu FFmpeg/FFprobe. Test unit dùng mock chỉ kiểm tra luồng tương ứng, không chứng minh giải mã video thực.

## Nhận diện và dịch (M1)

1. Nhập video như M0, chọn **Nhận diện & Dịch**, chọn dự án và khoảng lấy mẫu (mặc định 1 giây). Nhấn **Chạy OCR**. Một worker riêng chạy nền; tiến độ được lưu SQLite, refresh trang không tạo lại tác vụ.
2. Trạng thái tự cập nhật mỗi 2 giây; nhấn **Tải lại kết quả** khi hoàn tất để nạp bảng. Có thể hủy hoặc thử lại khi lỗi. Chỉ một tác vụ OCR/dịch hoạt động trên cùng DB tại một thời điểm.
3. Chọn **Argos offline**, đánh dấu các đoạn cần dịch và nhấn **Dịch các đoạn đã chọn**. OCR và dịch là hai tác vụ riêng; thiếu mô hình dịch không làm mất kết quả OCR. Mặc định `manual` không gọi mô hình dịch.
4. Sửa chữ Trung/tiếng Việt, thời gian và tọa độ nếu cần. Chọn **Chờ duyệt / Đã duyệt / Loại bỏ**, nhấn **Lưu chỉnh sửa**. Đoạn được duyệt phải có bản dịch. Để dịch lại một đoạn đã duyệt, chuyển về chờ duyệt và lưu trước. Những thay đổi đồng thời bị phát hiện qua revision, không ghi đè âm thầm.
5. Mở **Kiểm tra khung chữ OCR** để xem ảnh gốc với khung diagnostic và điểm tin cậy. Đây là ảnh kiểm tra, không phải video được thay chữ. Chữ chỉ có tiếng Anh/số và điểm OCR rất thấp vẫn có raw detection nhưng không tạo đoạn dịch tự động.

Chạy OCR lại yêu cầu xác nhận vì chỉ khi hoàn tất thành công nó mới thay các đoạn/chỉnh sửa trước đó. Lỗi hoặc hủy giữ kết quả trước. Rerun OCR là thao tác có chủ đích; dịch/lưu đồng thời được kiểm soát bằng DB và revision.

### Mô hình, tài nguyên và chất lượng

`requirements-m1.txt` ghim PaddleOCR 3.3.2, PaddlePaddle CPU 3.2.2, PaddleX 3.3.13 (ocr-core), OpenCV 4.10, CTranslate2 4.8.5 và SentencePiece 0.2.2. NumPy 1.26.4 + PyArrow 19.0.1 + pandas 3.0.6 đã kiểm chứng cho bảng review; tránh nâng riêng PyArrow lên bản đòi NumPy 2.

OCR dùng **PP-OCRv5_mobile_det + PP-OCRv5_mobile_rec**, không tải mô hình orientation/unwarping/server/VL. Script setup tải khoảng 21.8 MB hai archive OCR và 142.3 MB hai archive Argos; dung lượng giải nén đo được khoảng 187.3 MB tổng. Chỉ tải khi chạy script; ứng dụng dùng đường dẫn local và không tự tải thêm mô hình. Nguồn: [PaddleOCR 3.3 OCR API](https://github.com/PaddlePaddle/PaddleOCR/blob/release/3.3/docs/version3.x/pipeline_usage/OCR.en.md), [Argos package index](https://github.com/argosopentech/argospm-index).

Argos 1.9 chưa có gói trực tiếp zh→vi trong index đã kiểm tra; dùng **zh→en→vi** qua hai model OpenNMT/CTranslate2. Chạy trực tiếp gói Argos bằng CTranslate2/SentencePiece cho caption ngắn, không cần toàn bộ Argos library/Torch/spaCy/Stanza. Bốn cụm thời trang khớp chính xác được dịch bằng từ điển biên soạn (hiển thị rõ trong UI); các câu còn lại dùng mô hình neural. Không có dịch vụ cloud hay API key.

**Bản dịch cần được kiểm tra trước khi xuất.** Dịch qua tiếng Anh có thể sai/ngắn quá mức: thử nghiệm `这件衬衫很舒服` đã ra `Áo đẹp đấy.` và phải sửa thành `Áo sơ mi này rất thoải mái`. Mọi đầu ra tự động đều chờ duyệt; không coi confidence OCR là confidence dịch. Kiểm tra đặc biệt tên thương hiệu, mã sản phẩm, giá/kích thước/chất liệu; không dùng bản chưa duyệt để đưa ra khẳng định sản phẩm. Thử nghiệm `我喜欢这件衬衫` ra `Tôi thích cái áo này.`; đây không phải benchmark độ chính xác tổng quát.

Các cấu hình M1 ở `.env.example`: interval, cap khung, chiều dài ảnh, số pixel nguồn, confidence/similarity/IoU, CPU threads, đường dẫn model, timeout/retry và giới hạn ký tự. Mặc định CPU 2 threads, tối đa 300 mẫu, cạnh ảnh 1280, nguồn không quá 16,777,216 pixel. Chạm cap sẽ báo phần video chưa quét, không tự tăng số mẫu. `OCR_ENABLE_GPU=true` chỉ chọn thiết bị; cần tự cài Paddle GPU tương thích thay CPU, chưa được thử trên GPU.

Timestamp là mốc nguồn được yêu cầu khi lấy mẫu, không phải tracking chính xác đến từng frame; frame VFR/chuyển cảnh/ngắn hơn interval có thể cần lấy mẫu dày hơn và sửa thời gian. Khung lưu `[x,y,w,h]` theo video gốc đã xử lý hướng xoay, raw polygon vẫn được giữ. Cache ảnh gắn SHA256 của nguồn và kích thước lấy mẫu. Không gộp các caption thay số/mã sản phẩm; chữ chuyển động xa hoặc bị che có thể tách thành nhiều đoạn.

### Dữ liệu và worker

Migration phiên bản 1 chỉ thêm `schema_migrations`, `ocr_jobs`, `ocr_detections`, `text_segments`, `translation_cache`; không đổi bảng M0 `projects`. DB M0 có sẵn được sao lưu qua SQLite backup API thành `*.pre-m1-<id>.db` trước khi nâng cấp; bản sao cũng bị Git bỏ qua. Raw detections và segment lưu theo transaction. Chỉ một slot active toàn DB, có deadline/cancel và phát hiện process chết; worker có UUID khớp command line mới bị dừng. Nạp lại model một lần mỗi worker; OCR và dịch dùng process riêng để tránh xung đột DLL trên Windows và giải phóng RAM sau job. Lỗi native được cô lập khỏi Streamlit.

Kết quả dịch cache theo nội dung chuẩn hóa, context cố định cho thời trang, provider/model manifest và phiên bản từ điển. Đổi model phải cài lại bằng setup để cập nhật manifest. Log worker, model, frame, backup và ảnh minh chứng đều nằm ngoài Git. Giới hạn dung lượng nguồn/khung/timeout có kiểm soát; cache trên đĩa có thể tích lũy giữa nhiều cấu hình. Không tự xóa video, chỉnh sửa hoặc model của người dùng.

### Test mô hình thật

Sau khi cài model và FFmpeg, trên PowerShell:

```powershell
.\.venv-m1\Scripts\python.exe scripts/generate_m1_fixture.py
$env:M1_RUN_REAL='1'
# Trên Windows script dùng font msyh.ttc ở WINDIR; máy khác cần font CJK:
# $env:M1_CHINESE_FONT='duong-dan-font-CJK.ttf'
.\.venv-m1\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:M1_RUN_REAL
```

Fixture tự tạo, không kèm video Douyin. Test thật dùng supervisor/worker process như ứng dụng để OCR → dịch → sửa/duyệt → hủy rerun → mở lại DB. Không nạp Paddle và CTranslate2 liên tiếp trong cùng process Windows do xung đột DLL đã quan sát; production tách hai worker. Không bật `M1_RUN_REAL` thì đúng một test model thật được skip có lý do; CI chạy riêng 26 test M0 và 60 test M1 xác định, không tải model. Xem `docs/M1_TEST_REPORT.md` để biết chính xác những gì đã/chưa kiểm thử.

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

Quy trình Git: M0 có tag `v0.1.0` trên main. M1 đã được chủ dự án merge qua PR #2 vào approved develop `bb4b94a`. Smart Review đã được chủ dự án merge qua PR #3 vào develop `c76f4c5`; M2 đã cập nhật baseline này và kiểm chứng chung. Chỉ push nhánh M2 và tạo PR, không merge PR M2, không đổi main/tag/release và không làm M3.

## Thay chữ và xuất MP4 (M2)

Cài Python 3.11, FFmpeg/FFprobe có libx264, và dependencies M2:

```powershell
py -3.11 -m venv .venv-m2
.\.venv-m2\Scripts\python.exe -m pip install -r requirements-m2.txt
# Dùng .env hiện có; máy mới sao chép .env.example và đặt đường dẫn FFmpeg.
.\.venv-m2\Scripts\python.exe -m streamlit run app/main.py --server.address 127.0.0.1
```

M2 dùng lại dữ liệu OCR/dịch M1, không cần model inpainting mới. Muốn chạy OCR/dịch trên máy mới, cài hai bộ model theo hướng dẫn M1. Mở **Text Replacement Studio**, chọn dự án và đoạn đã duyệt, bật đoạn cần xuất và lưu cấu hình riêng. Các đoạn chưa cấu hình giữ nguyên; rejected luôn bị bỏ qua; pending chỉ được dùng khi chủ động chọn sau kiểm tra. Sửa chữ đã approved ở trang M1 sẽ đưa về pending, không giữ duyệt cũ.

Chọn **A · Mask màu / Làm mờ**, **B · OpenCV inpaint**, hoặc **C · Chỉ chèn chữ**. Có thể chỉnh khung gốc, khung chữ riêng, khoảng hiện/ẩn, font/cỡ/màu/viền/bóng/nền/căn dòng/giãn dòng/lề an toàn, padding và opacity. Bản sửa nội dung riêng cho render cần xác nhận đã kiểm tra. Không sửa OCR/bản dịch M1 khi lưu style. Chữ tự xuống dòng và giảm cỡ để vừa khung, không tự cắt nội dung; lỗi glyph, khung quá nhỏ hoặc hai bản dịch đè nhau yêu cầu chỉnh tay.

Font hệ thống Arial/Segoe UI trên Windows hoặc DejaVu Sans; không kèm font có bản quyền trong Git. Glyph tiếng Việt được kiểm tra bằng FontTools trước khi vẽ. Font mặc định trắng, viền đen, căn giữa; cỡ tự giảm theo khung. Khung gốc theo hướng hiển thị của video; tracking nội suy các detection M1 liền kề. Mẫu thưa/điểm thấp phải xem trước, chỉnh khung cố định hoặc xác nhận; không coi một khung đại diện là tracking chính xác mọi cảnh.

Nhấn **Xem frame trước / sau** sau khi lưu. Preview chỉ giải mã frame đã chọn và dùng cùng compositor với xuất video. Inpaint cơ bản có thể làm nhòe/vệt nền chuyển động hoặc phức tạp; xem kỹ các mốc cảnh. Tool chỉ dùng cho caption được phép thay. Xác nhận quyền video/âm thanh và vùng caption, cập nhật quyền nguồn hợp lệ trước **Render MP4**; dự án unknown bị chặn. Không có phát hiện/xóa watermark hay công cụ che attribution chuyên biệt.

Render chạy worker CPU riêng, tối đa một render toàn DB, có tiến độ/hủy/lịch sử SQLite. OCR/dịch và render không chạy chồng nhau. Rerun UI không khởi động lại job đang chạy; nạp lịch sử sau khi hoàn tất để xem/tải MP4. File ở `storage/projects/<project-id>/exports/`, UUID riêng cho mỗi lần; partial chỉ đổi tên sau FFprobe validation và kiểm tra nội dung duyệt không đổi. Lỗi/hủy không xóa bản gốc hoặc lần xuất trước.

Đầu ra H.264/yuv420p giữ kích thước hiển thị chẵn, tỷ lệ và FPS phân số. VFR được chuẩn hóa về average FPS hữu tỉ, giữ timeline trong sai số tối đa 0.12 giây hoặc 2 frame; không giữ cadence VFR gốc. Âm thanh đầu tiên AAC/MP3/ALAC được copy, codec khác chuyển AAC; không xuất các audio/subtitle track phụ. Không xử lý ASR/TTS/dubbing. Pipeline stream từng frame, không giữ cả video raw trong RAM.

Các biến `.env.example`: `RENDER_TIMEOUT_SECONDS=1800`, `RENDER_MAX_FRAMES=12000`, `RENDER_MAX_FPS=60`, `PREVIEW_CACHE_ENTRIES=12`; cap pixel/thời lượng nguồn dùng cấu hình M1/M0. Cache PNG preview giới hạn; frame cache M1/log/video xuất có thể tích lũy trên đĩa. Migration additive version30 tạo bản SQLite `*.pre-v30-*.db`, giữ bảng M0/M1 và tương thích review schema20, không xóa DB.

Kiểm chứng Windows CPU: **138 test pass**, gồm toàn bộ M0/M1 và M2, OCR→dịch→xuất thật, AAC packet/timestamp, VFR, FPS phân số và hướng xoay. Chạy deterministic M2: `python -m pytest tests/test_m2.py -q`. Để chạy đầy đủ model thật, bật `M1_RUN_REAL=1`, `M2_RUN_REAL=1` rồi `python -m pytest -q --tb=short`; xem lệnh PowerShell, acceptance matrix và giới hạn ở [M2_TEST_REPORT.md](docs/M2_TEST_REPORT.md).
