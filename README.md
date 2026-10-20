# NVB AI Studio — Windows AI image/video batches

[Download latest Windows Setup](https://github.com/techzoneadapter-droid/NVB-AI-Studio/releases/latest)

## Đăng nhập qua Chrome đã có sẵn

1. Cài Setup mới nhất, mở Tài khoản Flow, bấm KẾT NỐI VỚI CHROME ĐANG MỞ.
2. App tự giải nén sub2gen đã đóng gói và tự cài các phụ thuộc Python lần đầu qua uv, dùng Internet; không yêu cầu Git/Python/Bun/uv riêng trên máy.
3. Lần đầu duy nhất: app mở chrome://extensions, bật Developer mode rồi Load unpacked, chọn thư mục extension mà app đã sao chép vào clipboard.
4. Trong sub2gen Worker → Options: chọn My account, dán khóa bằng nút Sao chép khóa kết nối trên app, lưu cấu hình và Import/Sync account.
5. Quay lại app nhấn Kiểm tra tài khoản Flow. Khi báo đã đồng bộ thì tạo thử một ảnh.

Chrome không cho app đọc phiên/cookie của cửa sổ Chrome đang chạy khi người dùng chưa cấp quyền extension. Do đó **không thể tự đăng nhập hoàn toàn bằng một cú nhấp** mà không có bước phê duyệt Chrome một lần. Extension upstream xin quyền web và cookie rộng; đọc quyền trước khi chấp thuận. App không âm thầm cài tiện ích hoặc truy xuất cơ sở dữ liệu cookie của Chrome.

## Chức năng

- PyQt5 desktop dark mode với 9 màn hình, nhiều dự án.
- Import Excel, TXT, CSV và JSON thành batch ảnh/video.
- Hồ sơ nhân vật với ảnh tham chiếu và mô tả ngoại hình chung.
- Các chế độ Veo text-to-video, image-to-video, first/last, reference theo khả năng model.
- Hàng đợi SQLite giữ job ID từ xa, tránh gửi lại nếu chưa rõ có tiêu credits.
- Thư viện kết quả, lưu theo dự án, metadata JSON, ghép MP4 dùng FFmpeg.
- Nút Cập nhật kiểm tra GitHub Releases và mở bộ cài mới.

## Giới hạn

- Dùng sub2gen không chính thức; Flow thay đổi giao thức hoặc credits có thể gây lỗi.
- Engine sub2gen được pin commit 324038a6102817a88459ce193ad39472bab9d537 và build cùng Setup.
- Python/phụ thuộc cần tải ở lần đầu; cần kết nối Internet. Lần sau engine dùng lại các gói đã tải.
- Đã bổ sung test nội bộ engine nhưng **chưa thử bằng tài khoản Flow thực tế của bạn**.
- Chưa có nhận diện khuôn mặt AI chuyên sâu, tự phân cảnh bằng LLM hoặc nút auto-cài Chrome extension im lặng.

## Kỹ thuật

Engine ở %LOCALAPPDATA%\NVB_AI_Studio\engine; dữ liệu được giữ trong thư mục persistent khi nâng cấp. Khóa lưu Windows Credential Manager, Chrome đăng nhập Google trong phiên đã được cấp quyền, backend chỉ lắng nghe 127.0.0.1:8000.

[Windows build Actions](https://github.com/techzoneadapter-droid/NVB-AI-Studio/actions/workflows/build-windows.yml)

Chạy source chỉ dành cho lập trình viên: cài requirements.txt và chạy python app.py. Bản source không chứa backend tích hợp; cần sử dụng Setup trên Releases để có chế độ kết nối tự động.


### Chrome extension: ghép nối hai khóa riêng biệt

- Mở NVB AI Studio → Tài khoản Flow → **Sao chép API key** và **Tạo mã ghép nối (10 phút)**.
- Mở cửa sổ sub2gen Worker ở Chrome → bánh răng (Options): **WebSocket URL** = `ws://127.0.0.1:8000/worker_ws`; chế độ **My account**.
- Dán API key vào **Managed API key**; dán mã một lần vào **Pairing code**. Đây là hai giá trị khác nhau.
- Bấm **Save changes**, mở popup → **Reconnect**, rồi **Sync Google account**.
- Cuối cùng trở lại app → **Kiểm tra tài khoản Flow**. Khi mã hết hạn, tạo mã mới trong app.
- Không chia sẻ mã ghép nối, cookie, API key hoặc mật khẩu Google qua ảnh chụp màn hình.
