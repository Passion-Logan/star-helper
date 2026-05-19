"""Star Helper 应用入口：初始化 Qt 应用、加载主题并启动主窗口。"""

import sys
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.ui.styles import get_qss
from src.utils.config import load_config


def main():
    """构建 QApplication，根据用户配置应用主题样式后展示主窗口。"""
    app = QApplication(sys.argv)
    app.setApplicationName("Star Helper")
    # 从配置读取主题偏好；首次启动或缺失时默认使用 dark 主题
    theme = load_config().get("theme", "dark")
    app.setStyleSheet(get_qss(theme))
    window = MainWindow()
    window.show()
    # exec() 返回 Qt 事件循环的退出码，传给 sys.exit 以便正确反馈给操作系统
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
