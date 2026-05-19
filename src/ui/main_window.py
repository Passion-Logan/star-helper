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
    def __init__(self, on_login):
        super().__init__()
        self.setObjectName("loginView")
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

        self.code_label = QLabel("")
        self.code_label.setProperty("role", "codeBadge")
        self.code_label.setFont(QFont("Consolas", 20))
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setVisible(False)
        panel_layout.addWidget(self.code_label)

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
        self.verification_url = url
        self.code_label.setText(code)
        self.code_label.setVisible(True)
        self.info_label.setText("请在浏览器中输入上方验证码完成授权")
        self.link_btn.setText(url)
        self.link_btn.setVisible(True)
        QDesktopServices.openUrl(QUrl(url))

    def _open_verification_url(self):
        if self.verification_url:
            QDesktopServices.openUrl(QUrl(self.verification_url))

    def on_token(self, token):
        self.on_login(token)

    def on_error(self, msg):
        self.info_label.setText(f"错误: {msg}")
        self.login_btn.setEnabled(True)


class TagCheckDialog(QDialog):
    def __init__(self, all_tags, current_tag_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置标签")
        self.setMinimumWidth(250)
        layout = QVBoxLayout(self)
        self.checks = []
        if not all_tags:
            empty = QLabel("还没有自定义标签，请先在左侧创建标签。")
            empty.setProperty("role", "muted")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        for tag in all_tags:
            cb = QCheckBox(tag["name"])
            cb.setChecked(tag["id"] in current_tag_ids)
            cb.tag_id = tag["id"]
            self.checks.append(cb)
            layout.addWidget(cb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_ids(self):
        return [cb.tag_id for cb in self.checks if cb.isChecked()]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Star Helper")
        self.setMinimumSize(900, 600)
        self.token = None
        self.current_stars = []
        self.current_tag_filter = None
        self._fetch_thread = None
        self._unstar_threads = {}
        self._sync_incremental = False

        cfg = load_config()
        self._theme = cfg.get("theme", "dark")

        db.init_db()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_widget = LoginWidget(self.on_login)
        self.stack.addWidget(self.login_widget)

        self.main_widget = self._build_main_ui()
        self.stack.addWidget(self.main_widget)

        token = get_saved_token()
        if token:
            self.on_login(token)

        self.statusBar().showMessage("就绪")

    # ─── Build UI ───────────────────────────────────────────────

    def _build_main_ui(self):
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
        self.tag_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.tag_list.setDefaultDropAction(Qt.MoveAction)
        self.tag_list.setDragEnabled(True)
        self.tag_list.setAcceptDrops(True)
        self.tag_list.setDropIndicatorShown(True)
        self.tag_list.currentRowChanged.connect(self._on_tag_selected)
        self.tag_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self._tag_context_menu)
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
        splitter.setSizes([230, 480, 520])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        return widget

    def _decorate_button(self, button, variant="secondary"):
        button.setProperty("variant", variant)
        button.setCursor(Qt.PointingHandCursor)

    # ─── Theme ──────────────────────────────────────────────────

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        QApplication.instance().setStyleSheet(get_qss(self._theme))
        self.theme_btn.setText("浅色模式" if self._theme == "dark" else "深色模式")
        cfg = load_config()
        cfg["theme"] = self._theme
        save_config(cfg)

    # ─── Login / Logout ─────────────────────────────────────────

    def on_login(self, token):
        self.token = token
        self.stack.setCurrentIndex(1)
        self._refresh_tags()
        self._refresh_languages()
        self._refresh_stars()
        self.statusBar().showMessage("已登录")

    def _do_logout(self):
        self._stop_background_threads()
        logout()
        self.token = None
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        self._stop_background_threads()
        super().closeEvent(event)

    # ─── Sync ───────────────────────────────────────────────────

    def _sync_stars(self):
        self._start_sync(incremental=False)

    def _sync_incremental_stars(self):
        self._start_sync(incremental=True)

    def _start_sync(self, incremental=False):
        if not self.token:
            return
        since = db.get_latest_starred_at() if incremental else ""
        self._sync_incremental = bool(since)
        label = "增量同步" if self._sync_incremental else "同步"
        self.statusBar().showMessage(f"正在{label} Stars...")
        self._fetch_thread = FetchStarsThread(self.token, since_starred_at=since)
        self._fetch_thread.progress.connect(lambda p, _, name=label: self.statusBar().showMessage(f"{name}中... 第{p}页"))
        self._fetch_thread.finished.connect(self._on_stars_fetched)
        self._fetch_thread.error.connect(lambda e, name=label: self.statusBar().showMessage(f"{name}失败: {e}"))
        self._fetch_thread.start()

    def _on_stars_fetched(self, stars):
        db.upsert_stars(stars)
        deleted_count = 0
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
        saved = self.current_tag_filter
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        all_item = QListWidgetItem("全部")
        all_item.setFlags(all_item.flags() & ~Qt.ItemIsDragEnabled)
        self.tag_list.addItem(all_item)
        untagged_item = QListWidgetItem("未分类")
        untagged_item.setFlags(untagged_item.flags() & ~Qt.ItemIsDragEnabled)
        self.tag_list.addItem(untagged_item)
        target_row = 0
        if saved == 0:
            target_row = 1
        for i, tag in enumerate(db.get_all_tags()):
            item = QListWidgetItem(f"{tag['name']}  {tag['count']}")
            item.setData(Qt.UserRole, tag["id"])
            self.tag_list.addItem(item)
            if saved == tag["id"]:
                target_row = i + 2
        self.tag_list.setCurrentRow(target_row)
        self.tag_list.blockSignals(False)
        self._on_tag_selected(target_row)

    def _on_tag_selected(self, row):
        if row == 0:
            self.current_tag_filter = None
        elif row == 1:
            self.current_tag_filter = 0
        else:
            item = self.tag_list.item(row)
            self.current_tag_filter = item.data(Qt.UserRole) if item else None
        self._refresh_stars()

    def _add_tag(self):
        name, ok = QInputDialog.getText(self, "新标签", "标签名称:")
        if ok and name.strip():
            db.create_tag(name.strip())
            self._refresh_tags()

    def _tag_context_menu(self, pos):
        item = self.tag_list.itemAt(pos)
        row = self.tag_list.row(item) if item else -1
        if row < 2:
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
        QTimer.singleShot(0, self._save_tag_order_from_ui)

    def _save_tag_order_from_ui(self):
        tag_ids = []
        for row in range(self.tag_list.count()):
            tag_id = self.tag_list.item(row).data(Qt.UserRole)
            if tag_id:
                tag_ids.append(tag_id)
        if tag_ids:
            db.update_tag_order(tag_ids)
            self._refresh_tags()

    # ─── Stars ──────────────────────────────────────────────────

    def _refresh_languages(self):
        self.lang_combo.blockSignals(True)
        current = self.lang_combo.currentData()
        self.lang_combo.clear()
        self.lang_combo.addItem("所有语言", "")
        for lang in db.get_languages():
            self.lang_combo.addItem(lang, lang)
        if current:
            idx = self.lang_combo.findData(current)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)

    def _refresh_stars(self):
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
            meta_parts = []
            if star["language"]:
                meta_parts.append(star["language"])
            if star["starred_at"]:
                meta_parts.append(star["starred_at"][:10])
            meta = " · ".join(meta_parts) or "无语言信息"
            desc = (star["description"] or "无描述").strip()
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
            empty_title = "没有匹配的仓库" if search or language or self.current_tag_filter is not None else "还没有同步仓库"
            self._show_empty_detail(empty_title)

    def _on_star_selected(self, row):
        if row < 0 or row >= len(self.current_stars):
            return
        star = self.current_stars[row]
        self.detail_name.setText(f"<a href='{star['url']}'>{star['full_name']}</a>")
        self.detail_desc.setText(star["description"] or "无描述")

        # Topics chips
        self._clear_flow_layout(self.topics_layout)
        topics = star.get("topics") or []
        if topics:
            for t in topics:
                self.topics_layout.addWidget(make_chip(
                    t,
                    on_click=lambda topic=t: self._filter_by_topic(topic),
                    tooltip="点击按该 topic 搜索",
                ))
        else:
            self.topics_layout.addWidget(self._muted_label("无 GitHub topics"))

        # Tags chips
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

        # Note
        self.note_edit.setPlainText(db.get_note(star["id"]))

    def _filter_by_topic(self, topic):
        self.search_input.setText(topic)
        self.statusBar().showMessage(f"已按 topic 搜索: {topic}")

    def _remove_tag_from_current_star(self, star_id, tag_id):
        row = self.star_list.currentRow()
        if row < 0 or row >= len(self.current_stars):
            return
        current_star = self.current_stars[row]
        if current_star["id"] != star_id:
            return
        db.remove_star_tag(star_id, tag_id)
        self._refresh_tags()
        self._refresh_stars()
        row = self.star_list.currentRow()
        if 0 <= row < len(self.current_stars):
            self._on_star_selected(row)
        self.statusBar().showMessage("已从当前仓库移除标签")

    def _stop_background_threads(self):
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.requestInterruption()
            self._wait_or_terminate_thread(self._fetch_thread, 5000)

        login_thread = getattr(self.login_widget, "thread", None)
        if login_thread and login_thread.isRunning():
            login_thread.requestInterruption()
            self._wait_or_terminate_thread(login_thread, 7000)

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
        if thread.wait(timeout_ms):
            return
        thread.terminate()
        thread.wait(3000)

    def _show_empty_detail(self, title):
        self.detail_name.setText(title)
        self.detail_desc.setText("同步或调整筛选条件后，在左侧列表选择仓库查看详情。")
        self._clear_flow_layout(self.topics_layout)
        self.topics_layout.addWidget(self._muted_label("无内容"))
        self._clear_flow_layout(self.tags_layout)
        self.tags_layout.addWidget(self._muted_label("无内容"))
        self.note_edit.clear()

    @staticmethod
    def _muted_label(text):
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    # ─── Multi-select / Batch ───────────────────────────────────

    def _on_selection_changed(self):
        count = len(self.star_list.selectedItems())
        if count > 1:
            self.batch_widget.setVisible(True)
            self.batch_label.setText(f"已选 {count} 项")
        else:
            self.batch_widget.setVisible(False)

    def _batch_set_tags(self):
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
        if star["full_name"] in self._unstar_threads:
            self.statusBar().showMessage("正在取消 Star，请稍候")
            return
        ret = QMessageBox.question(
            self,
            "取消 Star",
            f"确认在 GitHub 上取消 star：{star['full_name']}？",
            QMessageBox.Yes | QMessageBox.No,
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
        star = next((item for item in self.current_stars if item["full_name"] == full_name), None)
        deleted = False
        if star:
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
        self._unstar_threads.pop(full_name, None)
        self.statusBar().showMessage(f"取消 Star 失败: {msg}")

    # ─── Notes ──────────────────────────────────────────────────

    def _save_note(self):
        row = self.star_list.currentRow()
        if row < 0:
            return
        star = self.current_stars[row]
        db.save_note(star["id"], self.note_edit.toPlainText())
        self.statusBar().showMessage("备注已保存")

    # ─── Import / Export ────────────────────────────────────────

    def _export_json(self):
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
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.statusBar().showMessage(f"已导出到 {path}")

    def _import_json(self):
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
            summary += f"。{len(set(missing_stars))} 个仓库本地不存在,已跳过"
        self.statusBar().showMessage(summary)

    # ─── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _clear_flow_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
