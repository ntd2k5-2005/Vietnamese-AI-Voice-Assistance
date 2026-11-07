# Vietnamese Voice AI TTS

VieNeu v3 Turbo dùng ONNX/CPU cho profile local; `colab-t4` và `server-gpu` dùng PyTorch/CUDA FP16. Cùng checkpoint backbone đã khóa; codec ONNX và PyTorch có artifact/revision riêng trong `config/model_manifest.json`. Không đổi `TTS_DEVICE=cuda` trong khi giữ backend ONNX vì upstream ONNX này là đường CPU.

Setup đọc `runtime.json`, checkout đúng upstream commit và chạy `uv sync --frozen`. Colab cài thêm torch/torchaudio CUDA và Transformers trong riêng `orther/envs/tts`, rồi prefetch đúng checkpoint GPU vào `orther/cache/huggingface`. GPU không sẵn sàng thì báo lỗi rõ, không tự chạy CPU rồi ghi nhận CUDA.

Service warmup native `infer_stream()` khi khởi động và công khai device/backend/TTFB/RTF trong `/health/ready`. Khả năng phát PCM và tốc độ thực đo được báo riêng; cấu hình GPU không bảo đảm RTF khi chưa đo trên Colab thật.

API chính: `POST /api/tts`, raw float32 PCM 48 kHz mono.
