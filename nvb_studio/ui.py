"""Native PyQt5 desktop. All network generation is off the UI thread."""
import json
import shutil
import sys
import webbrowser
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QComboBox, QLineEdit, QTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QAbstractItemView, QCheckBox, QFormLayout,
    QScrollArea, QSplitter, QProgressBar, QGroupBox
)
from . import __version__
from .config import APP_NAME, REPOSITORY, SecretStore, load_settings, save_settings, data_dir
from .store import Store, slug
from .importers import read_prompts
from .worker import BatchWorker
from .gateway import Gateway
from .media import combine_videos

IMAGE_MODELS = [
    "gemini-3.1-flash-image-landscape", "gemini-3.1-flash-image-portrait",
    "gemini-3.1-flash-image-square", "gemini-3.0-pro-image-landscape-2k",
    "gemini-3.1-flash-image-landscape-2k", "imagen-4.0-generate-preview-landscape"
]
VIDEO_MODES = {
    "Text → Video": ("text", "veo_3_1_t2v_fast_landscape"),
    "Image → Video": ("image", "veo_3_1_i2v_s_fast_fl"),
    "First / Last Frame": ("first-last", "veo_3_1_interpolation_lite_landscape"),
    "Reference → Video": ("reference", "veo_3_1_r2v_fast_landscape"),
}

STYLE = """
QWidget { background:#0D121C; color:#E6EDF7; font-family:Segoe UI; font-size:12px; }
QFrame#Sidebar { background:#111A28; border-right:1px solid #293549; }
QFrame#Topbar { background:#111926; border-bottom:1px solid #293549; }
QFrame#Panel { background:#172132; border:1px solid #2B3A51; border-radius:12px; }
QLabel#Title { font-size:22px; font-weight:700; }
QLabel#SubTitle { color:#8FA4BD; font-size:12px; }
QLabel#Brand { font-size:18px; font-weight:800; color:#DCEFFF; }
QLabel#Metric { font-size:27px; font-weight:750; }
QPushButton { background:#223149; padding:9px 13px; border:1px solid #344861; border-radius:8px; color:#E5EDFA; }
QPushButton:hover { background:#324967; }
QPushButton:disabled { background:#1A2433; color:#6F8098; }
QPushButton#Primary { background:#287DD9; border:1px solid #4399F1; font-weight:700; color:white; }
QPushButton#Primary:hover { background:#3991EB; }
QPushButton#Nav { text-align:left; background:transparent; border:0; color:#9CAEC8; padding:12px 14px; border-radius:7px; }
QPushButton#Nav:checked { color:#8AD9FF; background:#213651; border-left:3px solid #46B8FA; font-weight:700; }
QLineEdit,QTextEdit,QComboBox,QSpinBox,QListWidget,QTableWidget {
 background:#101A2A; border:1px solid #34445B; border-radius:7px;
 selection-background-color:#246EA9; padding:7px; color:#E8F1FD; }
QTextEdit { padding:10px; }
QComboBox::drop-down { border:0; width:22px; }
QComboBox QAbstractItemView { background:#1B293A; color:white; }
QHeaderView::section { background:#263247; color:#B4C8DD; border:none; padding:10px; }
QTableWidget { gridline-color:#233247; alternate-background-color:#152238; }
QTableWidget::item { padding:4px; }
QScrollBar:vertical { background:#141D2A; width:10px; }
QScrollBar::handle:vertical { background:#415573; border-radius:5px; }
QGroupBox { border:1px solid #2B3A51; border-radius:9px; margin-top:14px; padding:12px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; padding:0 8px; color:#BFD3EB; }
QCheckBox { color:#AFC4D9; }
"""

def label(text, title=False):
    widget = QLabel(text)
    if title:
        widget.setObjectName("Title")
    else:
        widget.setObjectName("SubTitle")
    widget.setWordWrap(True)
    return widget


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("Primary")
    item.clicked.connect(callback)
    return item


def panel_layout():
    box = QFrame()
    box.setObjectName("Panel")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)
    return box, layout


def line_title(title, subtitle, right=None):
    row = QHBoxLayout()
    column = QVBoxLayout()
    column.addWidget(label(title, title=True))
    column.addWidget(label(subtitle))
    row.addLayout(column, 1)
    if right:
        row.addWidget(right)
    return row


class CallThread(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            self.done.emit(self.callback())
        except Exception as err:
            self.failed.emit(str(err))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.store.recover()
        self.settings = load_settings()
        self.secrets = SecretStore()
        self.worker = None
        self.threads = []
        self.setWindowTitle(f"{APP_NAME} · {__version__}")
        self.resize(1360, 825)
        self.setMinimumSize(940, 620)
        self.setStyleSheet(STYLE)
        self._layout()
        self.reload_projects()
        self.refresh_all()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(5000)

    def _layout(self):
        wrapper = QWidget()
        self.setCentralWidget(wrapper)
        root = QHBoxLayout(wrapper)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(205)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(12, 20, 12, 14)
        left.setSpacing(4)
        brand = QLabel("✦  NVB AI Studio")
        brand.setObjectName("Brand")
        left.addWidget(brand)
        left.addWidget(label("Creative Workspace · v" + __version__))
        left.addSpacing(16)
        self.navs = []
        tabs = [
            ("◫   Tổng quan", self.make_home),
            ("▧   Xưởng tạo ảnh", self.make_images),
            ("▶   Xưởng tạo video", self.make_video),
            ("♙   Nhân vật AI", self.make_characters),
            ("▦   Storyboard", self.make_story),
            ("≋   Hàng đợi", self.make_queue),
            ("▣   Thư viện", self.make_library),
            ("◎   Tài khoản Flow", self.make_accounts),
            ("⚙   Cài đặt", self.make_settings),
        ]
        self.pages = QStackedWidget()
        for i, (name, maker) in enumerate(tabs):
            nav = QPushButton(name)
            nav.setObjectName("Nav")
            nav.setCheckable(True)
            nav.setChecked(i == 0)
            nav.clicked.connect(lambda checked=False, index=i: self.navigate(index))
            left.addWidget(nav)
            self.navs.append(nav)
            self.pages.addWidget(maker())
        left.addStretch(1)
        self.gateway_status = label("● Gateway: Chưa kiểm tra")
        left.addWidget(self.gateway_status)
        root.addWidget(sidebar)
        content = QWidget()
        right = QVBoxLayout(content)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("Topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(22, 9, 22, 9)
        top.addWidget(label("NVB Studio  /  Dự án"), 0)
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(210)
        self.project_combo.currentIndexChanged.connect(self.project_changed)
        top.addWidget(self.project_combo, 0)
        top.addWidget(button("＋ Dự án", self.new_project, primary=True))
        top.addStretch()
        top.addWidget(button("↻ Cập nhật", self.check_update))
        right.addWidget(topbar)
        right.addWidget(self.pages, 1)
        root.addWidget(content, 1)

    def page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 21, 24, 22)
        layout.setSpacing(15)
        return w, layout

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, item in enumerate(self.navs):
            item.setChecked(i == index)
        self.refresh_all()

    def current_project(self):
        return self.project_combo.currentData()

    def project_changed(self, *_):
        if hasattr(self, "char_list"):
            self.refresh_all()

    def reload_projects(self, wanted=None):
        chosen = wanted or self.current_project()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in self.store.projects():
            self.project_combo.addItem(project["name"], project["id"])
        if chosen:
            for n in range(self.project_combo.count()):
                if self.project_combo.itemData(n) == chosen:
                    self.project_combo.setCurrentIndex(n)
                    break
        self.project_combo.blockSignals(False)
        self.refresh_all()

    def new_project(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Dự án mới", "Tên dự án:")
        if ok and name.strip():
            identifier = self.store.create_project(name)
            self.reload_projects(identifier)

    def require_project(self):
        project = self.current_project()
        if not project:
            QMessageBox.warning(self, "Chưa có dự án", "Hãy tạo dự án trước khi thêm nội dung.")
        return project

    def make_home(self):
        w, lay = self.page()
        lay.addLayout(line_title("Không gian sáng tạo", "Toàn bộ quy trình tạo ảnh & video AI trong một màn hình."))
        top, inside = panel_layout()
        inside.addWidget(QLabel("TỪ KỊCH BẢN ĐẾN THÀNH PHẨM"))
        inside.addWidget(label("01 Nhân vật     →     02 Storyboard     →     03 Tạo ảnh     →     04 Video     →     05 Xuất"))
        lay.addWidget(top)
        cards = QHBoxLayout()
        self.metrics = []
        for title in ["Ảnh hoàn thành", "Video hoàn thành", "Tác vụ chờ"]:
            frame, body = panel_layout()
            body.addWidget(label(title))
            number = QLabel("0")
            number.setObjectName("Metric")
            body.addWidget(number)
            cards.addWidget(frame)
            self.metrics.append(number)
        lay.addLayout(cards)
        self.recent = QListWidget()
        lay.addWidget(label("Tác vụ gần đây"))
        lay.addWidget(self.recent)
        return w

    def make_images(self):
        w, lay = self.page()
        lay.addLayout(line_title("Xưởng tạo ảnh hàng loạt", "Nhập danh sách prompt; tự lưu ảnh theo thứ tự và theo dự án.", button("Nhập Excel / TXT", lambda: self.import_text(self.image_prompts))))
        split = QHBoxLayout()
        frame, f = panel_layout()
        f.addWidget(label("Danh sách prompt: mỗi dòng một ảnh, hoặc phân đoạn bằng dòng trống."))
        self.image_prompts = QTextEdit()
        self.image_prompts.setPlaceholderText("Lâm Phong đứng giữa rừng trúc, ánh nắng ban mai...\n\nCảnh tu luyện kiếm pháp trên đỉnh núi...")
        f.addWidget(self.image_prompts, 1)
        self.image_model = QComboBox()
        self.image_model.setEditable(True)
        self.image_model.addItems(IMAGE_MODELS)
        f.addWidget(label("Model ảnh"))
        f.addWidget(self.image_model)
        self.image_char = QComboBox()
        f.addWidget(label("Nhân vật tham chiếu (tùy chọn)"))
        f.addWidget(self.image_char)
        f.addWidget(button("＋ Thêm vào hàng đợi ảnh", self.queue_images, primary=True))
        split.addWidget(frame, 2)
        info, i = panel_layout()
        i.addWidget(label("Cấu hình sản xuất"))
        i.addWidget(QLabel("▧  IMAGE STUDIO"))
        i.addWidget(label("Model mặc định: Nano Banana · 16:9\nCó thể nhập model ID khác nếu sub2gen hỗ trợ."))
        i.addWidget(label("Prompt nhân vật được giữ cố định; chỉ mô tả cảnh thay đổi theo từng tác vụ."))
        i.addWidget(label("Kiểm tra lại ảnh thực tế trước khi duyệt. Độ giống nhân vật không được bảo đảm tuyệt đối."))
        i.addStretch()
        split.addWidget(info, 1)
        lay.addLayout(split, 1)
        return w

    def make_video(self):
        w, lay = self.page()
        lay.addLayout(line_title("Xưởng tạo video AI", "Text-to-video, image-to-video, khung đầu/cuối và ảnh nhân vật."))
        split = QHBoxLayout()
        frame, f = panel_layout()
        self.video_mode = QComboBox()
        self.video_mode.addItems(VIDEO_MODES)
        self.video_mode.currentIndexChanged.connect(self.video_mode_changed)
        f.addWidget(label("Chế độ"))
        f.addWidget(self.video_mode)
        self.video_model = QComboBox()
        self.video_model.setEditable(True)
        self.video_model.addItems([v[1] for v in VIDEO_MODES.values()])
        f.addWidget(label("Model Veo (chọn đúng chế độ)"))
        f.addWidget(self.video_model)
        f.addWidget(label("Prompt video: mỗi đoạn trống ngăn cách một cảnh"))
        self.video_prompts = QTextEdit()
        self.video_prompts.setPlaceholderText("Máy quay tiến gần nhân vật; gió thổi bay tà áo...")
        f.addWidget(self.video_prompts, 1)
        self.video_refs = []
        self.ref_text = label("Chưa chọn khung hình tham chiếu")
        f.addWidget(self.ref_text)
        f.addWidget(button("＋ Chọn ảnh đầu vào", self.choose_video_refs))
        f.addWidget(button("＋ Đưa video vào hàng đợi", self.queue_videos, primary=True))
        split.addWidget(frame, 2)
        info, i = panel_layout()
        i.addWidget(label("Ảnh tham chiếu nhân vật"))
        self.video_char = QComboBox()
        i.addWidget(self.video_char)
        i.addWidget(label("Đối với video Reference, có thể chọn bộ ảnh của nhân vật từ thư viện."))
        i.addWidget(label("Để nối nhiều cảnh, tạo từng video trước rồi mở Thư viện → Ghép video."))
        i.addStretch()
        split.addWidget(info, 1)
        lay.addLayout(split, 1)
        return w

    def video_mode_changed(self, *_):
        mode = self.video_mode.currentText()
        if mode in VIDEO_MODES:
            self.video_model.setCurrentText(VIDEO_MODES[mode][1])

    def make_characters(self):
        w, lay = self.page()
        lay.addLayout(line_title("Thư viện nhân vật AI", "Một bộ ảnh chuẩn và mô tả ngoại hình xuyên suốt mọi cảnh."))
        row = QHBoxLayout()
        left, f = panel_layout()
        self.char_list = QListWidget()
        self.char_list.currentItemChanged.connect(self.show_character)
        f.addWidget(self.char_list)
        f.addWidget(button("Xóa nhân vật đã chọn", self.delete_character))
        row.addWidget(left, 1)
        right, r = panel_layout()
        self.char_name = QLineEdit()
        self.char_name.setPlaceholderText("Tên nhân vật")
        r.addWidget(label("Tên nhân vật"))
        r.addWidget(self.char_name)
        self.char_desc = QTextEdit()
        self.char_desc.setPlaceholderText("Ngoại hình, mái tóc, trang phục, nét nhận diện, phong cách...")
        self.char_desc.setMaximumHeight(140)
        r.addWidget(label("Hồ sơ ngoại hình cố định"))
        r.addWidget(self.char_desc)
        self.char_refs = []
        self.char_refs_label = label("Chưa có ảnh chuẩn")
        r.addWidget(self.char_refs_label)
        r.addWidget(button("Chọn ảnh chính diện / nghiêng / toàn thân", self.choose_char_refs))
        r.addWidget(button("＋ Lưu nhân vật", self.save_character, primary=True))
        self.char_preview = QLabel("Chưa chọn nhân vật")
        self.char_preview.setAlignment(Qt.AlignCenter)
        self.char_preview.setMinimumHeight(130)
        r.addWidget(self.char_preview)
        row.addWidget(right, 2)
        lay.addLayout(row, 1)
        return w

    def make_story(self):
        w, lay = self.page()
        lay.addLayout(line_title("Storyboard / Phân cảnh", "Duyệt thứ tự trước khi gửi vào xưởng tạo ảnh hoặc video."))
        f, body = panel_layout()
        body.addWidget(label("Nhập nội dung theo từng cảnh hoặc chương, ngăn bằng dòng trống."))
        self.story_text = QTextEdit()
        body.addWidget(self.story_text, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Nhập kịch bản", lambda: self.import_text(self.story_text)))
        actions.addWidget(button("→ Xưởng ảnh", lambda: self.story_to("image"), primary=True))
        actions.addWidget(button("→ Xưởng video", lambda: self.story_to("video")))
        body.addLayout(actions)
        lay.addWidget(f, 1)
        return w

    def make_queue(self):
        w, lay = self.page()
        lay.addLayout(line_title("Hàng đợi thông minh", "Lưu trạng thái trong SQLite; không gửi lại job từ xa chưa xác định.", button("▶ Bắt đầu", self.start_worker, primary=True)))
        actions = QHBoxLayout()
        actions.addWidget(button("Tạm dừng / Tiếp tục", self.toggle_pause))
        actions.addWidget(button("■ Dừng sau tác vụ hiện tại", self.stop_worker))
        actions.addWidget(button("↻ Thử lại tác vụ đã chọn", self.retry_job))
        actions.addWidget(button("Xóa mục đã chọn", self.remove_job))
        actions.addStretch()
        lay.addLayout(actions)
        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels(["#", "Dự án", "Loại", "Trạng thái", "Model", "Chi tiết / Lỗi"])
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.queue_table.setAlternatingRowColors(True)
        lay.addWidget(self.queue_table, 1)
        self.queue_msg = label("Sẵn sàng.")
        lay.addWidget(self.queue_msg)
        return w

    def make_library(self):
        w, lay = self.page()
        lay.addLayout(line_title("Thư viện thành phẩm", "Xem kết quả từ dự án hiện tại. Đã lưu sẽ không bị xóa khi thử lại tác vụ."))
        self.library_table = QTableWidget(0, 4)
        self.library_table.setHorizontalHeaderLabels(["#", "Loại", "Đường dẫn", "Model"])
        self.library_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.library_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.library_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.library_table, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(button("Mở file được chọn", self.open_library_file))
        buttons.addWidget(button("Mở thư mục xuất", self.open_output_folder))
        buttons.addWidget(button("Ghép video đã tạo", self.merge_project_videos, primary=True))
        lay.addLayout(buttons)
        return w

    def make_accounts(self):
        w, lay = self.page()
        lay.addLayout(line_title("Đăng nhập Google Flow", "Dùng Chrome đang đăng nhập sẵn — không cài repo hoặc nhập token thủ công."))
        frame, body = panel_layout()
        body.addWidget(label(
            "1. Bấm Kết nối Chrome: ứng dụng tự chuẩn bị sub2gen và tạo khóa kết nối.\n"
            "2. Bấm CHUẨN BỊ & MỞ THƯ MỤC TIỆN ÍCH — app tự giải nén và mở thư mục chứa manifest.json.\n"
            "3. Chrome → chrome://extensions → bật Developer mode → Load unpacked → chọn cả THƯ MỤC đó.\n"
            "4. Mở sub2gen Worker → Options → My account → dán khóa rồi Import/Sync account.\n"
            "5. Quay lại app bấm Kiểm tra tài khoản; các lần sau tái sử dụng tiện ích đã cấp quyền.\n\n"
            "Lưu ý: Chrome không cho chương trình khác đọc phiên đăng nhập hiện tại mà chưa được cấp quyền."
        ))
        self.auto_login_button = button("◎  KẾT NỐI VỚI CHROME ĐANG MỞ", self.login_with_chrome, primary=True)
        body.addWidget(self.auto_login_button)
        self.auto_progress = label("Sẵn sàng. Tiện ích Chrome đã nằm trong gói Setup; bạn không phải tải trên GitHub.")
        body.addWidget(self.auto_progress)
        body.addWidget(label("Thư mục tiện ích có sẵn trong máy (Chrome chọn THƯ MỤC, không chọn file manifest.json):"))
        self.extension_folder_edit = QLineEdit()
        self.extension_folder_edit.setReadOnly(True)
        from .config import data_dir
        self.extension_folder_edit.setText(str(data_dir() / "engine" / "chrome-extension"))
        self.extension_folder_edit.setToolTip("App sẽ tự chuẩn bị và xác minh đủ tệp trước khi mở thư mục.")
        body.addWidget(self.extension_folder_edit)
        row = QHBoxLayout()
        row.addWidget(button("① CHUẨN BỊ & MỞ THƯ MỤC TIỆN ÍCH", self.open_extension_setup, primary=True))
        row.addWidget(button("Sao chép đường dẫn thư mục", self.copy_extension_folder))
        body.addLayout(row)
        rowkey = QHBoxLayout()
        rowkey.addWidget(button("② Mở trang tiện ích trong Chrome", self.open_chrome_extensions))
        rowkey.addWidget(button("③ Sao chép khóa kết nối", self.copy_extension_key))
        body.addLayout(rowkey)
        row2 = QHBoxLayout()
        row2.addWidget(button("③ Kiểm tra tài khoản Flow", self.check_flow_account, primary=True))
        row2.addWidget(button("Mở Google Flow", self.open_flow))
        body.addLayout(row2)
        self.account_status = label("Chưa kết nối tài khoản.")
        body.addWidget(self.account_status)
        lay.addWidget(frame)

        advanced, more = panel_layout()
        more.addWidget(label("Nâng cao: chỉ dùng khi bạn đã có gateway riêng"))
        self.gateway_edit = QLineEdit()
        more.addWidget(label("Gateway URL"))
        more.addWidget(self.gateway_edit)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        more.addWidget(label("API Key (ứng dụng sẽ tự điền ở chế độ Chrome)"))
        more.addWidget(self.key_edit)
        self.remember = QCheckBox("Ghi nhớ khóa trong Windows Credential Manager")
        more.addWidget(self.remember)
        actions = QHBoxLayout()
        actions.addWidget(button("Lưu nâng cao", self.save_connection))
        actions.addWidget(button("Kiểm tra Gateway", self.test_connection))
        more.addLayout(actions)
        lay.addWidget(advanced)
        lay.addStretch()
        QTimer.singleShot(0, self.load_connection)
        return w

    def login_with_chrome(self):
        from .engine import EngineManager
        if getattr(self, "_flow_setup_thread", None) and self._flow_setup_thread.isRunning():
            return
        manager = EngineManager()
        self._flow_engine = manager
        self.auto_login_button.setEnabled(False)
        self.auto_progress.setText("Đang chuẩn bị sub2gen tích hợp; lần đầu cần kết nối Internet...")
        class EngineThread(QThread):
            notice = pyqtSignal(str)
            ready = pyqtSignal(str)
            failed = pyqtSignal(str)
            def run(inner):
                try:
                    manager.start(inner.notice.emit)
                    inner.ready.emit(manager.managed_key())
                except Exception as exc:
                    inner.failed.emit(str(exc))
        self._flow_setup_thread = EngineThread(self)
        self._flow_setup_thread.notice.connect(self.auto_progress.setText)
        self._flow_setup_thread.ready.connect(self.flow_ready)
        self._flow_setup_thread.failed.connect(self.flow_failed)
        self._flow_setup_thread.finished.connect(lambda: self.auto_login_button.setEnabled(True))
        self._flow_setup_thread.start()

    def flow_ready(self, key):
        from .engine import BASE_URL
        self.settings["gateway_url"] = BASE_URL
        save_settings(self.settings)
        self.secrets.set(key, remember=True)
        self.gateway_edit.setText(BASE_URL)
        self.key_edit.setText(key)
        self.remember.setChecked(True)
        self.auto_progress.setText(
            "Engine sẵn sàng. Đang mở thư mục tiện ích Chrome đi kèm Setup."
        )
        self.account_status.setText(
            "Chưa đồng bộ Google Flow; hãy tải tiện ích trong Chrome và chọn Import/Sync."
        )
        self.open_extension_setup()

    def flow_failed(self, reason):
        self.auto_progress.setText("Không khởi động được engine: " + reason[:500])
        QMessageBox.warning(self, "Kết nối Flow", reason[:1800])

    def open_extension_setup(self):
        """Prepare from the installed payload and reveal the REAL folder."""
        from .engine import EngineManager
        try:
            folder = EngineManager().extension_folder()
            self.extension_folder_edit.setText(str(folder))
            QApplication.clipboard().setText(str(folder))
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                QMessageBox.warning(self, "Không mở được thư mục",
                    "Đã chuẩn bị tiện ích nhưng Windows không mở Explorer. "
                    "Bạn có thể sao chép đường dẫn hiển thị phía trên.")
                return
            self.auto_progress.setText(
                "ĐÃ TÌM THẤY tiện ích (manifest.json, background.js...). "
                "Đường dẫn đã sao chép. Mở Chrome → chrome://extensions → bật "
                "Chế độ nhà phát triển → Tải tiện ích đã giải nén → chọn THƯ MỤC đang mở."
            )
            self.account_status.setText(
                "Tiện ích đã có trên máy. Chờ bạn cho phép Chrome tải tiện ích, rồi đồng bộ tài khoản."
            )
        except Exception as exc:
            self.auto_progress.setText("Không chuẩn bị được tiện ích: " + str(exc)[:350])
            QMessageBox.warning(self, "Thiếu tiện ích Chrome",
                "App chưa tạo được thư mục tiện ích từ Setup. "
                "Không cần tìm tải trên GitHub.\n\n" + str(exc)[:1000])

    def copy_extension_folder(self):
        from .engine import EngineManager
        try:
            folder = EngineManager().extension_folder()
            self.extension_folder_edit.setText(str(folder))
            QApplication.clipboard().setText(str(folder))
            self.auto_progress.setText("Đã sao chép đường dẫn THƯ MỤC (không phải file manifest.json).")
        except Exception as exc:
            QMessageBox.warning(self, "Tiện ích Chrome", str(exc))

    def open_chrome_extensions(self):
        from .engine import open_chrome_page
        try:
            open_chrome_page("chrome://extensions/")
        except Exception as exc:
            QMessageBox.warning(self, "Chrome", str(exc))

    def copy_extension_key(self):
        key = self.secrets.get()
        if not key:
            QMessageBox.information(self, "Chưa có khóa", "Bấm Kết nối với Chrome trước.")
            return
        QApplication.clipboard().setText(key)
        self.auto_progress.setText("Khóa đã sao chép. Mở sub2gen Worker → Options, chọn My account, dán API Key, Save rồi Import/Sync account. Không dán khóa vào website lạ.")

    def open_flow(self):
        from .engine import open_chrome_page
        try:
            open_chrome_page("https://flow.google.com/")
        except Exception as exc:
            QMessageBox.warning(self, "Chrome", str(exc))

    def check_flow_account(self):
        from .engine import EngineManager
        self.account_status.setText("Đang kiểm tra tài khoản...")
        def verify():
            health = Gateway(self.settings["gateway_url"], self.secrets.get()).health()
            accounts = EngineManager().bind_available_accounts()
            return health, accounts
        self.async_call(verify, self.flow_account_status, "Kiểm tra Flow")

    def flow_account_status(self, result):
        health, account_count = result
        self.gateway_status.setText("● Gateway: Hoạt động")
        if account_count:
            self.account_status.setText(f"Đã đồng bộ {account_count} tài khoản; có thể tạo ảnh thử.")
        else:
            self.account_status.setText("Engine đang chạy, nhưng chưa có tài khoản. Hãy mở extension, kết nối API key và Import/Sync account.")

    def make_settings(self):
        w, lay = self.page()
        lay.addLayout(line_title("Cài đặt hệ thống", "Lưu trên thiết bị Windows. Thay đổi không ảnh hưởng job đang chạy."))
        frame, f = panel_layout()
        self.output_edit = QLineEdit()
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.output_edit, 1)
        dir_row.addWidget(button("Chọn thư mục", self.choose_output_dir))
        f.addWidget(label("Thư mục xuất"))
        f.addLayout(dir_row)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 4)
        f.addWidget(label("Số tác vụ song song (giới hạn 1–4; tùy credits và provider)"))
        f.addWidget(self.concurrency)
        self.ffmpeg_edit = QLineEdit()
        f.addWidget(label("Đường dẫn FFmpeg hoặc tên lệnh ffmpeg trong PATH"))
        f.addWidget(self.ffmpeg_edit)
        f.addWidget(button("Lưu cài đặt", self.save_preferences, primary=True))
        f.addWidget(button("Kiểm tra bản cập nhật", self.check_update))
        f.addWidget(label("Tải bản setup mới qua GitHub Releases. App không tự ghi đè bộ cài đang chạy."))
        lay.addWidget(frame)
        lay.addStretch()
        QTimer.singleShot(0, self.load_preferences)
        return w

    def choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu kết quả", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def load_preferences(self):
        self.output_edit.setText(self.settings["output_dir"])
        self.concurrency.setValue(int(self.settings["concurrency"]))
        self.ffmpeg_edit.setText(self.settings.get("ffmpeg", "ffmpeg"))

    def save_preferences(self):
        self.settings["output_dir"] = self.output_edit.text().strip()
        self.settings["concurrency"] = self.concurrency.value()
        self.settings["ffmpeg"] = self.ffmpeg_edit.text().strip() or "ffmpeg"
        save_settings(self.settings)
        QMessageBox.information(self, "Đã lưu", "Cấu hình đã được lưu.")

    def load_connection(self):
        self.gateway_edit.setText(self.settings["gateway_url"])
        key = self.secrets.get()
        self.key_edit.setText(key)
        self.remember.setChecked(bool(key))

    def save_connection(self):
        url = self.gateway_edit.text().strip().rstrip("/")
        # Verify URL policy before saving.
        try:
            Gateway(url, self.key_edit.text())
        except Exception as exc:
            QMessageBox.warning(self, "Sai URL", str(exc))
            return
        self.settings["gateway_url"] = url
        save_settings(self.settings)
        self.secrets.set(self.key_edit.text().strip(), self.remember.isChecked())
        self.account_status.setText("Đã lưu. Bấm Kiểm tra Gateway để thử kết nối.")

    def async_call(self, fn, on_success, title="Thao tác"):
        thread = CallThread(fn, self)
        self.threads.append(thread)
        thread.done.connect(on_success)
        thread.failed.connect(lambda e: QMessageBox.warning(self, title, e))
        thread.finished.connect(lambda: self.threads.remove(thread) if thread in self.threads else None)
        thread.start()

    def test_connection(self):
        try:
            self.save_connection()
            gateway = Gateway(self.settings["gateway_url"], self.secrets.get())
        except Exception as exc:
            QMessageBox.warning(self, "Kết nối", str(exc))
            return
        self.account_status.setText("Đang kiểm tra kết nối...")
        self.async_call(gateway.health, self.health_result, "Kiểm tra Gateway")

    def health_result(self, result):
        text = json.dumps(result, ensure_ascii=False)[:450]
        self.gateway_status.setText("● Gateway: Hoạt động")
        self.account_status.setText("Đã kết nối: " + text)

    def import_text(self, target):
        path, _ = QFileDialog.getOpenFileName(self, "Nhập prompt", "",
                                              "Prompts (*.txt *.csv *.xlsx *.xlsm *.json)")
        if not path:
            return
        try:
            prompts = read_prompts(path)
            if not prompts:
                raise ValueError("Không tìm thấy prompt hợp lệ.")
            target.setPlainText("\n\n".join(prompts))
            QMessageBox.information(self, "Đã nhập", f"Đã đọc {len(prompts)} prompt.")
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi import", str(exc))

    def prompts(self, textedit):
        text = textedit.toPlainText().strip()
        if not text:
            return []
        chunks = [s.strip() for s in text.split("\n\n") if s.strip()]
        return chunks if len(chunks) > 1 else [s.strip() for s in text.splitlines() if s.strip()]

    def current_character(self, combo):
        identifier = combo.currentData()
        return next((c for c in self.store.characters(self.current_project()) if c["id"] == identifier), None) if identifier else None

    def apply_character(self, prompts, character):
        if not character:
            return prompts, []
        consistency = "\nCHARACTER REFERENCE / KEEP CONSISTENT: " + character["name"] + ". " + character["description"]
        return [p + consistency for p in prompts], json.loads(character["refs_json"])

    def queue_images(self):
        project = self.require_project()
        if not project:
            return
        prompts = self.prompts(self.image_prompts)
        prompts, refs = self.apply_character(prompts, self.current_character(self.image_char))
        if not prompts:
            QMessageBox.warning(self, "Thiếu prompt", "Hãy nhập ít nhất một prompt.")
            return
        model = self.image_model.currentText().strip()
        count = self.store.add_jobs(project, "image", "reference" if refs else "text", model, prompts, refs[:3])
        self.refresh_all()
        QMessageBox.information(self, "Đã thêm", f"{count} tác vụ ảnh đã vào hàng đợi. Mở Hàng đợi để chạy.")

    def choose_video_refs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn 1–3 ảnh", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if files:
            self.video_refs = files[:3]
            self.ref_text.setText(" · ".join(Path(p).name for p in self.video_refs))

    def queue_videos(self):
        project = self.require_project()
        if not project:
            return
        mode = VIDEO_MODES[self.video_mode.currentText()][0]
        refs = self.video_refs[:]
        char = self.current_character(self.video_char)
        if mode == "reference" and not refs and char:
            refs = json.loads(char["refs_json"])[:3]
        if mode == "text":
            refs = []
        if mode == "image" and len(refs) != 1:
            QMessageBox.warning(self, "Ảnh đầu vào", "Image-to-video cần đúng một ảnh.")
            return
        if mode == "first-last" and len(refs) != 2:
            QMessageBox.warning(self, "Ảnh đầu/cuối", "Hãy chọn đúng hai ảnh.")
            return
        if mode == "reference" and not 1 <= len(refs) <= 3:
            QMessageBox.warning(self, "Ảnh tham chiếu", "Chọn 1–3 ảnh hoặc một nhân vật có ảnh chuẩn.")
            return
        prompts = self.prompts(self.video_prompts)
        if char:
            prompts, _ = self.apply_character(prompts, char)
        if not prompts:
            QMessageBox.warning(self, "Thiếu prompt", "Hãy nhập ít nhất một prompt video.")
            return
        count = self.store.add_jobs(project, "video", mode, self.video_model.currentText().strip(), prompts, refs)
        self.refresh_all()
        QMessageBox.information(self, "Đã thêm", f"{count} video đã vào hàng đợi.")

    def choose_char_refs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh nhân vật", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if files:
            self.char_refs = files[:3]
            self.char_refs_label.setText(" · ".join(Path(p).name for p in self.char_refs))

    def save_character(self):
        project = self.require_project()
        if not project:
            return
        name = self.char_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Thiếu tên", "Nhập tên nhân vật.")
            return
        if not self.char_refs:
            QMessageBox.warning(self, "Thiếu ảnh", "Hãy thêm tối thiểu một ảnh chuẩn.")
            return
        from uuid import uuid4
        folder = data_dir() / "characters" / uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        saved = []
        for index, file in enumerate(self.char_refs):
            src = Path(file)
            if not src.is_file() or src.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                QMessageBox.warning(self, "Ảnh sai", f"Ảnh không hợp lệ: {file}")
                return
            dest = folder / (str(index + 1) + src.suffix.lower())
            shutil.copy2(src, dest)
            saved.append(str(dest))
        self.store.create_character(project, name, self.char_desc.toPlainText(), saved)
        self.char_name.clear()
        self.char_desc.clear()
        self.char_refs = []
        self.char_refs_label.setText("Chưa có ảnh")
        self.refresh_all()

    def delete_character(self):
        item = self.char_list.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Xóa nhân vật", "Xóa hồ sơ này khỏi dự án?") != QMessageBox.Yes:
            return
        self.store.delete_character(item.data(Qt.UserRole))
        self.refresh_all()

    def show_character(self, current, previous=None):
        self.char_preview.setText("Chọn nhân vật để xem ảnh.")
        if not current:
            return
        characters = self.store.characters(self.current_project())
        record = next((c for c in characters if c["id"] == current.data(Qt.UserRole)), None)
        if not record:
            return
        refs = json.loads(record["refs_json"])
        if refs and Path(refs[0]).exists():
            pm = QPixmap(refs[0])
            self.char_preview.setPixmap(pm.scaled(220, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.char_preview.setText("Không tìm thấy ảnh tham chiếu.")

    def story_to(self, kind):
        prompts = self.prompts(self.story_text)
        if not prompts:
            QMessageBox.warning(self, "Thiếu nội dung", "Hãy nhập kịch bản/phân cảnh.")
            return
        target = self.image_prompts if kind == "image" else self.video_prompts
        target.setPlainText("\n\n".join(prompts))
        self.navigate(1 if kind == "image" else 2)

    def start_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.pause(False)
            return
        if not self.store.jobs(status="queued"):
            QMessageBox.information(self, "Hàng đợi trống", "Chưa có tác vụ cần chạy.")
            return
        key = self.secrets.get()
        if not key:
            QMessageBox.warning(self, "API key", "Hãy kết nối API key sub2gen ở Tài khoản Flow.")
            self.navigate(7)
            return
        self.worker = BatchWorker(self.store, self.settings, key, self)
        self.worker.changed.connect(self.refresh_all)
        self.worker.message.connect(self.queue_msg.setText)
        self.worker.finished.connect(self.refresh_all)
        self.worker.start()

    def toggle_pause(self):
        if self.worker and self.worker.isRunning():
            value = not self.worker.pause_flag.is_set()
            self.worker.pause(value)
            self.queue_msg.setText("Đã tạm dừng nhận tác vụ mới." if value else "Đã tiếp tục.")

    def stop_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.queue_msg.setText("Đang dừng theo dõi; job từ xa sẽ được giữ ID để phục hồi.")

    def selected_job_id(self):
        row = self.queue_table.currentRow()
        return self.queue_table.item(row, 0).data(Qt.UserRole) if row >= 0 and self.queue_table.item(row, 0) else None

    def retry_job(self):
        identifier = self.selected_job_id()
        if identifier:
            self.store.requeue(identifier)
            self.refresh_all()

    def remove_job(self):
        identifier = self.selected_job_id()
        if identifier and QMessageBox.question(self, "Xóa tác vụ", "Xóa mục này khỏi hàng đợi?") == QMessageBox.Yes:
            self.store.delete_job(identifier)
            self.refresh_all()

    def library_path(self):
        row = self.library_table.currentRow()
        return self.library_table.item(row, 2).text() if row >= 0 and self.library_table.item(row, 2) else None

    def open_library_file(self):
        path = self.library_path()
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "Không tìm thấy file", "Chọn một file có sẵn trong thư viện.")

    def open_output_folder(self):
        folder = Path(self.settings["output_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def merge_project_videos(self):
        project = self.require_project()
        if not project:
            return
        jobs = [j for j in self.store.jobs(project) if j["kind"] == "video" and
                j["status"] == "completed" and Path(j["output"]).exists()]
        if len(jobs) < 2:
            QMessageBox.warning(self, "Thiếu video", "Cần ít nhất hai video đã hoàn thành.")
            return
        jobs.sort(key=lambda j: j["sequence"])
        project_name = self.store.project(project)["name"]
        output, _ = QFileDialog.getSaveFileName(
            self, "Xuất video ghép", str(Path(self.settings["output_dir"]) / (slug(project_name) + "_merged.mp4")),
            "Video MP4 (*.mp4)")
        if not output:
            return
        srcs = [j["output"] for j in jobs]
        self.async_call(lambda: str(combine_videos(srcs, output, self.settings.get("ffmpeg", "ffmpeg"))),
                        lambda result: QMessageBox.information(self, "Ghép thành công", result),
                        "Lỗi ghép video")

    def check_update(self):
        import requests
        def request():
            r = requests.get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                             headers={"Accept": "application/vnd.github+json"}, timeout=12)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        self.async_call(request, self.show_update, "Cập nhật")

    def show_update(self, result):
        if not result:
            QMessageBox.information(self, "Cập nhật", "Chưa có bản phát hành chính thức trên GitHub Releases.")
            return
        from packaging.version import Version, InvalidVersion
        tag = str(result.get("tag_name", "")).lstrip("v")
        try:
            newer = Version(tag) > Version(__version__)
        except InvalidVersion:
            newer = tag != __version__
        if not newer:
            QMessageBox.information(self, "Cập nhật", f"Đã ở bản mới nhất: {__version__}.")
            return
        if QMessageBox.question(self, "Có bản mới", f"Phiên bản {tag} đã phát hành. Tải bộ cài Windows mới?") == QMessageBox.Yes:
            installers = [a for a in result.get("assets", []) if a.get("name", "").lower().endswith(".exe")]
            url = installers[0]["browser_download_url"] if installers else result["html_url"]
            QDesktopServices.openUrl(QUrl(url))

    def refresh_all(self):
        if not hasattr(self, "metrics"):
            return
        project = self.current_project() if hasattr(self, "project_combo") else None
        all_jobs = self.store.jobs()
        selected = [j for j in all_jobs if j["project_id"] == project] if project else []
        self.metrics[0].setText(str(sum(j["kind"] == "image" and j["status"] == "completed" for j in all_jobs)))
        self.metrics[1].setText(str(sum(j["kind"] == "video" and j["status"] == "completed" for j in all_jobs)))
        self.metrics[2].setText(str(sum(j["status"] == "queued" for j in all_jobs)))
        self.recent.clear()
        for job in reversed(all_jobs[-12:]):
            self.recent.addItem(f"{job['project_name']} | {job['kind']} #{job['sequence']} | {job['status']}")
        self.refresh_combos()
        # Preserve queue selection across refresh.
        previous = self.selected_job_id()
        self.queue_table.setRowCount(0)
        for job in list(reversed(all_jobs))[:300]:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            cells = [str(job["sequence"]), job["project_name"], job["kind"], job["status"],
                     job["model"], job["error"] or job["output"] or job["remote_id"] or "—"]
            for col, val in enumerate(cells):
                cell = QTableWidgetItem(val)
                if col == 0:
                    cell.setData(Qt.UserRole, job["id"])
                self.queue_table.setItem(row, col, cell)
                if col == 0 and previous == job["id"]:
                    self.queue_table.selectRow(row)
        self.library_table.setRowCount(0)
        for job in selected:
            if job["status"] != "completed" or not job["output"]:
                continue
            row = self.library_table.rowCount()
            self.library_table.insertRow(row)
            for col, val in enumerate((str(job["sequence"]), job["kind"], job["output"], job["model"])):
                self.library_table.setItem(row, col, QTableWidgetItem(val))
        # Character rows are refreshed only on change to avoid selection flicker.
        chars = self.store.characters(project) if project else []
        current_ids = [self.char_list.item(i).data(Qt.UserRole) for i in range(self.char_list.count())]
        if current_ids != [c["id"] for c in chars]:
            self.char_list.clear()
            for character in chars:
                item = QListWidgetItem(character["name"] + "  ·  " + character["description"][:65])
                item.setData(Qt.UserRole, character["id"])
                self.char_list.addItem(item)

    def refresh_combos(self):
        project = self.current_project()
        chars = self.store.characters(project) if project else []
        for combo in (self.image_char, self.video_char):
            chosen = combo.currentData()
            ids = [combo.itemData(i) for i in range(combo.count())]
            new_ids = [None] + [c["id"] for c in chars]
            if ids == new_ids:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Không chọn nhân vật", None)
            for char in chars:
                combo.addItem(char["name"], char["id"])
            index = combo.findData(chosen)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(self, "Đang sản xuất",
                "Có tác vụ đang chạy. Đóng app sẽ ngừng theo dõi và lưu ID để tiếp tục. Bạn chắc chắn muốn đóng?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.stop()
            self.worker.wait(5000)
            if self.worker.isRunning():
                event.ignore()
                QMessageBox.warning(self, "Đang dừng", "Hãy thử đóng sau khi worker dừng.")
                return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
