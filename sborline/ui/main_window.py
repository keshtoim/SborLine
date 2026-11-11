from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import services
from ..codes import ROLE_TITLES
from .admin import UsersPage
from .dashboard import DashboardPage
from .orders import OrdersPage
from .refs import RefsPage
from .reports import ReportsPage
from .timesheet import TimesheetPage
from .widgets import Context, label

# разделы по ролям: (подпись, фабрика страницы)
ROLE_PAGES = {
    "master": [("Сводка", DashboardPage), ("Наряды", OrdersPage), ("Табель", TimesheetPage),
               ("Ведомость", ReportsPage), ("Справочники", RefsPage)],
    "worker": [("Мои наряды", lambda ctx: OrdersPage(ctx, worker=True))],
    "accountant": [("Ведомость", ReportsPage), ("Табель", TimesheetPage)],
    "admin": [("Сводка", DashboardPage), ("Справочники", RefsPage), ("Пользователи", UsersPage)],
}


class MainWindow(QMainWindow):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.logged_out = False
        self.setWindowTitle("СборЛайн — учёт работы сборочного цеха")
        self.resize(1280, 800)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(220)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(12, 16, 12, 16)
        side_lay.setSpacing(4)
        brand = QHBoxLayout()
        brand.addWidget(label("СЛ", "brandMark"))
        brand.addWidget(label("СборЛайн", "brand"))
        brand.addStretch()
        side_lay.addLayout(brand)
        side_lay.addSpacing(16)

        self.stack = QStackedWidget()
        self.pages = []
        self.group = group = QButtonGroup(self)
        for i, (title, make_page) in enumerate(ROLE_PAGES[ctx.user["role"]]):
            page = make_page(ctx)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            self.pages.append(page)
            btn = QPushButton(title)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            group.addButton(btn, i)
            side_lay.addWidget(btn)
        group.idClicked.connect(self._open)

        side_lay.addStretch()
        who = services.employee(ctx.conn, ctx.user["employee_id"])["short_name"] if ctx.user["employee_id"] else ctx.user["login"]
        side_lay.addWidget(label(who))
        side_lay.addWidget(label(ROLE_TITLES[ctx.user["role"]]))
        logout = QPushButton("Выйти")
        logout.setObjectName("logout")
        logout.clicked.connect(self._logout)
        side_lay.addSpacing(6)
        side_lay.addWidget(logout)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        if self.pages:
            self._open(0)

    def _open(self, index: int) -> None:
        self.group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        self.pages[index].refresh()

    def _logout(self) -> None:
        self.logged_out = True
        self.close()
