"""主窗口及登录界面实现。

界面整体使用 QStackedWidget 在登录页和主工作台之间切换。主工作台为
三栏式布局:左侧标签/工具,中间仓库列表与筛选,右侧详情/备注/标签编辑。
所有耗时的网络操作(同步、取消 star)都放在 QThread 中执行。
"""

import json
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QComboBox, QTextEdit,
    QSplitter, QStackedWidget, QInputDialog, QMessageBox, QMenu,
    QDialog, QDialogButtonBox, QCheckBox, QFileDialog,
    QApplication, QAbstractItemView, QFrame
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont

from src.auth.github_oauth import DeviceFlowThread, get_saved_token, logout
from src.api.github_api import FetchStarsThread, UnstarRepoThread
from src.db import database as db
from src.ui.styles import get_qss
from src.ui.widgets import FlowLayout, make_chip
from src.utils.config import load_config, save_config


class LoginWidget(QWidget):
    """登录页:展示 Device Flow 的验证码与跳转链接,授权完成后回调 on_login。"""

    def __init__(self, on_login):
        super().__init__()
        self.setObjectName("loginView")
        # 父窗口注入的回调,登录成功后用 token 切换到主工作台
        self.on_login = on_login
        self.thread = None
        self.verification_url = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(32, 32, 32, 32)

        panel = QFrame()
        panel.setObjectName("loginPanel")
        panel.setMaximumWidth(460)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(36, 34, 36, 34)
        panel_layout.setSpacing(16)

        title = QLabel("Star Helper")
        title.setObjectName("loginTitle")
        title.setFont(QFont("", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(title)

        self.info_label = QLabel("把 GitHub Stars 整理成可搜索、可标注、可阅读的知识库")
        self.info_label.setProperty("role", "muted")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        panel_layout.addWidget(self.info_label)

        # 验证码 label 平时隐藏,收到 code_received 信号后才显示
        self.code_label = QLabel("")
        self.code_label.setProperty("role", "codeBadge")
        self.code_label.setFont(QFont("Consolas", 20))
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setVisible(False)
        panel_layout.addWidget(self.code_label)

        # 跳转链接按钮:点击会再次唤起浏览器,防止用户首次自动跳转被拦截
        self.link_btn = QPushButton("")
        self.link_btn.setProperty("variant", "ghost")
        self.link_btn.setCursor(Qt.PointingHandCursor)
        self.link_btn.setVisible(False)
        self.link_btn.clicked.connect(self._open_verification_url)
        panel_layout.addWidget(self.link_btn, alignment=Qt.AlignCenter)

        self.login_btn = QPushButton("使用 GitHub 登录")
        self.login_btn.setProperty("variant", "primary")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setFixedWidth(220)
        self.login_btn.clicked.connect(self.start_login)
        panel_layout.addWidget(self.login_btn, alignment=Qt.AlignCenter)

        layout.addWidget(panel)

    def start_login(self):
        """禁用按钮、清理上一轮 UI,启动 Device Flow 线程开始授权。"""
        self.login_btn.setEnabled(False)
        self.code_label.setVisible(False)
        self.link_btn.setVisible(False)
        self.info_label.setText("正在请求授权...")
        self.thread = DeviceFlowThread()
        self.thread.code_received.connect(self.show_code)
        self.thread.token_received.connect(self.on_token)
        self.thread.error.connect(self.on_error)
        self.thread.start()

    def show_code(self, code, url):
        """展示验证码和跳转链接,并自动打开默认浏览器。"""
        self.verification_url = url
        self.code_label.setText(code)
        self.code_label.setVisible(True)
        self.info_label.setText("请在浏览器中输入上方验证码完成授权")
        self.link_btn.setText(url)
        self.link_btn.setVisible(True)
        # 主动唤起浏览器;若被系统拦截用户仍可点击下方链接按钮
        QDesktopServices.openUrl(QUrl(url))

    def _open_verification_url(self):
        """链接按钮的点击处理:再次尝试打开 GitHub 授权页。"""
        if self.verification_url:
            QDesktopServices.openUrl(QUrl(self.verification_url))

    def on_token(self, token):
        """拿到 access token 后回调到 MainWindow 切换界面。"""
        self.on_login(token)

    def on_error(self, msg):
        """Device Flow 失败时显示错误信息并允许用户重试。"""
        self.info_label.setText(f"错误: {msg}")
        self.login_btn.setEnabled(True)


class TagCheckDialog(QDialog):
    """复选框对话框:让用户为一个或一批仓库勾选标签。

    Ok 时通过 selected_ids() 返回勾选项;批量场景下 current_tag_ids 传空列表,
    单个场景传当前已选 id 以便对话框正确预选。
    """

    def __init__(self, all_tags, current_tag_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置标签")
        self.setMinimumWidth(250)
        layout = QVBoxLayout(self)
        self.checks = []
        if not all_tags:
            # 库内无标签时给出友好提示而非空对话框
            empty = QLabel("还没有自定义标签，请先在左侧创建标签。")
            empty.setProperty("role", "muted")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        for tag in all_tags:
            cb = QCheckBox(tag["name"])
            cb.setChecked(tag["id"] in current_tag_ids)
            # 把 tag_id 挂在 widget 上,后续读勾选结果时一并取出
            cb.tag_id = tag["id"]
            self.checks.append(cb)
            layout.addWidget(cb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_ids(self):
        """返回当前勾选的全部标签 id,供调用方写库使用。"""
        return [cb.tag_id for cb in self.checks if cb.isChecked()]


class MainWindow(QMainWindow):
    """应用主窗口:登录态与已登录态通过 QStackedWidget 切换。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Star Helper")
        self.setMinimumSize(900, 600)
        # 当前会话状态
        self.token = None
        self.current_stars = []
        self.current_tag_filter = None
        # 线程引用必须保留为成员,避免被 GC 提前回收导致 Qt 段错误
        self._fetch_thread = None
        # 多个 unstar 操作可并发进行,这里用 dict 按仓库名追踪
        self._unstar_threads = {}
        self._sync_incremental = False

        cfg = load_config()
        self._theme = cfg.get("theme", "dark")

        # 初始化数据库 schema(包含必要的迁移),在 UI 渲染前完成
        db.init_db()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # 索引 0 = 登录,1 = 主工作台;切换通过 stack.setCurrentIndex
        self.login_widget = LoginWidget(self.on_login)
        self.stack.addWidget(self.login_widget)

        self.main_widget = self._build_main_ui()
        self.stack.addWidget(self.main_widget)

        # 已登录用户跳过登录页直接进入主界面
        token = get_saved_token()
        if token:
            self.on_login(token)

        self.statusBar().showMessage("就绪")

    # ─── Build UI ───────────────────────────────────────────────

    def _build_main_ui(self):
        """构建三栏主工作台:左侧导航 / 中间列表 / 右侧详情。"""
        widget = QWidget()
        widget.setObjectName("appShell")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("mainSplitter")
        layout.addWidget(splitter)

        # Left: navigation and global actions
        left = QFrame()
        left.setObjectName("sidebar")
        left.setMinimumWidth(210)
        left.setMaximumWidth(270)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 14, 18)
        left_layout.setSpacing(12)

        brand = QLabel("Star Helper")
        brand.setObjectName("brandTitle")
        brand.setFont(QFont("", 18, QFont.Bold))
        left_layout.addWidget(brand)

        brand_desc = QLabel("GitHub Stars 工作台")
        brand_desc.setProperty("role", "muted")
        left_layout.addWidget(brand_desc)

        nav_title = QLabel("分类")
        nav_title.setProperty("role", "sectionTitle")
        left_layout.addWidget(nav_title)

        self.tag_list = QListWidget()
        self.tag_list.setObjectName("tagList")
        # 启用拖拽内部移动以支持用户自定义标签顺序
        self.tag_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.tag_list.setDefaultDropAction(Qt.MoveAction)
        self.tag_list.setDragEnabled(True)
        self.tag_list.setAcceptDrops(True)
        self.tag_list.setDropIndicatorShown(True)
        self.tag_list.currentRowChanged.connect(self._on_tag_selected)
        self.tag_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self._tag_context_menu)
        # rowsMoved 来自底层 model,拖拽完成时触发持久化新顺序
        self.tag_list.model().rowsMoved.connect(self._on_tag_rows_moved)
        left_layout.addWidget(self.tag_list)

        add_tag_btn = QPushButton("新建标签")
        self._decorate_button(add_tag_btn, "secondary")
        add_tag_btn.clicked.connect(self._add_tag)
        left_layout.addWidget(add_tag_btn)

        tools_title = QLabel("工具")
        tools_title.setProperty("role", "sectionTitle")
        left_layout.addWidget(tools_title)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(8)
        import_btn = QPushButton("导入")
        self._decorate_button(import_btn, "secondary")
        import_btn.clicked.connect(self._import_json)
        tool_row.addWidget(import_btn)

        export_btn = QPushButton("导出")
        self._decorate_button(export_btn, "secondary")
        export_btn.clicked.connect(self._export_json)
        tool_row.addWidget(export_btn)
        left_layout.addLayout(tool_row)

        self.theme_btn = QPushButton("浅色模式" if self._theme == "dark" else "深色模式")
        self._decorate_button(self.theme_btn, "secondary")
        self.theme_btn.setToolTip("切换界面主题")
        self.theme_btn.clicked.connect(self._toggle_theme)
        left_layout.addWidget(self.theme_btn)

        logout_btn = QPushButton("退出登录")
        self._decorate_button(logout_btn, "ghost")
        logout_btn.clicked.connect(self._do_logout)
        left_layout.addWidget(logout_btn)

        splitter.addWidget(left)

        # Middle: repository list
        middle = QFrame()
        middle.setObjectName("contentPane")
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(18, 18, 10, 18)
        middle_layout.setSpacing(12)

        list_header = QHBoxLayout()
        list_header.setSpacing(12)
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        repo_title = QLabel("仓库")
        repo_title.setObjectName("paneTitle")
        repo_title.setFont(QFont("", 17, QFont.Bold))
        title_block.addWidget(repo_title)

        self.repo_count_label = QLabel("0 个仓库")
        self.repo_count_label.setProperty("role", "muted")
        title_block.addWidget(self.repo_count_label)
        list_header.addLayout(title_block)
        list_header.addStretch()

        sync_btn = QPushButton("同步")
        self._decorate_button(sync_btn, "primary")
        sync_btn.clicked.connect(self._sync_stars)
        list_header.addWidget(sync_btn)

        incremental_btn = QPushButton("增量")
        self._decorate_button(incremental_btn, "secondary")
        incremental_btn.setToolTip("只拉取本地最新 star 时间之后新增的项目")
        incremental_btn.clicked.connect(self._sync_incremental_stars)
        list_header.addWidget(incremental_btn)
        middle_layout.addLayout(list_header)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索仓库名称或描述")
        self.search_input.textChanged.connect(self._refresh_stars)
        filter_bar.addWidget(self.search_input, 1)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("所有语言", "")
        self.lang_combo.currentIndexChanged.connect(self._refresh_stars)
        self.lang_combo.setMinimumWidth(142)
        filter_bar.addWidget(self.lang_combo)
        middle_layout.addLayout(filter_bar)

        # Batch toolbar (shown when multi-select)
        self.batch_bar = QHBoxLayout()
        self.batch_bar.setContentsMargins(10, 8, 10, 8)
        self.batch_bar.setSpacing(10)
        self.batch_label = QLabel("")
        self.batch_label.setProperty("role", "meta")
        self.batch_bar.addWidget(self.batch_label)
        self.batch_bar.addStretch()
        batch_tag_btn = QPushButton("批量设置标签")
        self._decorate_button(batch_tag_btn, "secondary")
        batch_tag_btn.clicked.connect(self._batch_set_tags)
        self.batch_bar.addWidget(batch_tag_btn)
        self.batch_widget = QFrame()
        self.batch_widget.setObjectName("batchBar")
        self.batch_widget.setLayout(self.batch_bar)
        self.batch_widget.setVisible(False)
        middle_layout.addWidget(self.batch_widget)

        self.star_list = QListWidget()
        self.star_list.setObjectName("repoList")
        # ExtendedSelection 支持 Ctrl/Shift 多选,与 batch 工具栏联动
        self.star_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.star_list.currentRowChanged.connect(self._on_star_selected)
        self.star_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.star_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.star_list.customContextMenuRequested.connect(self._star_context_menu)
        middle_layout.addWidget(self.star_list, 1)

        splitter.addWidget(middle)

        # Right: detail reader
        detail = QFrame()
        detail.setObjectName("detailPane")
        detail.setMinimumWidth(360)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(10)

        detail_title = QLabel("详情")
        detail_title.setProperty("role", "sectionTitle")
        detail_layout.addWidget(detail_title)

        self.detail_name = QLabel("")
        self.detail_name.setObjectName("detailName")
        self.detail_name.setFont(QFont("", 12, QFont.Bold))
        self.detail_name.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.detail_name.setOpenExternalLinks(True)
        self.detail_name.setWordWrap(True)
        detail_layout.addWidget(self.detail_name)

        self.detail_desc = QLabel("")
        self.detail_desc.setProperty("role", "muted")
        self.detail_desc.setWordWrap(True)
        detail_layout.addWidget(self.detail_desc)

        # Topics chips
        topics_title = QLabel("GitHub Topics")
        topics_title.setProperty("role", "sectionTitle")
        detail_layout.addWidget(topics_title)
        self.topics_container = QWidget()
        self.topics_layout = FlowLayout(self.topics_container, margin=2, h_spacing=4, v_spacing=4)
        detail_layout.addWidget(self.topics_container)

        # Tags chips
        tags_title = QLabel("自定义标签")
        tags_title.setProperty("role", "sectionTitle")
        detail_layout.addWidget(tags_title)
        self.tags_container = QWidget()
        self.tags_layout = FlowLayout(self.tags_container, margin=2, h_spacing=4, v_spacing=4)
        detail_layout.addWidget(self.tags_container)

        # Note
        note_label = QLabel("备注:")
        note_label.setProperty("role", "sectionTitle")
        detail_layout.addWidget(note_label)
        self.note_edit = QTextEdit()
        self.note_edit.setObjectName("noteEdit")
        self.note_edit.setPlaceholderText("添加备注...")
        detail_layout.addWidget(self.note_edit, 1)
        save_note_btn = QPushButton("保存备注")
        self._decorate_button(save_note_btn, "primary")
        save_note_btn.clicked.connect(self._save_note)
        detail_layout.addWidget(save_note_btn)

        splitter.addWidget(detail)
        # 三栏的初始宽度比例:导航较窄,列表与详情各占大头
        splitter.setSizes([230, 480, 520])
        # 导航与列表禁止折叠,避免被用户拖到 0 宽度后丢失功能入口
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        return widget

    def _decorate_button(self, button, variant="secondary"):
        """统一为按钮设置 QSS variant 属性并改成手形光标,避免重复样板代码。"""
        button.setProperty("variant", variant)
        button.setCursor(Qt.PointingHandCursor)

    # ─── Theme ──────────────────────────────────────────────────

    def _toggle_theme(self):
        """切换深浅主题:更新 QSS、刷新按钮文本并持久化偏好。"""
        self._theme = "light" if self._theme == "dark" else "dark"
        QApplication.instance().setStyleSheet(get_qss(self._theme))
        self.theme_btn.setText("浅色模式" if self._theme == "dark" else "深色模式")
        cfg = load_config()
        cfg["theme"] = self._theme
        save_config(cfg)

    # ─── Login / Logout ─────────────────────────────────────────

    def on_login(self, token):
        """登录成功:保存 token,切换到主界面并刷新各类列表。"""
        self.token = token
        self.stack.setCurrentIndex(1)
        self._refresh_tags()
        self._refresh_languages()
        self._refresh_stars()
        self.statusBar().showMessage("已登录")

    def _do_logout(self):
        """登出:先停掉后台线程再清除凭据,避免回调时访问已销毁的 UI。"""
        self._stop_background_threads()
        logout()
        self.token = None
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        """窗口关闭前显式收尾后台线程,防止进程因悬挂线程无法退出。"""
        self._stop_background_threads()
        super().closeEvent(event)

    # ─── Sync ───────────────────────────────────────────────────

    def _sync_stars(self):
        """完整同步:重拉全部 starred 并清理已取消且未整理的旧数据。"""
        self._start_sync(incremental=False)

    def _sync_incremental_stars(self):
        """增量同步:只拉取比本地最新 star 时间更晚的新条目。"""
        self._start_sync(incremental=True)

    def _start_sync(self, incremental=False):
        """启动同步线程并把进度、完成、错误回调挂到状态栏。"""
        if not self.token:
            return
        # 增量模式下取本地最新 starred_at 作为下限;若本地为空则退化为全量
        since = db.get_latest_starred_at() if incremental else ""
        self._sync_incremental = bool(since)
        label = "增量同步" if self._sync_incremental else "同步"
        self.statusBar().showMessage(f"正在{label} Stars...")
        self._fetch_thread = FetchStarsThread(self.token, since_starred_at=since)
        # lambda 中默认参数 name=label 防止后续 label 被改写时影响已绑定的槽
        self._fetch_thread.progress.connect(lambda p, _, name=label: self.statusBar().showMessage(f"{name}中... 第{p}页"))
        self._fetch_thread.finished.connect(self._on_stars_fetched)
        self._fetch_thread.error.connect(lambda e, name=label: self.statusBar().showMessage(f"{name}失败: {e}"))
        self._fetch_thread.start()

    def _on_stars_fetched(self, stars):
        """同步完成回调:写库、按需清理、刷新筛选项与列表。"""
        db.upsert_stars(stars)
        deleted_count = 0
        # 仅完整同步时才修剪本地已取消 star 的项;增量数据不足以判断
        if not self._sync_incremental:
            deleted_count = db.prune_unstarred_unorganized_stars(star["id"] for star in stars)
        self._refresh_languages()
        self._refresh_stars()
        prefix = "增量同步" if self._sync_incremental else "同步"
        message = f"{prefix}完成，共 {len(stars)} 个项目"
        if deleted_count:
            message += f"，已清理 {deleted_count} 个已取消且未整理的项目"
        self.statusBar().showMessage(message)

    # ─── Tags ───────────────────────────────────────────────────

    def _refresh_tags(self):
        """重建标签列表 UI,并尽量保留用户之前选中的过滤项。

        前两行固定为"全部"与"未分类",其余为用户自定义标签(可拖拽排序)。
        """
        # 记下当前过滤,刷新后尝试还原以减少视觉跳变
        saved = self.current_tag_filter
        # 阻断信号防止重建过程中触发 _on_tag_selected 引起额外刷新
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        all_item = QListWidgetItem("全部")
        # 内置项关闭拖拽,避免破坏前两行的特殊语义
        all_item.setFlags(all_item.flags() & ~Qt.ItemIsDragEnabled)
        self.tag_list.addItem(all_item)
        untagged_item = QListWidgetItem("未分类")
        untagged_item.setFlags(untagged_item.flags() & ~Qt.ItemIsDragEnabled)
        self.tag_list.addItem(untagged_item)
        target_row = 0
        # current_tag_filter == 0 表示"未分类"伪标签,对应索引 1
        if saved == 0:
            target_row = 1
        for i, tag in enumerate(db.get_all_tags()):
            item = QListWidgetItem(f"{tag['name']}  {tag['count']}")
            # 把真实 tag id 存进 UserRole,后续选中/拖拽都从这里取
            item.setData(Qt.UserRole, tag["id"])
            self.tag_list.addItem(item)
            if saved == tag["id"]:
                target_row = i + 2
        self.tag_list.setCurrentRow(target_row)
        self.tag_list.blockSignals(False)
        # 信号被阻断时不会自动触发选中处理,这里手动调用一次确保列表同步
        self._on_tag_selected(target_row)

    def _on_tag_selected(self, row):
        """根据用户在左侧的选择更新过滤条件:None=全部,0=未分类,其余=具体 tag。"""
        if row == 0:
            self.current_tag_filter = None
        elif row == 1:
            self.current_tag_filter = 0
        else:
            item = self.tag_list.item(row)
            self.current_tag_filter = item.data(Qt.UserRole) if item else None
        self._refresh_stars()

    def _add_tag(self):
        """弹输入框创建新标签;空白名称视为取消。"""
        name, ok = QInputDialog.getText(self, "新标签", "标签名称:")
        if ok and name.strip():
            db.create_tag(name.strip())
            self._refresh_tags()

    def _tag_context_menu(self, pos):
        """标签的右键菜单:重命名 / 删除;前两行(全部、未分类)不可操作。"""
        item = self.tag_list.itemAt(pos)
        row = self.tag_list.row(item) if item else -1
        if row < 2:
            # 全部、未分类是内置过滤项,没有 tag_id 可操作
            return
        tag_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.tag_list.mapToGlobal(pos))
        if action == rename_action:
            name, ok = QInputDialog.getText(self, "重命名", "新名称:")
            if ok and name.strip():
                db.rename_tag(tag_id, name.strip())
                self._refresh_tags()
        elif action == delete_action:
            db.delete_tag(tag_id)
            self._refresh_tags()

    def _on_tag_rows_moved(self, *_args):
        """rowsMoved 在拖拽过程中可能频繁触发,延迟到下一事件循环再持久化顺序。"""
        QTimer.singleShot(0, self._save_tag_order_from_ui)

    def _save_tag_order_from_ui(self):
        """从 UI 当前顺序读出 tag id 列表写库,并触发一次刷新使计数对齐。"""
        tag_ids = []
        for row in range(self.tag_list.count()):
            tag_id = self.tag_list.item(row).data(Qt.UserRole)
            # 内置行没有 UserRole,自然被跳过
            if tag_id:
                tag_ids.append(tag_id)
        if tag_ids:
            db.update_tag_order(tag_ids)
            self._refresh_tags()

    # ─── Stars ──────────────────────────────────────────────────

    def _refresh_languages(self):
        """重建语言下拉框,尽量保留当前选择以减少筛选意外重置。"""
        self.lang_combo.blockSignals(True)
        current = self.lang_combo.currentData()
        self.lang_combo.clear()
        self.lang_combo.addItem("所有语言", "")
        for lang in db.get_languages():
            self.lang_combo.addItem(lang, lang)
        if current:
            # 之前选过的语言被删除时 findData 返回 -1,则保持"所有语言"默认项
            idx = self.lang_combo.findData(current)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)

    def _refresh_stars(self):
        """根据搜索/语言/标签过滤条件重建仓库列表,并尽力保留选中项。"""
        # 记下当前选中仓库的 full_name,以便重建后回到同一行
        current_row = self.star_list.currentRow()
        current_full_name = None
        if 0 <= current_row < len(self.current_stars):
            current_full_name = self.current_stars[current_row]["full_name"]

        search = self.search_input.text().strip()
        language = self.lang_combo.currentData() or ""
        self.current_stars = db.get_all_stars(search, language, self.current_tag_filter)
        self.star_list.clear()
        if hasattr(self, "repo_count_label"):
            self.repo_count_label.setText(f"{len(self.current_stars)} 个仓库")

        selected_row = -1
        for star in self.current_stars:
            # 拼接副标题:语言 · 日期(只取 yyyy-mm-dd)
            meta_parts = []
            if star["language"]:
                meta_parts.append(star["language"])
            if star["starred_at"]:
                meta_parts.append(star["starred_at"][:10])
            meta = " · ".join(meta_parts) or "无语言信息"
            desc = (star["description"] or "无描述").strip()
            # 描述过长会撑爆列表行,这里截断并加省略号
            if len(desc) > 92:
                desc = desc[:89] + "..."
            item = QListWidgetItem(f"{star['full_name']}\n{meta}    {desc}")
            item.setToolTip(f"{star['full_name']}\n{desc}")
            self.star_list.addItem(item)
            if star["full_name"] == current_full_name:
                selected_row = self.star_list.count() - 1

        if selected_row >= 0:
            self.star_list.setCurrentRow(selected_row)
        elif self.current_stars:
            self._show_empty_detail("选择一个仓库查看详情")
        else:
            # 区分"过滤后无结果"和"从未同步过",给出不同提示
            empty_title = "没有匹配的仓库" if search or language or self.current_tag_filter is not None else "还没有同步仓库"
            self._show_empty_detail(empty_title)

    def _on_star_selected(self, row):
        """单击仓库后填充右侧详情:名称、描述、topics、自定义标签、备注。"""
        if row < 0 or row >= len(self.current_stars):
            return
        star = self.current_stars[row]
        # 用 <a> 包裹让标题本身就是一个外链
        self.detail_name.setText(f"<a href='{star['url']}'>{star['full_name']}</a>")
        self.detail_desc.setText(star["description"] or "无描述")

        # Topics chips:点击其中一个会把搜索框设成该 topic 做快速筛选
        self._clear_flow_layout(self.topics_layout)
        topics = star.get("topics") or []
        if topics:
            for t in topics:
                # 默认参数捕获 topic 值,避免 lambda 闭包 late-binding 问题
                self.topics_layout.addWidget(make_chip(
                    t,
                    on_click=lambda topic=t: self._filter_by_topic(topic),
                    tooltip="点击按该 topic 搜索",
                ))
        else:
            self.topics_layout.addWidget(self._muted_label("无 GitHub topics"))

        # Tags chips:文本后面挂 "×" 提示可点击移除关联
        self._clear_flow_layout(self.tags_layout)
        tags = db.get_star_tags(star["id"])
        if tags:
            for t in tags:
                self.tags_layout.addWidget(make_chip(
                    f"{t['name']} ×",
                    on_click=lambda tag_id=t["id"], star_id=star["id"]: self._remove_tag_from_current_star(star_id, tag_id),
                    tooltip="点击从当前仓库移除该标签",
                ))
        else:
            self.tags_layout.addWidget(self._muted_label("无自定义标签"))

        # 备注
        self.note_edit.setPlainText(db.get_note(star["id"]))

    def _filter_by_topic(self, topic):
        """topic chip 的点击处理:写入搜索框触发列表刷新。"""
        self.search_input.setText(topic)
        self.statusBar().showMessage(f"已按 topic 搜索: {topic}")

    def _remove_tag_from_current_star(self, star_id, tag_id):
        """从当前选中仓库摘掉一个标签;若选中行已变化则忽略以免误操作。"""
        row = self.star_list.currentRow()
        if row < 0 or row >= len(self.current_stars):
            return
        current_star = self.current_stars[row]
        # 期间用户可能切换到了别的仓库,严格校验以保护数据
        if current_star["id"] != star_id:
            return
        db.remove_star_tag(star_id, tag_id)
        self._refresh_tags()
        self._refresh_stars()
        # 刷新后选中行可能换位置,重新填充详情区
        row = self.star_list.currentRow()
        if 0 <= row < len(self.current_stars):
            self._on_star_selected(row)
        self.statusBar().showMessage("已从当前仓库移除标签")

    def _stop_background_threads(self):
        """请求中断并等待所有后台线程结束,登出/关闭前必须调用。"""
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.requestInterruption()
            self._wait_or_terminate_thread(self._fetch_thread, 5000)

        # 登录线程可能正在轮询 token,需要更长的等待时间让 sleep 周期走完
        login_thread = getattr(self.login_widget, "thread", None)
        if login_thread and login_thread.isRunning():
            login_thread.requestInterruption()
            self._wait_or_terminate_thread(login_thread, 7000)

        # 先一次性向所有 unstar 线程发出中断,再统一 wait,缩短总等待时间
        for thread in list(self._unstar_threads.values()):
            if thread.isRunning():
                thread.requestInterruption()
        for full_name, thread in list(self._unstar_threads.items()):
            if thread.isRunning():
                self._wait_or_terminate_thread(thread, 5000)
            if not thread.isRunning():
                self._unstar_threads.pop(full_name, None)

    @staticmethod
    def _wait_or_terminate_thread(thread, timeout_ms):
        """先 wait,超时再强行 terminate;terminate 后再多 wait 一次确保资源释放。"""
        if thread.wait(timeout_ms):
            return
        # terminate 不保证立即结束,且可能造成资源未释放,仅作为最后保险
        thread.terminate()
        thread.wait(3000)

    def _show_empty_detail(self, title):
        """无选中仓库或列表为空时的占位详情区。"""
        self.detail_name.setText(title)
        self.detail_desc.setText("同步或调整筛选条件后，在左侧列表选择仓库查看详情。")
        self._clear_flow_layout(self.topics_layout)
        self.topics_layout.addWidget(self._muted_label("无内容"))
        self._clear_flow_layout(self.tags_layout)
        self.tags_layout.addWidget(self._muted_label("无内容"))
        self.note_edit.clear()

    @staticmethod
    def _muted_label(text):
        """生成带 muted 样式的占位 QLabel,主要用于"无内容"提示。"""
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    # ─── Multi-select / Batch ───────────────────────────────────

    def _on_selection_changed(self):
        """当选中数量大于 1 时显示批量操作工具栏。"""
        count = len(self.star_list.selectedItems())
        if count > 1:
            self.batch_widget.setVisible(True)
            self.batch_label.setText(f"已选 {count} 项")
        else:
            self.batch_widget.setVisible(False)

    def _batch_set_tags(self):
        """批量为多个仓库整体替换标签集合。

        注意这里使用 set_star_tags 而非追加,意味着勾选框反映"目标状态",
        会覆盖原先的标签;批量场景下 current_tag_ids 留空以提示新选择。
        """
        selected_rows = [self.star_list.row(item) for item in self.star_list.selectedItems()]
        if not selected_rows:
            return
        all_tags = db.get_all_tags()
        dlg = TagCheckDialog(all_tags, [], self)
        if dlg.exec():
            tag_ids = dlg.selected_ids()
            for row in selected_rows:
                star = self.current_stars[row]
                db.set_star_tags(star["id"], tag_ids)
            self._refresh_tags()
            self.statusBar().showMessage(f"已为 {len(selected_rows)} 个项目设置标签")

    # ─── Context menu ───────────────────────────────────────────

    def _star_context_menu(self, pos):
        """仓库列表右键菜单:设置标签 / 取消 star / 在浏览器中打开。"""
        item = self.star_list.itemAt(pos)
        row = self.star_list.row(item) if item else -1
        if row < 0:
            return
        star = self.current_stars[row]
        menu = QMenu(self)
        tag_action = menu.addAction("设置标签")
        unstar_action = menu.addAction("取消 Star")
        open_action = menu.addAction("在浏览器中打开")
        action = menu.exec(self.star_list.mapToGlobal(pos))
        if action == tag_action:
            all_tags = db.get_all_tags()
            current_tags = db.get_star_tags(star["id"])
            # 把当前已有标签传给对话框做预选,用户能看到已有状态再调整
            current_ids = [t["id"] for t in current_tags]
            dlg = TagCheckDialog(all_tags, current_ids, self)
            if dlg.exec():
                db.set_star_tags(star["id"], dlg.selected_ids())
                self._refresh_tags()
                self._on_star_selected(row)
        elif action == unstar_action:
            self._unstar_repo(star)
        elif action == open_action:
            QDesktopServices.openUrl(QUrl(star["url"]))

    def _unstar_repo(self, star):
        """向 GitHub 发起取消 star 请求(走后台线程),并先做幂等性与二次确认。"""
        # 同一仓库的请求并发去重,避免重复点击造成重复 API 调用
        if star["full_name"] in self._unstar_threads:
            self.statusBar().showMessage("正在取消 Star，请稍候")
            return
        ret = QMessageBox.question(
            self,
            "取消 Star",
            f"确认在 GitHub 上取消 star：{star['full_name']}？",
            QMessageBox.Yes | QMessageBox.No,
            # 默认按钮设为"否",避免误按回车导致非预期操作
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        self.statusBar().showMessage(f"正在取消 Star: {star['full_name']}")
        thread = UnstarRepoThread(self.token, star["full_name"])
        self._unstar_threads[star["full_name"]] = thread
        thread.finished.connect(self._on_unstar_finished)
        thread.error.connect(self._on_unstar_error)
        thread.start()

    def _on_unstar_finished(self, full_name):
        """GitHub 取消 star 成功:本地是否同步删除取决于该仓库是否被整理过。"""
        star = next((item for item in self.current_stars if item["full_name"] == full_name), None)
        deleted = False
        if star:
            # 仅在没有标签 / 备注时才物理删除,以保留用户的整理成果
            deleted = db.delete_star_if_unorganized(star["id"])
        self._unstar_threads.pop(full_name, None)
        self._refresh_tags()
        self._refresh_languages()
        self._refresh_stars()
        if deleted:
            self.statusBar().showMessage(f"已取消 Star 并从本地移除: {full_name}")
        else:
            self.statusBar().showMessage(f"已取消 GitHub Star，本地因有标签或备注已保留: {full_name}")

    def _on_unstar_error(self, full_name, msg):
        """取消 star 失败时清理线程引用并把错误展示在状态栏。"""
        self._unstar_threads.pop(full_name, None)
        self.statusBar().showMessage(f"取消 Star 失败: {msg}")

    # ─── Notes ──────────────────────────────────────────────────

    def _save_note(self):
        """保存当前选中仓库的备注(空白内容会触发 save_note 内部删除该行)。"""
        row = self.star_list.currentRow()
        if row < 0:
            return
        star = self.current_stars[row]
        db.save_note(star["id"], self.note_edit.toPlainText())
        self.statusBar().showMessage("备注已保存")

    # ─── Import / Export ────────────────────────────────────────

    def _export_json(self):
        """导出标签和备注到 JSON 文件,用 full_name 作为外键以便跨设备迁移。

        注意:仓库本身的元数据(描述、语言等)是从 GitHub 拉来的,导出时
        无需备份,只导出用户产生的整理数据(标签关联 + 备注)。
        """
        path, _ = QFileDialog.getSaveFileName(self, "导出", "star_helper_data.json", "JSON (*.json)")
        if not path:
            return
        tags = db.get_all_tags()
        data = {"tags": [], "notes": []}
        conn = db.get_conn()
        # Export tags with star full_names
        for tag in tags:
            rows = conn.execute(
                "SELECT s.full_name FROM stars s JOIN star_tags st ON s.id=st.star_id WHERE st.tag_id=?",
                (tag["id"],)
            ).fetchall()
            data["tags"].append({"name": tag["name"], "stars": [r["full_name"] for r in rows]})
        # Export notes
        rows = conn.execute(
            "SELECT s.full_name, n.content FROM notes n JOIN stars s ON s.id=n.star_id"
        ).fetchall()
        conn.close()
        for r in rows:
            data["notes"].append({"full_name": r["full_name"], "content": r["content"]})
        with open(path, "w", encoding="utf-8") as f:
            # ensure_ascii=False 保留中文备注的可读性
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.statusBar().showMessage(f"已导出到 {path}")

    def _import_json(self):
        """从 JSON 文件导入标签与备注,以 full_name 关联到本地已有的仓库。

        若本地缺失某个 full_name(尚未同步或已取消 star),会记录到 missing_stars
        在末尾汇总提示,而不是直接报错。
        """
        path, _ = QFileDialog.getOpenFileName(self, "导入", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("JSON 根节点应为对象")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            QMessageBox.warning(self, "导入失败", f"无法读取文件: {e}")
            return

        # 统计三类计数,导入完成后回显给用户
        tag_count = 0
        assoc_count = 0
        note_count = 0
        missing_stars = []
        try:
            conn = db.get_conn()
            for tag_data in data.get("tags", []):
                name = tag_data.get("name")
                if not name:
                    continue
                # 同名标签视为合并而非冲突
                conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
                tag_row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
                if not tag_row:
                    continue
                tag_count += 1
                tag_id = tag_row["id"]
                for full_name in tag_data.get("stars", []):
                    star_row = conn.execute(
                        "SELECT id FROM stars WHERE full_name=?", (full_name,)
                    ).fetchone()
                    if star_row:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO star_tags (star_id, tag_id) VALUES (?,?)",
                            (star_row["id"], tag_id)
                        )
                        # rowcount > 0 才代表新建立了关联,用于过滤重复导入
                        if cur.rowcount:
                            assoc_count += 1
                    else:
                        missing_stars.append(full_name)
            for note_data in data.get("notes", []):
                full_name = note_data.get("full_name")
                content = note_data.get("content", "")
                if not full_name:
                    continue
                star_row = conn.execute(
                    "SELECT id FROM stars WHERE full_name=?", (full_name,)
                ).fetchone()
                if star_row:
                    # 备注采用 REPLACE,使本地若有同仓库备注会被覆盖为导入内容
                    conn.execute(
                        "INSERT OR REPLACE INTO notes (star_id, content) VALUES (?,?)",
                        (star_row["id"], content)
                    )
                    note_count += 1
                else:
                    missing_stars.append(full_name)
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"写入数据库时出错: {e}")
            return

        self._refresh_tags()
        self._refresh_stars()
        summary = f"已导入 {tag_count} 个标签、{assoc_count} 个关联、{note_count} 条备注"
        if missing_stars:
            # 去重计数:同一缺失仓库可能既出现在 tags 又在 notes 中
            summary += f"。{len(set(missing_stars))} 个仓库本地不存在,已跳过"
        self.statusBar().showMessage(summary)

    # ─── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _clear_flow_layout(layout):
        """清空 FlowLayout 中的全部子部件,用于在切换详情时重建 chip 列表。"""
        while layout.count():
            item = layout.takeAt(0)
            # deleteLater 让 Qt 在事件循环空闲时回收,避免在槽函数中即刻 delete
            if item.widget():
                item.widget().deleteLater()
