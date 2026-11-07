# Vietnamese Voice AI

Trợ lý giọng nói tiếng Việt độc lập, hỗ trợ trò chuyện và tìm thông tin từ kho tri thức của người dùng.

## Chức năng

- Đặt câu hỏi bằng văn bản hoặc giọng nói.
- Bấm mic để nói, tự gửi khi ngừng nói; có chế độ tự nghe liên tục.
- Truy xuất tài liệu và hiển thị nguồn tham khảo.
- Đọc câu trả lời theo hàng đợi âm thanh.
- Quản lý tài liệu và các cuộc trò chuyện.

## Khởi chạy

Cách nhanh trên Colab/Kaggle: mở [notebook demo](notebooks/CHAY_VIETNAMESE_VOICE_AI_COLAB_KAGGLE.ipynb), bật GPU/Internet và **Run all**. Notebook tự clone đúng commit, chạy dịch vụ và in link Cloudflare; không cần ô vá digest trước bước 4.

VieNeu SDK 3.8.3 đã khóa commit, đủ 25 giọng (mặc định Hải Đăng), streaming PCM 48 kHz. Xem [kết quả kiểm thử và độ trễ](docs/VIENEU_383_UPGRADE.md).

Trên Colab/Linux, từ thư mục gốc repository:

```bash
bash scripts/setup_colab.sh
orther/envs/app/bin/python scripts/start_services.py --profile colab-t4 --with-web
```

Giao diện web ở cổng 7860. Chỉ mở tunnel sau khi dịch vụ báo sẵn sàng.

Trên Windows, dùng `scripts/setup_windows.ps1` để cài môi trường theo hướng dẫn trong [hướng dẫn vận hành](docs/RUNTIME_GUIDE.md).

## Cấu hình và dữ liệu

Model được khai báo trong `config/model_manifest.json`; phân bố thiết bị và cổng dịch vụ trong `config/runtime_profiles.json`. Tùy chọn ứng dụng nằm trong `app/.env`, có mẫu tại `app/.env.example`.

Môi trường, model, cache, tệp tạm và log được lưu trong `orther/` của repository. Không đưa thư mục này lên Git.

## Tài liệu

- [Hướng dẫn vận hành](docs/RUNTIME_GUIDE.md)
- [Kiến trúc](docs/ARCHITECTURE.md)
- [Nguồn gốc thành phần](PROVENANCE.md)
