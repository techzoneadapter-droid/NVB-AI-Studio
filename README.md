# NVB AI Studio

Ứng dụng Windows 10/11 tạo ảnh và video AI hàng loạt thông qua [sub2gen](https://github.com/agmmnn/sub2gen), sử dụng PyQt5, hàng đợi SQLite, thư viện nhân vật, storyboard, thư viện kết quả và FFmpeg.

## Tải Setup Windows

- [Tải bộ cài mới nhất (.exe) từ GitHub Releases](https://github.com/techzoneadapter-droid/NVB-AI-Studio/releases/latest)
- [Theo dõi build tại GitHub Actions](https://github.com/techzoneadapter-droid/NVB-AI-Studio/actions/workflows/build-windows.yml)

Mỗi lần push main, Actions chạy test, build PyInstaller + Inno Setup, tải artifact và phát hành bản Setup mới nếu tất cả thành công. Nút Cập nhật trong ứng dụng kiểm tra bản phát hành mới và mở link trực tiếp tới file cài đặt.

## Yêu cầu

Ứng dụng KHÔNG kèm sub2gen, tài khoản Flow hoặc credits. Cần tự thiết lập sub2gen theo hướng dẫn upstream.

1. Cài Git, uv, Bun theo [README sub2gen](https://github.com/agmmnn/sub2gen).
2. PowerShell: git clone https://github.com/agmmnn/sub2gen.git
3. PowerShell: cd sub2gen
4. PowerShell: uv run setup
5. PowerShell: uv run sub2gen
6. Vào http://localhost:8000 và đổi mật khẩu admin mặc định ngay.
7. Đăng nhập Flow và ghép worker/Chrome Extension theo tài liệu sub2gen.
8. Trong sub2gen API key manager, tạo key có quyền chạy mô hình và async jobs.
9. Mở NVB AI Studio → Tài khoản Flow → nhập http://127.0.0.1:8000 và API key.
10. Tạo dự án, thêm prompt vào hàng đợi, bắt đầu xử lý.

Cần cài FFmpeg nếu muốn ghép nhiều video theo thứ tự.

## Chạy từ source

- git clone https://github.com/techzoneadapter-droid/NVB-AI-Studio.git
- cd NVB-AI-Studio
- py -3.11 -m venv .venv
- .venv\Scripts\python.exe -m pip install -r requirements.txt
- .venv\Scripts\python.exe app.py

## Các màn hình

Tổng quan, Xưởng tạo ảnh, Xưởng tạo video, Nhân vật AI, Storyboard, Hàng đợi, Thư viện, Tài khoản Flow, Cài đặt.

Hỗ trợ nhập TXT/CSV/XLSX/XLSM/JSON. Nhân vật gồm mô tả và tối đa ba ảnh mẫu. Các chế độ video gồm text, image, first/last frame và reference tùy giới hạn model. Hàng đợi lưu remote_id để tra cứu sau khi khởi động lại; không tự gửi lại job có thể đã trừ credits. Media hoàn thành được lưu theo thư mục dự án, kèm JSON metadata.

## Những gì chưa có / chưa kiểm chứng

Chưa chạy thử end-to-end bằng tài khoản Google Flow thực tế. sub2gen dùng giao thức không chính thức và có thể thay đổi. Đồng nhất nhân vật mới ở mức prompt + ảnh tham chiếu, chưa có bộ đánh giá danh tính AI tự động. Storyboard hỗ trợ chuẩn bị phân cảnh thủ công, chưa dùng AI để tự tách kịch bản. Bộ cài chỉ chứa ứng dụng desktop và không cài backend sub2gen. Nút cập nhật tải bộ cài mới, chưa cài đè im lặng. Không cam kết ẩn hoàn toàn trình duyệt vì khi xác minh đăng nhập có thể cần Chrome.

## Kiến trúc và dữ liệu

NVB AI Studio PyQt5 → SQLite job manager → Gateway HTTP API của sub2gen → Worker/session Google Flow. Không thay đổi mã nguồn sub2gen.

Dữ liệu cục bộ: %LOCALAPPDATA%\NVB_AI_Studio. Kết quả: thư mục do người dùng chọn. API key ghi nhớ bằng Windows Credential Manager qua keyring; nếu không có secure storage sẽ chỉ giữ trong phiên hiện tại.

Chỉ dùng tài khoản/credits bạn được phép sử dụng. Tuân thủ rate limits và xác minh từ Google Flow.
