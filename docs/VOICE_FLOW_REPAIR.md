# Sửa luồng giọng nói

**Ghi chép lịch sử của đợt sửa trước.** Bản hiện tại đã nâng VieNeu lên 3.8.3 và mặc định chuyển PCM ngay từng khung; xem [kết quả nâng cấp và đo Colab](VIENEU_383_UPGRADE.md). Các số liệu và giới hạn bên dưới thuộc đợt cũ.

Lỗi đã tái hiện bằng kiểm thử: `TurnManager.next_audio()` hết thời gian chờ nhưng tiếp tục vòng lặp trong khi giữ `audio_condition`. Producer không lấy được khóa để nạp PCM, thao tác hủy cũng có thể bị kẹt; điều này phù hợp hiện tượng LLM xong nhưng không có audio và HTTP hủy bị Cloudflare timeout. Bản sửa trả về khi hết hạn chờ; WebSocket phát keepalive rồi chờ tiếp, chỉ gửi end khi producer thực sự kết thúc. Không coi 15 giây chưa có audio là hết câu trả lời.

Luồng hiện tại:

```text
LLM reader → hàng chờ text → bộ tách câu → hàng chờ câu có giới hạn
→ một worker TTS/lượt → hàng chờ PCM có giới hạn
→ WebSocket audio → FIFO AudioWorklet → loa
                                └→ số frame đã tiêu thụ → chữ hiện dần
```

LLM reader độc lập với TTS. Câu hoàn chỉnh được đưa vào queue ngay khi nhận diện được dấu kết câu; dấu chấm cần lookahead để tránh tách nhầm số thập phân, chữ viết tắt. Cuối lượt flush phần còn lại. Kiểm thử LLM cố ý chờ TTS bắt đầu trước khi sinh tiếp đã đạt, xác nhận không phải đợi LLM xong toàn bộ mới xử lý câu đầu.

Mặc định đệm trọn đơn vị câu trước khi phát để giảm thiếu audio giữa câu. Khi xử lý xong câu A, worker nhận câu B ngay; không có ACK “loa phát xong A” chặn lời gọi TTS tiếp theo. Hàng đợi có giới hạn vẫn tạo backpressure khi quá đầy. AudioWorklet phát độc lập, giữ quyền sở hữu lượt tới khi FIFO cạn. Chữ dùng tỷ lệ frame đã phát/thời lượng câu, không dùng đồng hồ chạy tiếp trong lúc audio đang chờ đệm. Text từ LLM được giữ riêng, không hiện hết sớm; khi audio kết thúc mới hoàn thiện định dạng gốc. Nếu audio lỗi, vẫn cho xem văn bản đã sinh với thông báo lỗi.

Hủy bỏ hàng đợi cũ, lọc callback/PCM theo epoch. Đã sửa đường EOF khi queue đầy và đã hủy, tránh đợi sentinel không tới. WebSocket đóng không có end bị xem là gián đoạn thay vì treo Promise. Lỗi HTML 524 không còn được in thô lên UI; HTTP hủy có giới hạn chờ và dừng âm thanh tại máy người dùng trước khi đợi server.

## GPU

Profile `colab-t4` và `server-gpu`: VieNeu v3 Turbo PyTorch/CUDA FP16. Profile local vẫn ONNX/CPU. Phải cài lại phần TTS bằng setup và tải đúng artifact GPU; graph ONNX CPU không tự thành CUDA khi đổi một biến. Backbone và codec PyTorch được prefetch theo revision riêng, kiểm tra CUDA trước khi nạp. Health báo backend/device thực và revision đã dùng. CUDA không có thì lỗi rõ, không giả đã dùng GPU.

Căn cứ tương thích là [constructor v3 Turbo ở đúng upstream commit đang khóa](https://github.com/pnnbao97/VieNeu-TTS/blob/36c4b501b0634a8f59805e6b529a058fbd30190b/src/vieneu/v3turbo.py). GPU dùng `backend=pytorch`, `device=cuda`; không thay mô hình sang một TTS khác.

## Tài liệu thử Colab

Không tìm thấy ô tạo `colab-smoke-*` trong mã/notebook được lưu ở repo này. Khi khởi chạy, dọn qua API lifecycle đúng cặp ID/tên file kiểm thử; không hard-delete DB hoặc xóa tài liệu khác. Tombstone đã xóa không hiện trong picker. Nếu notebook Colab bên ngoài vẫn tự tạo `smoke-source.txt`, cần bỏ ô tạo đó; cleanup và lọc danh sách không chỉnh được notebook không có trong repo.

## Kiểm chứng và giới hạn

- JUnit trong `orther/artifacts/voice-repair-regression.xml`, `voice-repair-websocket.xml`, `voice-gpu-prefetch.xml`: số ca duy nhất tính trong summary; không cộng các lượt chạy lặp. Kiểm queue, timeout/keepalive, cancellation, câu đầu tới TTS trước LLM done, codec/pin GPU và tương thích stream HTTP CPU/GPU.
- `node app/tests/browser_audio_regression.cjs`: bảy nhóm kiểm tra gồm thứ tự/khử trùng PCM, pause chữ theo buffer và epoch cũ.
- `orther/artifacts/voice-repair-browser-final/`: trình duyệt Chrome, WebSocket/gateway/AudioWorklet thật với LLM stub và audio sine tổng hợp. Hai chế độ đều phát hết 20 PCM chunk, hết lượt và có chữ theo audio; kiểm từ ký tự đầu không xuất hiện trước lúc player bắt đầu. Ảnh desktop và màn hẹp có nhãn fixture, không phải minh chứng model thật.
- Chưa chạy VieNeu PyTorch CUDA hoặc tunnel Colab thật trong lượt sửa này; không có số RTF/VRAM/GPU latency mới. Chưa cam kết hết mọi khoảng ngắt khi producer chậm hơn realtime. Cần kiểm tra riêng driver CUDA, VRAM dùng chung LLM/TTS và quality giọng sau khi chạy lại Colab.
- Browser cần HTTPS hoặc localhost cho AudioWorklet/mic và thao tác người dùng để mở audio. Giới hạn replay cursor và bộ đệm vẫn tồn tại; mất kết nối quá lâu phải thử lại lượt, không được bỏ qua PCM để giả phát đủ.

Không chỉnh project KLTN hoặc khởi động model Eureka tại laptop. Không tải model/dependency mới trong lượt sửa; metadata đối chiếu nhỏ, cache, test, WAV tổng hợp và ảnh đều trong `orther/` của riêng Eureka.
