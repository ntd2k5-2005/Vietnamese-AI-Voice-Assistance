# Vietnamese Voice AI TTS

SDK **3.8.3**, upstream **6cdb62e03e6a9fd6ebff70e77aff8570c50949c3**. Giữ v3 Turbo; không chuyển sang v3 Nano (24 kHz) hoặc dịch vụ V4. Bộ preset có 25 giọng, mặc định Hải Đăng; alias Minh Quân/Minh Quân Pro còn được upstream hỗ trợ.

`GET /api/voices` trả tên, nhãn, index và giọng mặc định; không trả vector speaker/ref codes. `POST /api/tts` nhận `voice_id` theo tên hoặc `voice_index` cho client cũ. Giao diện tải danh sách từ API, không yêu cầu nhập số. Hủy/disconnect đóng generator và trả lại slot; CPU có một slot để bảo vệ trạng thái ONNX, GPU dùng `TTS_MAX_STREAMS` (mặc định 1 cho demo).

CPU mặc định `TTS_ONNX_PRECISION=fp32` (thư mục graph `onnx_update`), có tùy chọn `int8` riêng, không tự lượng tử hóa. `TTS_THREADS=4` được giới hạn theo số CPU. GPU dùng CUDA Graph streaming từ SDK mới; không bật codec CUDA Graph thử nghiệm không bảo đảm chất lượng. Cùng bộ trọng số backbone và codec đã khóa trước khi nâng SDK.

VieNeu v3 Turbo dùng ONNX/CPU cho profile local; `colab-t4` và `server-gpu` dùng PyTorch/CUDA FP16. Cùng checkpoint backbone đã khóa; codec ONNX và PyTorch có artifact/revision riêng trong `config/model_manifest.json`. Không đổi `TTS_DEVICE=cuda` trong khi giữ backend ONNX vì upstream ONNX này là đường CPU.

Setup đọc `runtime.json`, checkout đúng upstream commit và chạy `uv sync --frozen`. Colab cài thêm torch/torchaudio CUDA và Transformers trong riêng `orther/envs/tts`, rồi prefetch đúng checkpoint GPU vào `orther/cache/huggingface`. GPU không sẵn sàng thì báo lỗi rõ, không tự chạy CPU rồi ghi nhận CUDA.

Service warmup native `infer_stream()` khi khởi động và công khai device/backend/TTFB/RTF trong `/health/ready`. Khả năng phát PCM và tốc độ thực đo được báo riêng; cấu hình GPU không bảo đảm RTF khi chưa đo trên Colab thật.

API chính: `POST /api/tts`, raw float32 PCM 48 kHz mono.
