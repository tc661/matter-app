from PySide6.QtWidgets import (QLabel, QMenu, QApplication,
                               QScrollArea, QWidget, QVBoxLayout)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

class ImageLabel(QLabel):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(pixmap)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        copy_action = menu.addAction("Copy Image")
        action = menu.exec(event.globalPos())
        if action == copy_action:
            QApplication.clipboard().setPixmap(self._pixmap)

class ImageTab(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)


        label = ImageLabel(pixmap)
        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        self.setLayout(layout)