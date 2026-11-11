from dataclasses import dataclass
from datetime import date
from sqlite3 import Connection, Row

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

STATUS_COLORS = {1: "#3a5f9a", 2: "#a8690f", 3: "#0e6a70", 4: "#2c7a4b"}


@dataclass
class Context:
    conn: Connection
    user: Row
    today: date


def rub(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def num(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def ddmm(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}"


def item(text, right=False, color=None, bold=False, data=None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    if data is not None:
        it.setData(Qt.UserRole, data)
    return it


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.horizontalHeader().setHighlightSections(False)
    return t


def fill_table(table: QTableWidget, rows: list[list[QTableWidgetItem]], stretch_col: int | None = None) -> None:
    table.setRowCount(len(rows))
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            table.setItem(r, c, cell)
    table.resizeColumnsToContents()
    if stretch_col is not None:
        table.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)


def label(text: str, name: str | None = None, wrap=False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def page_header(eyebrow: str, title: str, *buttons: QWidget) -> tuple[QHBoxLayout, QLabel, QLabel]:
    box = QHBoxLayout()
    titles = QVBoxLayout()
    titles.setSpacing(2)
    eb = label(eyebrow.upper(), "eyebrow")
    h2 = label(title, "h2")
    titles.addWidget(eb)
    titles.addWidget(h2)
    box.addLayout(titles)
    box.addStretch()
    for b in buttons:
        box.addWidget(b, alignment=Qt.AlignBottom)
    return box, eb, h2


def primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("primary")
    return b


def warn(parent: QWidget, text: str) -> None:
    QMessageBox.warning(parent, "СборЛайн", text)


class Page(QWidget):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("page")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(14)

    def refresh(self) -> None:
        raise NotImplementedError


class Tile(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        lay.addWidget(label(title.upper(), "eyebrow"))
        self.value = label("", "tileValue")
        self.sub = label("", "muted")
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)


class Panel(QFrame):
    def __init__(self, title: str, note: str = ""):
        super().__init__()
        self.setObjectName("panel")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 14)
        self.body.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label(title, "panelTitle"))
        head.addStretch()
        if note:
            head.addWidget(label(note, "muted"))
        self.body.addLayout(head)


class MonthBar(QWidget):
    changed = Signal(int, int)

    def __init__(self, today: date):
        super().__init__()
        self.year, self.month = today.year, today.month
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        prev_btn, next_btn = QPushButton("◀"), QPushButton("▶")
        prev_btn.setFixedWidth(36)
        next_btn.setFixedWidth(36)
        self.caption = QLabel()
        self.caption.setMinimumWidth(120)
        self.caption.setAlignment(Qt.AlignCenter)
        f = QFont(self.caption.font())
        f.setBold(True)
        self.caption.setFont(f)
        prev_btn.clicked.connect(lambda: self._shift(-1))
        next_btn.clicked.connect(lambda: self._shift(1))
        lay.addWidget(prev_btn)
        lay.addWidget(self.caption)
        lay.addWidget(next_btn)
        self._update_caption()

    def _shift(self, delta: int) -> None:
        m = self.year * 12 + self.month - 1 + delta
        self.year, self.month = divmod(m, 12)
        self.month += 1
        self._update_caption()
        self.changed.emit(self.year, self.month)

    def _update_caption(self) -> None:
        self.caption.setText(f"{MONTHS[self.month - 1]} {self.year}")
