import sys
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.ui.styles import get_qss
from src.utils.config import load_config


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Star Helper")
    theme = load_config().get("theme", "dark")
    app.setStyleSheet(get_qss(theme))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
