# NVB AI Studio — Tạo ảnh/video AI hàng loạt bằng Google Flow

[Tải bộ cài Windows mới nhất](https://github.com/techzoneadapter-droid/NVB-AI-Studio/releases/latest)

## Kết nối Google Flow — chỉ một nút trong app

1. Cài Setup và mở **Tài khoản Flow → KẾT NỐI GOOGLE FLOW**.
2. App tự khởi động backend sub2gen, tạo API key và Pairing code (không yêu cầu tự cài repo) rồi tự sao chép **một mã kết nối**.
3. Chỉ lần đầu hoặc sau khi cập nhật tiện ích: mở \`chrome://extensions\` (app tự mở), cài tiện ích sub2gen Worker từ thư mục app đã chuẩn bị nếu chưa có, hoặc bấm **Reload** nếu đã cài. Chrome yêu cầu người dùng cấp quyền.
4. Mở popup tiện ích → bánh răng Options → khung **NVB AI Studio · Kết nối nhanh** → **Ctrl+V → Kết nối NVB AI Studio**. Tiện ích tự điền hai khóa, ghép nối và Sync Google account; app tự dò trạng thái.
5. Khi app báo Đã kết nối, bắt đầu tạo ảnh/video.

**Không cần điền gateway URL, API key hoặc Pairing code riêng lẻ.** Chrome không cho phép phần mềm tự cài/chỉnh quyền extension của trình duyệt hiện tại một cách im lặng. Vì vậy bước cấp quyền/click một lần bên Chrome vẫn cần thiết.

**Bảo mật:** mã một lần trên clipboard chứa API key nội bộ và Pairing code có hạn; không gửi mã đó cho người khác và không dán lên web khác. Extension chỉ nhận mã do app tạo cho localhost. Khi đã ghép nối, hãy sao chép một nội dung không nhạy cảm khác để xóa mã khỏi clipboard nếu cần.

## Khả năng hiện có

Dự án độc lập, nhập Excel/TXT/CSV/JSON, ảnh tham chiếu nhân vật, xưởng ảnh/video, hàng đợi SQLite có phục hồi, thư viện kết quả, ghép MP4 bằng FFmpeg và nút Cập nhật qua GitHub Releases.

Phiên Flow dùng cơ chế không chính thức của sub2gen, có thể thay đổi theo chính sách Google. Chưa nghiệm thu tạo video/ảnh end-to-end bằng tài khoản Google Flow thực tế của người dùng.
