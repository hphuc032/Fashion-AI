# Fashion AI Localizer v1.0.0 — M0–M4

## Local Web foundation — W1

W1 adds a separate Next.js/FastAPI health workspace at `http://127.0.0.1:3000`.
It does not open/migrate a database, adopt existing storage or run AI jobs.
Projects and Settings are unavailable placeholders; the existing Streamlit
workflow below remains the working M0–M4 interface.

Use Python3.11 and Node24/npm11. Install `apps/api/requirements.lock` with
`--require-hashes` into `.venv-web`, then run `npm ci` and `npm run build`
inside `apps/web`. From repository root, run `scripts/start_web.ps1` and use
`scripts/stop_web.ps1` for owned-process shutdown. Startup never installs
dependencies/models and refuses occupied ports3000/8000.

See [W1 setup, security, verification and limitations](docs/WEB_W1_IMPLEMENTATION_REPORT.md).

## M4 — Final Export Studio

M4 nối video M2 đã hoàn tất với WAV/lời nói Việt M3 đã duyệt, tạo ASS UTF-8 và MP4 H.264/AAC. Chọn **Final Export Studio**, áp dụng cấu hình, tạo/xem preview, xác nhận quyền nguồn và kiểm tra sync rồi xuất cuối. Không chạy lại OCR, dịch hay TTS. Thiếu artifact hoặc bản duyệt thay đổi sẽ chặn xuất.

Burn-in libass là mặc định. Soft MP4 dùng `mov_text` sau xác nhận tương thích và giữ ASS sidecar; không giữ mọi style/position ASS trên mọi trình phát. Có chế độ tắt phụ đề. Font hệ thống Arial/Segoe UI/DejaVu Sans được dò và kiểm tra glyph; không phân phối font Windows. Có màu/outline/shadow/background, tối đa hai dòng, speaker style, safe margin, vị trí và khoảng dòng. Timestamp theo M3, độ chính xác ASS tới centisecond.

Preserve Original giữ kích thước/FPS; TikTok mặc định1080×1920 với padding, crop cần xác nhận; Compact chỉ dành preview. Fast/Balanced/High dùng libx264 CRF26/21/18 và preset veryfast/fast/medium. CRF thấp thường lớn/chất lượng cao hơn; preset chậm tốn CPU hơn. Soft/tắt phụ đề có thể copy video nếu không đổi hình học/FPS/range. Voice Việt là nguồn audio mặc định; background chỉ bật khi có track tách riêng cùng provenance hợp lệ, không trộn thoại Trung gốc.

Job lưu SQLite, chạy tuần tự, có hủy/phục hồi worker; xuất vào thư mục UUID mới. Thư viện cho xem/tải MP4/ASS/report, dùng lại cấu hình và chuyển bản xuất vào thùng rác có khôi phục. Không xóa upload/artifact M2/M3. Video được kiểm tra FFprobe, decode toàn bộ, waveform và khung hình đại diện trước công bố.

```powershell
Set-Location 'D:\tiktok\Fashion-AI'
py -3.11 -m venv .venv-m4
.\.venv-m4\Scripts\python.exe -m pip install -r requirements-m4.txt
# Máy mới: Copy-Item .env.example .env; không ghi đè .env đang dùng.
# Cài FFmpeg/FFprobe có libx264, AAC, libass; đặt PATH hoặc FFMPEG_PATH/FFPROBE_PATH trong .env.
ffmpeg -hide_banner -filters | Select-String 'ass|subtitles'
ffmpeg -hide_banner -encoders | Select-String 'libx264|libopenh264|aac|mov_text'
.\.venv-m4\Scripts\python.exe -m streamlit run app/main.py
.\.venv-m4\Scripts\python.exe -m pytest tests/test_m4.py -q
```

Các model M1/M3 chỉ cần để tạo artifact trước M4 hoặc chạy E2E thật, không tải lúc khởi động. Hướng dẫn model, test đầy đủ, kết quả, giới hạn và 18 tiêu chí: [M4 test report](docs/M4_TEST_REPORT.md); thiết kế: [M4 plan](docs/M4_IMPLEMENTATION_PLAN.md). M4 đã merge qua PR #6. Hướng dẫn source release v1.0.0: [cài đặt và nâng cấp](docs/RELEASE_v1.0.0.md); Windows packaging thuộc M5, chưa nằm trong bản này.

## Smart Auto Review

Trong Nhận diện & Dịch, chọn Thủ công (mặc định), Smart Auto Review (khuyên dùng), hoặc Auto Approve All. Smart đánh giá OCR và bản dịch độc lập; chỉ cụm khớp chính xác thuật ngữ đã kiểm chứng mới có đủ bằng chứng để tự duyệt. Câu neural chưa xác định được nghĩa vẫn cần kiểm tra dù OCR=1.000. Điểm là heuristic, không phải xác suất đúng.

Có duyệt các đoạn đã chọn / cả trang (tối đa 100) kèm xác nhận, chuyển về chờ duyệt, lọc cần kiểm tra và số liệu từng nhóm. Đoạn bị loại không tự được duyệt lại; chuyển về chờ duyệt trước. Sửa nội dung đã duyệt sẽ hủy duyệt cũ. Các thao tác có audit, hash nội dung và thời gian; rerun không tự lặp thao tác. Giá/số/kích thước, tên thương hiệu, chữ Trung còn sót, câu lặp, lỗi provider và claim đáng ngờ đều ngăn Smart tự duyệt. Tắt kiểm tra nghĩa không cho phép duyệt chỉ bằng OCR.

Migration review phiên bản 20 chỉ thêm bảng trạng thái/audit, có backup SQLite; trạng thái cũ pending/approved/rejected vẫn được giữ cho M1 và M2. AUTO_APPROVED và MANUALLY_APPROVED cùng ánh xạ approved. Không gọi API ngoài. Cấu hình AUTO_REVIEW_* trong .env.example. Chạy bằng `.\.venv-m1-clean\Scripts\python.exe -m streamlit run app/main.py`; test đầy đủ với M1_RUN_REAL=1. Chi tiết: docs/SMART_AUTO_REVIEW_PLAN.md.

Ứng dụng Windows chạy cục bộ: nhập MP4/MOV/MKV, giữ bản gốc, lưu SQLite, nhận diện chữ Trung bằng PaddleOCR, gom caption, dịch Việt offline và sửa/duyệt từng đoạn. Giao diện tiếng Việt, không cần tài khoản hoặc API trả phí. M0–M4 đã tích hợp: thay chữ Việt trên hình, nhận diện/lồng tiếng Việt, ASS và MP4 cuối. Bản dịch/lời nói cần duyệt trước xuất.

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

Quy trình Git: M0 có tag `v0.1.0` trên main. M1 đã được chủ dự án merge qua PR #2 vào approved develop `bb4b94a`. Smart Review đã được chủ dự án merge qua PR #3 vào develop `c76f4c5`; M2 đã cập nhật baseline này và kiểm chứng chung. Đây là lịch sử workflow M2; trạng thái hiện tại xem CHANGELOG.md và báo cáo nghiệm thu M4.

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

## Nhận diện lời và lồng tiếng Việt (M3)

M2 đã được chủ dự án merge qua PR #4 vào develop `59220ba`. M3 tạo **audio riêng**, chưa ghép vào MP4; không làm M4/subtitle. Dữ liệu speech/voice/job tách khỏi OCR/text/render, nâng cấp additive schema40 có backup, giữ bảng cũ.

Cài local CPU trên Windows (FFmpeg/FFprobe có libx264; Python3.11):

```powershell
py -3.11 -m venv .venv-m3
.\.venv-m3\Scripts\python.exe -m pip install -r requirements-m3.txt
# Máy mới: sao chép .env.example thành .env; giữ .env hiện có nếu đã cài.
# Đặt ASR_PROVIDER=whisper trong .env để dùng lựa chọn CPU đã kiểm chứng.
$env:HF_HUB_DISABLE_XET='1'
.\.venv-m3\Scripts\python.exe scripts/setup_m3_models.py --whisper --tts
# Cần Argos/Paddle như M1 nếu chưa cài; không tải lại khi đã có:
.\.venv-m3\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
.\.venv-m3\Scripts\python.exe -m streamlit run app/main.py --server.address 127.0.0.1
```

Whisper base local ~148MB, TTS Việt ~81MB đã đo; chỉ tải chủ động, không tải khi khởi động ứng dụng. Có thể chọn tiny/base/small qua `--whisper-size` và đường dẫn WHISPER_MODEL_DIR riêng; base là lựa chọn đã test, tiny đã nhận sai nhiều trên mẫu thử. FunASR là adapter chính theo yêu cầu, mặc định cấu hình `funasr`, nhưng cần tự cài toolkit/model local theo phần dưới; không tuyên bố model FunASR đã chạy thật.

Trong **AI Dubbing Studio**, chọn dự án, ASR local, ngôn ngữ và chunk (mặc định30s, overlap2s), nhấn **Chạy ASR**, sau đó **Nạp transcript và lịch sử**. Nhận diện chữ giản/phồn phụ thuộc model; confidence thiếu sẽ giữ trống. Không có model/audio thì báo rõ. ASR rerun yêu cầu xác nhận và chỉ thay transcript khi thành công. Speech timestamps chỉnh tay được; chunk matching thận trọng, không bảo đảm speaker/từ chính xác mọi cảnh.

Chọn các câu rồi **Dịch lại các lời đã chọn** với Argos; sửa chữ Trung, câu Việt, timing, speaker và duyệt. Mọi dịch tự động pending; sửa lời/timing/speaker đã duyệt sẽ hủy duyệt cũ. Phải lưu bản sửa trước khi tạo job. Argos thực đã làm mất chi tiết quần áo (`Tôi thích cái này.`), nên cần sửa nghĩa trước khi duyệt; không dùng confidence ASR/OCR làm bằng chứng nghĩa dịch.

TTS local dùng **VAIS1000/Piper, một giọng Việt đã xác minh `vais1000:0`**,22,050Hz, qua sherpa-onnx1.13.8. Chọn tốc độ/volume, nghe thử câu ngắn trước khi tạo cả video; có cấu hình chung hoặc riêng speaker và tạo lại TTS các câu được chọn. Local model không hỗ trợ pitch/gender tùy chọn, UI báo rõ. Không cloning/giả giọng tác giả. Model card dữ liệu VAIS1000 ghi CC BY4.0; xem nguồn/notice ở báo cáo. Không đưa weights vào Git.

Azure chỉ là tùy chọn: đặt AZURE_SPEECH_KEY và AZURE_SPEECH_REGION trong môi trường/.env riêng, chọn Azure, xác nhận gửi chữ Việt tới Microsoft, lấy danh sách vi-VN thật rồi chọn giọng. Không hardcode giọng cloud giả định; không upload audio gốc; có thể phát sinh phí theo tài khoản. Azure chưa kiểm thử thật do không có credentials; unit test không được coi là cloud inference. Không bật cloud mặc định.

**Ghép toàn bộ audio Việt** chỉ dùng lời đã approved, yêu cầu duyệt/loại hết pending và xác nhận quyền nguồn hợp lệ. ModeA chỉ lời Việt và im lặng giữa các câu. ModeB chưa triển khai: FFmpeg đơn giản không tách sạch thoại Trung khỏi nhạc. Lời ngắn giữ tốc độ tự nhiên và chừa im lặng; chênh nhẹ dùng atempo giữ pitch, mặc định factor0.85–1.20; quá dài báo rút gọn bản dịch/chỉnh timing, không cắt lời hoặc ép tốc độ cực đoan. Overlap lời bị chặn để chỉnh tay. Master WAV mono24k PCM16 đúng timeline nguồn trong một sample; có limiter/normalization.

Worker nền lưu tiến độ/trạng thái, hủy/retry/phục hồi khi process chết; rerun trang không tạo lại job. Một tác vụ nặng chung OCR/render/dub mỗi DB. Source stream lưu riêng original.mka, WAV16k căn timeline cho ASR, TTS cache theo model/runtime/text/voice, các đoạn sau sync và master/manifest nằm trong thư mục audio của dự án. Nạp lịch sử để nghe/tải WAV. Chưa mux video. Cache/log/output có thể tích lũy, không tự xóa dữ liệu người dùng.

FunASR tùy chọn: cài `requirements-m3-funasr.txt`, tải thủ công model Paraformer timestamp-capable từ [model zoo chính thức](https://github.com/modelscope/FunASR), đặt ASR_MODEL_DIR tới thư mục có config.yaml/weights. FUNASR_VAD_DIR, FUNASR_PUNC_DIR, FUNASR_SPEAKER_DIR chỉ nhận thư mục local đã cài, không bật remote code. Speaker model cần VAD và một chunk duy nhất để tránh đổi nhãn speaker qua chunk; mặc định speaker thủ công, không cần diarization. Tool/model FunASR thực và GPU chưa kiểm chứng trên môi trường này.

Cấu hình M3 trong .env.example: provider/model paths, ngôn ngữ/device, chunk/overlap, timeout1800s, tối đa300 đoạn, ngưỡng sync. Dùng OCR_CPU_THREADS để giới hạn số thread CPU (mặc định2). Không ghi API key vào SQLite/log/manifest.

Kiểm chứng: **177 test pass**, gồm toàn bộ M0–M3/Smart,38 test M3 xác định và một E2E real Whisper→Argos→duyệt→TTS Việt→WAV5s/120.000 mẫu. Chạy `python -m pytest tests/test_m3.py -q`; bật M1_RUN_REAL/M2_RUN_REAL/M3_RUN_REAL để chạy đầy đủ model thật đã cài. Fixture tiếng Trung gốc được tạo bằng model AISHELL3 tùy chọn `setup_m3_models.py --fixture-chinese`, không dùng audio creator. ASR/giọng/dịch có giới hạn chất lượng; không phải benchmark thực tế tổng quát.

[M3_TEST_REPORT.md](docs/M3_TEST_REPORT.md) ghi đủ17 tiêu chí PASS/NOT TESTED, model/giấy phép, test thật so với mock, lệnh PowerShell và contract M4. Gọi `approved_dub(sessions,settings,project_id)` từ `app.services.dubbing_contract` để lấy audio/Chinese+Vietnamese transcript/timestamps/raw TTS/sync/config; hàm chặn output stale/sửa/hỏng/mất quyền. M3 đã merge qua PR #5 và tích hợp M4; workflow mới theo bản phát hành hiện tại.

Lịch sử M0: [PR #1](https://github.com/hphuc032/Fashion-AI/pull/1) đã qua CI và merge; tag chú thích v0.1.0 giữ nguyên trên main. Workflow: docs/GIT_WORKFLOW.md; thông tin hiện tại xem CHANGELOG.md.
