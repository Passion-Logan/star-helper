"""应用主题 QSS。"""

DARK_QSS = """
QWidget {
    background-color: #080A0F;
    color: #F8FAFC;
    font-family: "Inter", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 10pt;
}

QWidget#appShell, QWidget#loginView {
    background-color: #080A0F;
}

QFrame#sidebar {
    background-color: #10141D;
    border-right: 1px solid #2E3A4D;
}

QFrame#contentPane {
    background-color: #0B0F17;
    border-right: 1px solid #2E3A4D;
}

QFrame#detailPane {
    background-color: #111722;
}

QFrame#loginPanel {
    background-color: #111722;
    border: 1px solid #334155;
    border-radius: 14px;
}

QFrame#batchBar {
    background-color: #0F1D35;
    border: 1px solid #2563EB;
    border-radius: 10px;
}

QSplitter::handle {
    background: #1E293B;
}

QSplitter::handle:hover {
    background: #3B82F6;
}

QLabel {
    background: transparent;
}

QLabel#brandTitle, QLabel#loginTitle, QLabel#paneTitle {
    color: #FFFFFF;
    letter-spacing: 0;
}

QLabel#detailName {
    color: #FFFFFF;
    line-height: 1.35;
}

QLabel#detailName a {
    color: #93C5FD;
    text-decoration: none;
}

QLabel[role="muted"] {
    color: #B6C2D2;
}

QLabel[role="meta"] {
    color: #D7E3F4;
    font-weight: 600;
}

QLabel[role="sectionTitle"] {
    color: #93A4B8;
    font-size: 8.5pt;
    font-weight: 700;
    text-transform: uppercase;
}

QLabel[role="codeBadge"] {
    color: #FDE68A;
    background-color: #2A210B;
    border: 1px solid #B7791F;
    border-radius: 10px;
    padding: 12px 18px;
}

QLabel[role="chip"] {
    background-color: #172554;
    color: #BFDBFE;
    border: 1px solid #2563EB;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}

QLineEdit, QComboBox, QTextEdit, QListWidget {
    background-color: #0F1520;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 10px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}

QLineEdit, QComboBox {
    min-height: 36px;
    padding: 0 12px;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #60A5FA;
}

QTextEdit {
    padding: 10px;
    line-height: 1.55;
}

QTextEdit#noteEdit {
    background-color: #0F1520;
}

QListWidget {
    outline: none;
    padding: 6px;
}

QListWidget#tagList {
    background-color: transparent;
    border: none;
    padding: 0;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 8px;
    color: #DCE7F5;
}

QListWidget::item:hover {
    background-color: #172033;
    color: #FFFFFF;
}

QListWidget::item:selected {
    background-color: #1D4ED8;
    color: #FFFFFF;
}

QListWidget#repoList::item {
    padding: 12px 12px;
    margin: 2px 0;
    border-bottom: 1px solid #1E293B;
}

QListWidget#repoList::item:selected {
    background-color: #12357F;
    border: 1px solid #60A5FA;
}

QPushButton {
    min-height: 34px;
    padding: 0 14px;
    border-radius: 9px;
    border: 1px solid #334155;
    background-color: #151C2A;
    color: #F8FAFC;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1E293B;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #0F172A;
}

QPushButton:focus {
    border: 1px solid #60A5FA;
}

QPushButton:disabled {
    background-color: #1D2430;
    color: #64748B;
    border-color: #2B3544;
}

QPushButton[variant="primary"] {
    background-color: #2563EB;
    border-color: #3B82F6;
    color: #FFFFFF;
}

QPushButton[variant="primary"]:hover {
    background-color: #1D4ED8;
    border-color: #60A5FA;
}

QPushButton[variant="secondary"] {
    background-color: #111827;
    border-color: #334155;
    color: #EAF2FF;
}

QPushButton[variant="ghost"] {
    background-color: transparent;
    border-color: transparent;
    color: #B6C2D2;
}

QPushButton[variant="ghost"]:hover {
    background-color: #172033;
    border-color: #334155;
    color: #FFFFFF;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #0F1520;
    border: 1px solid #334155;
    selection-background-color: #2563EB;
    outline: none;
}

QMenu {
    background-color: #0F1520;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 28px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: #1D4ED8;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #64748B;
    border-radius: 4px;
    background: #0F1520;
}

QCheckBox::indicator:checked {
    background: #2563EB;
    border-color: #60A5FA;
}

QStatusBar {
    background-color: #10141D;
    color: #B6C2D2;
    border-top: 1px solid #2E3A4D;
}

QStatusBar::item {
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #475569;
    border-radius: 6px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: #64748B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

LIGHT_QSS = """
QWidget {
    background-color: #EEF2F7;
    color: #0F172A;
    font-family: "Inter", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 10pt;
}

QWidget#appShell, QWidget#loginView {
    background-color: #EEF2F7;
}

QFrame#sidebar {
    background-color: #FFFFFF;
    border-right: 1px solid #CBD5E1;
}

QFrame#contentPane {
    background-color: #F8FAFC;
    border-right: 1px solid #CBD5E1;
}

QFrame#detailPane {
    background-color: #FFFFFF;
}

QFrame#loginPanel {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 14px;
}

QFrame#batchBar {
    background-color: #DBEAFE;
    border: 1px solid #60A5FA;
    border-radius: 10px;
}

QSplitter::handle {
    background: #CBD5E1;
}

QSplitter::handle:hover {
    background: #2563EB;
}

QLabel {
    background: transparent;
}

QLabel#brandTitle, QLabel#loginTitle, QLabel#paneTitle {
    color: #020617;
    letter-spacing: 0;
}

QLabel#detailName {
    color: #020617;
    line-height: 1.35;
}

QLabel#detailName a {
    color: #1D4ED8;
    text-decoration: none;
}

QLabel[role="muted"] {
    color: #475569;
}

QLabel[role="meta"] {
    color: #1E293B;
    font-weight: 600;
}

QLabel[role="sectionTitle"] {
    color: #475569;
    font-size: 8.5pt;
    font-weight: 700;
    text-transform: uppercase;
}

QLabel[role="codeBadge"] {
    color: #92400E;
    background-color: #FEF3C7;
    border: 1px solid #F59E0B;
    border-radius: 10px;
    padding: 12px 18px;
}

QLabel[role="chip"] {
    background-color: #DBEAFE;
    color: #1E40AF;
    border: 1px solid #93C5FD;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}

QLineEdit, QComboBox, QTextEdit, QListWidget {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 10px;
    selection-background-color: #BFDBFE;
    selection-color: #1E3A8A;
}

QLineEdit, QComboBox {
    min-height: 36px;
    padding: 0 12px;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #2563EB;
}

QTextEdit {
    padding: 10px;
    line-height: 1.55;
}

QTextEdit#noteEdit {
    background-color: #F8FAFC;
}

QListWidget {
    outline: none;
    padding: 6px;
}

QListWidget#tagList {
    background-color: transparent;
    border: none;
    padding: 0;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 8px;
    color: #1E293B;
}

QListWidget::item:hover {
    background-color: #E2E8F0;
    color: #020617;
}

QListWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}

QListWidget#repoList::item {
    padding: 12px 12px;
    margin: 2px 0;
    border-bottom: 1px solid #E2E8F0;
}

QListWidget#repoList::item:selected {
    background-color: #DBEAFE;
    border: 1px solid #2563EB;
    color: #0F172A;
}

QPushButton {
    min-height: 34px;
    padding: 0 14px;
    border-radius: 9px;
    border: 1px solid #CBD5E1;
    background-color: #FFFFFF;
    color: #0F172A;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #E2E8F0;
    border-color: #94A3B8;
}

QPushButton:pressed {
    background-color: #CBD5E1;
}

QPushButton:focus {
    border: 1px solid #2563EB;
}

QPushButton:disabled {
    background-color: #F2F4F7;
    color: #98A2B3;
    border-color: #E4E7EC;
}

QPushButton[variant="primary"] {
    background-color: #2563EB;
    border-color: #2563EB;
    color: #FFFFFF;
}

QPushButton[variant="primary"]:hover {
    background-color: #1D4ED8;
    border-color: #1D4ED8;
}

QPushButton[variant="secondary"] {
    background-color: #FFFFFF;
    border-color: #CBD5E1;
    color: #0F172A;
}

QPushButton[variant="ghost"] {
    background-color: transparent;
    border-color: transparent;
    color: #475569;
}

QPushButton[variant="ghost"]:hover {
    background-color: #E2E8F0;
    border-color: #CBD5E1;
    color: #0F172A;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    selection-background-color: #BFDBFE;
    outline: none;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 28px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: #DBEAFE;
    color: #1E40AF;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #94A3B8;
    border-radius: 4px;
    background: #FFFFFF;
}

QCheckBox::indicator:checked {
    background: #2563EB;
    border-color: #2563EB;
}

QStatusBar {
    background-color: #FFFFFF;
    color: #475569;
    border-top: 1px solid #CBD5E1;
}

QStatusBar::item {
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #94A3B8;
    border-radius: 6px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: #64748B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def get_qss(theme: str) -> str:
    return DARK_QSS if theme == "dark" else LIGHT_QSS
