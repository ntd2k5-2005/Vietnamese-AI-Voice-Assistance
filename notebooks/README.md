# Chạy demo bằng notebook

Mở [Colab](https://colab.research.google.com/github/ntd2k5-2005/Vietnamese-AI-Voice-Assistance/blob/main/notebooks/CHAY_VIETNAMESE_VOICE_AI_COLAB_KAGGLE.ipynb), bật GPU và chọn **Run all**. Với Kaggle, tải file notebook, bật GPU và Internet.

Notebook khóa source commit trong ô cấu hình, tự cài môi trường riêng và xuất link Cloudflare. Không cần ô vá digest hoặc overlay source trước bước 4. Nếu không cần đo TTS mỗi lần khởi động, đặt `MEASURE_TTS=False`.

Bản này dùng VieNeu 3.8.3, đủ 25 giọng và mặc định Hải Đăng. Dùng phiên sạch khi chuyển từ notebook cũ đã có chỉnh sửa source; sao lưu tài liệu trước khi kết thúc phiên. Tài liệu và model/cache nằm trong `orther/`, lịch sử hội thoại hiện ở RAM.

Xem [kết quả kiểm thử và giới hạn](../docs/VIENEU_383_UPGRADE.md). Notebook không hứa RTF 0,01 hoặc cung cấp dịch vụ 24/7.

Để tạo lại notebook sau khi sửa launcher, chạy `python scripts/build_cloud_notebook.py --revision <commit-đã-phát-hành>` từ gốc repo. Tạo notebook sau khi commit source; notebook được commit riêng để trỏ đúng source đã phát hành.
