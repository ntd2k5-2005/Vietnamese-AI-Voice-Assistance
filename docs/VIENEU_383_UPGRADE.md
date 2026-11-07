# VieNeu 3.8.3 — nâng cấp và kiểm thử ngày 07/11/2026

Đã nâng SDK 3.3.0 lên **3.8.3**, khóa upstream `6cdb62e03e6a9fd6ebff70e77aff8570c50949c3`. Đây là bản mã nguồn mở mới nhất trên upstream khi đối chiếu, không phải số phiên bản ứng dụng Desktop hoặc dịch vụ V4. Giữ **v3 Turbo**, backbone `2da0efab622a1722125991736524f080b751ef5b`, codec GPU `6aa02b01e445cc585582cf0ba480bc3ea6c8dd68`, codec ONNX `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`.

Nguồn đối chiếu: [pyproject tại commit đã khóa](https://github.com/pnnbao97/VieNeu-TTS/blob/6cdb62e03e6a9fd6ebff70e77aff8570c50949c3/pyproject.toml), [API v3 Turbo](https://github.com/pnnbao97/VieNeu-TTS/blob/6cdb62e03e6a9fd6ebff70e77aff8570c50949c3/src/vieneu/v3turbo.py), [preset chính thức](https://github.com/pnnbao97/VieNeu-TTS/blob/6cdb62e03e6a9fd6ebff70e77aff8570c50949c3/src/vieneu/assets/voices_v3_turbo.json), [streaming và giới hạn hiệu năng](https://github.com/pnnbao97/VieNeu-TTS/blob/6cdb62e03e6a9fd6ebff70e77aff8570c50949c3/docs/streaming.md).

## Thay đổi cần cho sản phẩm

- Giữ `Vieneu(mode="v3turbo")`, `infer_stream(text, voice, max_chars)` và PCM float32 mono **48 kHz**. Gateway vẫn chuyển PCM16 qua WebSocket; AudioWorklet và epoch hủy giữ nguyên.
- SDK mới có CUDA Graph/continuous streaming. Cấu hình **một stream** cho demo (`TTS_MAX_STREAMS=1`), tránh đặt 16 slot mặc định khi chỉ có một lượt đọc. Không bật chế độ codec CUDA Graph thử nghiệm mà upstream cảnh báo làm sai âm thanh.
- Có **25 preset**, Hải Đăng mặc định. Upstream đổi tên Minh Quân/Minh Quân Pro thành Hải Đăng và giữ alias. Giọng khác như Thiện Minh, Quốc Tuấn cũng giữ alias cũ. Giao diện lấy danh sách API, chọn bằng tên; index chỉ dùng nội bộ cho client cũ.
- CPU mặc định **ONNX fp32**, chọn graph `onnx_update`, đúng thay đổi mặc định upstream từ 3.4. Có cấu hình int8 riêng, không tự bật khi chưa kiểm tra CPU/chất lượng. Giữ revision trọng số cũ, đã xác minh có đủ graph fp32.
- Sửa điểm giữ toàn bộ waveform của câu: `TTS_BUFFER_COMPLETE_UNITS=false`. Native PCM được đưa vào hàng chờ ngay khi tới; không đợi hết câu và không đợi loa phát xong mới tổng hợp câu kế. Hàng chờ vẫn có giới hạn, AudioWorklet vẫn prebuffer/rebuffer.
- HTTP disconnect/hủy đóng generator, trả lại slot xử lý; CPU giới hạn một stream để bảo vệ trạng thái ONNX. Worker CUDA lỗi khiến readiness báo lỗi.
- Chữ chạy theo số frame thực đã phát. Khi TTS chưa tạo xong nên chưa biết tổng thời lượng, dùng tốc độ ký tự tạm thời (từ các đoạn đã đo, mặc định 20 ký tự/giây cho đoạn đầu), sau đó đối chiếu thời lượng thật; không chạy tiếp lúc âm thanh đang đệm, không xóa lùi chữ. Đây là đồng bộ xấp xỉ, không phải căn chỉnh âm vị.

Không đổi STT, RAG, LLM hoặc thuật toán truy xuất. Riêng pin Ollama sai trước đó được sửa chính thức thành digest đã đối chiếu registry `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04` của `qwen3.5:4b`; không chấp nhận tùy ý digest đang cài. Không ghi đè kết quả benchmark cũ.

## Số đo trên phiên Colab người dùng cung cấp

Ba lượt `Xin chào.` trước và ba lượt sau; mỗi nhóm có sáu đơn vị TTS. Đây là quan sát demo, **không phải A/B cùng waveform/seed/giọng**: giọng mặc định và lời LLM có thay đổi. Không suy tốc độ tối đa hay chất lượng giọng từ pilot nhỏ này.

| Chỉ số, trung vị | 3.3.0 trước | 3.8.3 sau |
|---|---:|---:|
| TTFB HTTP của TTS, tại client gateway | 379 ms | 167 ms |
| RTF HTTP TTS: thời gian nhận hết / thời lượng PCM | 0,980 | 0,553 |
| Trình duyệt gửi yêu cầu → nhận PCM đầu | 5,406 s | 2,707 s |
| Gateway giữ khung PCM đầu trước khi vào media queue | 2.623 ms | 0,121 ms |
| Lỗi thứ tự PCM / thiếu âm thanh / lỗi JS | 0 / 0 / 0 | 0 / 0 / 0 |

Gateway giữ PCM được đo bằng `time.time_ns` ở cùng máy/tiến trình, từ TTS client nhận khung tới enqueue. TTFB/RTF HTTP dùng `perf_counter` ở gateway. Mốc trình duyệt dùng `performance.now`, bao gồm gửi yêu cầu, LLM, tổng hợp và mạng; **không phải TTFT LLM hoặc thời điểm loa vật lý bắt đầu phát**. Không trừ trực tiếp đồng hồ trình duyệt với đồng hồ máy chủ để suy độ trễ một chiều.

Warmup native SDK từ health của bản GPU mới có bốn lần chạy: TTFB trung vị **127 ms**, RTF trung vị **0,563**; lần đầu có tạo CUDA Graph, vẫn giữ trong dữ liệu. Health xác nhận `pytorch`, `cuda`, `cuda_graph_streaming=true`, một slot, 25 giọng. Không coi danh sách provider ONNX chỉ có CPU là bằng chứng PyTorch bị chuyển về CPU.

Một lượt bổ sung dùng frontend cuối trong checkout, gọi backend Colab thật, nhận PCM đầu sau **4,062 s**, rồi kiểm tra dừng lúc đang phát và gửi câu mới: lượt cũ `cancelled`, lượt mới phát hết, không lỗi JS/PCM. Frontend được nạp bằng route của công cụ kiểm thử, không sửa phiên đang chạy của người dùng; chưa coi đây là bằng chứng đã deploy toàn bộ commit cuối. Kết quả dao động theo mạng, lịch sử và lời LLM.

**RTF 0,01 chưa đạt.** SDK cũ và giữ PCM cả câu là hai bất cập đã có bằng chứng. Đo KLTN trước đây dùng chế độ/tải khác (full waveform so với streaming, tải GPU dùng chung), nên không dùng để kết luận đơn giản T4 chậm hơn GPU laptop. Chưa profile kernel codec/backbone để quy toàn bộ phần chậm còn lại cho một thành phần.

## ONNX CPU và kiểm thử chức năng

Chạy model thật 3.8.3 trong môi trường riêng của Eureka trên Windows, `onnx/fp32`, bốn thread: nạp được 25 giọng, chọn Hải Đăng, tạo WAV 48 kHz hữu hạn và không rỗng. Hai câu cho audio **2,64 / 5,92 s**, RTF HTTP **2,047 / 1,965**, PCM đầu **951 / 1.279 ms**. Đường CPU tương thích nhưng **không đạt sinh nhanh hơn thời gian thực** trong phép thử này; không ghi nhận nó thành GPU hoặc cam kết demo realtime CPU.

Kiểm thử tự động bao phủ preset theo tên/alias/index, PCM 48 kHz, đóng generator/disconnect/slot, hủy và lượt kế, câu đầu tới TTS trước LLM xong, truyền PCM trước khi hết câu, trace/pin, cache/resume và cú pháp notebook. Có tám nhóm Node kiểm worklet/chữ/micro/epoch; hai lượt Chrome fixture cố tình sinh chậm vẫn phát hết, có rebuffer đúng dự kiến. Fixture không dùng làm số tốc độ model. Chưa chấm MOS, độ đúng phát âm bằng người nghe hoặc mic/loa vật lý.

## Tái lập và bằng chứng

- `orther/artifacts/tts-upgrade-20261107/`: health trước/sau, preset, `t4-comparison.json`, các thư mục `t4-before-*`, `t4-after-*`, `t4-final-ui-*`, kiểm hủy/phát tiếp, ảnh, log và JUnit.
- `orther/artifacts/tts-runtime/*/`: phép đo độc lập mới, JSON từng request và WAV. Không ghi vào thư mục benchmark gốc.
- `orther/references/vieneu-20261107/sources.json`: URL/commit/checksum mã upstream đã đối chiếu. Toàn bộ môi trường, tải xuống và cache mới nằm trong `orther/` của Eureka, không ở ổ C.
- `python scripts/measure_tts_runtime.py --url http://127.0.0.1:8003 --runs 3` đo TTS đang chạy qua adapter production; ghi kết quả ngay từng request, không đổi model.
- `python scripts/benchmark_browser_runtime.py --url <link-demo> --runs 3 --check-cancel` đo trình duyệt/gateway đang chạy. `--frontend-from-checkout` chỉ dùng khi cần kiểm frontend local với backend thật; công cụ ghi rõ cách đo này.
- Notebook phát hành trong `notebooks/`, lấy nguyên mã từ commit GitHub được khóa trong ô cấu hình; không còn overlay/ô vá runtime. Bản copy cùng nội dung nằm ở thư mục `z_eureka` trên máy phát triển. Kaggle được hỗ trợ bằng nhận diện môi trường/thiết bị nhưng chưa chạy trực tiếp trong đợt này.
