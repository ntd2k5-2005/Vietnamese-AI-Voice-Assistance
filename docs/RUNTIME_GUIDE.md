# Vận hành Vietnamese Voice AI

## Colab

```bash
bash scripts/setup_colab.sh
orther/envs/app/bin/python scripts/start_services.py --profile colab-t4 --with-web
```

Đợi dịch vụ sẵn sàng rồi mở tunnel đến cổng 7860. Khi cập nhật mã, khởi động lại các dịch vụ và tải lại trang.

Profile Colab hiện dùng TTS PyTorch/CUDA, cần bật GPU trước setup. Nếu môi trường cũ chỉ cài VieNeu ONNX/CPU, phải chạy lại setup để có thư viện CUDA và bộ trọng số/codec tương ứng; chỉ restart web không đủ. Xem `services/tts/README.md`. Kiểm tra `/health/ready` của TTS: `backend=pytorch`, `device=cuda`, `streaming_supported=true`; không suy ra GPU chỉ từ tên profile.

Khởi động sẽ xóa qua lifecycle những tài liệu kiểm thử có đúng cặp ID/tên file `colab-smoke-*/smoke-source.txt` hoặc `product-smoke-*/product-smoke.txt`. Bản ghi đã xóa được giữ trong audit RAG và không hiện trong danh sách tài liệu web. Không nạp tài liệu smoke tự động; bỏ ô tạo smoke nếu notebook bên ngoài repo còn chứa ô đó. Có thể chạy riêng:

```bash
orther/envs/app/bin/python scripts/cleanup_demo_sources.py --rag-url http://127.0.0.1:8001 --apply
```

Chữ hiện theo số frame audio đã thực sự tiêu thụ ở AudioWorklet, chia theo thời lượng của câu. Khi chờ đệm, chữ dừng; hủy lượt thì bỏ cả hàng đợi chữ và audio cũ. Nếu giọng đọc lỗi, phần văn bản đã sinh vẫn được hiển thị kèm lỗi dễ hiểu.

## Windows

```powershell
. ./scripts/use-project-storage.ps1
$env:OLLAMA_HOST='127.0.0.1:11436'
ollama serve
```

Giữ terminal này mở. Trong terminal khác tại thư mục gốc, áp dụng cùng cấu hình lưu trữ/OLLAMA_HOST và chạy `scripts/setup_windows.ps1` khi chưa cài đủ môi trường. Khi đã cài đủ:

```powershell
. ./scripts/use-project-storage.ps1
./orther/envs/app/Scripts/python.exe scripts/start_services.py --profile local-balanced --with-web
```

Ollama dùng cổng riêng 11436. Các dịch vụ ứng dụng dùng 8100–8103; web ở cổng 7860.

## Hội thoại giọng nói

Luồng mặc định: gom câu → hàng đợi text → TTS → hàng đợi âm thanh → phát. TTS tiếp tục xử lý câu kế tiếp khi trình duyệt đang phát câu trước. Chỉ câu quá dài mới được chia tại ranh giới an toàn.

Trong `app/.env`:

```dotenv
TTS_SEGMENTATION_MODE=sentence
TTS_BUFFER_COMPLETE_UNITS=false
VAD_MIN_SPEECH_MS=250
VAD_MIN_SILENCE_MS=650
VAD_BARGE_IN_ENABLED=false
```

Khoảng im lặng được tính sau khi đã nhận đủ lời nói. Ngắt lời mặc định tắt để tránh mic bắt tiếng loa. VAD dùng năng lượng âm thanh; môi trường nhiều nhiễu có thể cần chỉnh ngưỡng.

Trình duyệt cần cho phép microphone; khi truy cập từ xa dùng HTTPS. Giới hạn phần cứng và tốc độ sinh vẫn có thể tạo khoảng chờ giữa các câu.

## Lưu trữ và kiểm tra

Model, cache, môi trường và log nằm trong `orther/`. Không đổi cấu hình cache ứng dụng toàn máy để chạy sản phẩm.

```powershell
. ./scripts/use-project-storage.ps1
./orther/envs/app/Scripts/python.exe -m pytest app/tests tests --basetemp=orther/tmp/pytest-run
node app/tests/browser_audio_regression.cjs
```
