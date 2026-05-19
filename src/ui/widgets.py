"""UI 小部件:FlowLayout(自动换行布局)和 chip 标签生成。"""

from PySide6.QtWidgets import QLabel, QLayout, QSizePolicy, QStyle
from PySide6.QtCore import Qt, QRect, QSize, QPoint


class FlowLayout(QLayout):
    """从左到右排列、超出宽度自动换行的布局。改编自 Qt 官方示例。

    Qt 内置的 QHBoxLayout / QVBoxLayout 都不支持"溢出时换行",而标签 chip 这种
    数量不固定的元素需要一个能自适应宽度的容器。这里实现 QLayout 的虚函数以
    支持 heightForWidth,使外层 QScrollArea 能正确推算所需高度。
    """

    def __init__(self, parent=None, margin=0, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        # 横向与纵向间距分别配置,以便外观调优
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def __del__(self):
        # 显式回收 LayoutItem,避免 Qt 在某些时序下重复释放底层 widget
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        # 不主动占据多余空间,行为类似一个收缩到内容大小的容器
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        # 关键:声明高度依赖宽度,父布局才会在窄屏下给我们更高的高度
        return True

    def heightForWidth(self, width):
        # test_only=True 仅用于推算高度,不真正调整子部件位置
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        # 最小尺寸取所有子元素 minimumSize 的逐元素最大值,加上外边距
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        """核心布局算法:逐项摆放,溢出右边界时换到下一行。返回总占用高度。"""
        m = self.contentsMargins()
        # 扣除内边距后得到真实可用区域
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            wid = item.widget()
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            # 当前行已无足够宽度,且行内至少有一个元素时换行
            # line_height > 0 的判断避免单个超宽元素无限换行
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            # 一行的高度由该行最高的元素决定
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + m.bottom()


def make_chip(text, on_click=None, tooltip=None) -> QLabel:
    """生成一个 chip 风格的 QLabel(实际样式由 QSS 根据 role 属性控制)。

    使用 QLabel 而非 QPushButton 是为了减少视觉噪音并允许 FlowLayout 准确推算
    尺寸;点击行为通过劫持 mousePressEvent 实现,使外观仍是纯文本。
    """
    label = QLabel(text)
    # 通过 dynamic property 让 QSS 的 [role="chip"] 选择器命中
    label.setProperty("role", "chip")
    label.setAlignment(Qt.AlignCenter)
    if tooltip:
        label.setToolTip(tooltip)
    if on_click is not None:
        label.setCursor(Qt.PointingHandCursor)

        # 闭包中默认参数捕获 handler,避免循环中复用 make_chip 时绑定到同一引用
        def _mouse_press(_event, handler=on_click):
            handler()
        label.mousePressEvent = _mouse_press
    return label
