from sqlite3 import Connection

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout

from ..auth import authenticate
from .widgets import label, primary


class LoginDialog(QDialog):
    def __init__(self, conn: Connection):
        super().__init__()
        self.conn = conn
        self.user = None
        self.setWindowTitle("СборЛайн — вход")
        self.setFixedWidth(400)

        card = QFrame()
        card.setObjectName("panel")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)

        brand = QHBoxLayout()
        brand.addWidget(label("СЛ", "brandMark"))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("СборЛайн", "h2"))
        titles.addWidget(label("Учёт работы сотрудников сборочного цеха", "muted"))
        brand.addLayout(titles)
        brand.addStretch()
        lay.addLayout(brand)

        self.login = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("Логин", self.login)
        form.addRow("Пароль", self.password)
        lay.addLayout(form)

        self.error = label("", "error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)

        btn = primary("Войти")
        btn.setDefault(True)
        btn.clicked.connect(self._try_login)
        lay.addWidget(btn)
        lay.addWidget(label("Демо-учётки (пароль = логин): belova — мастер, petrov — сборщик, "
                            "buh — бухгалтер, admin — администратор.", "muted", wrap=True))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(card, alignment=Qt.AlignTop)
        self.login.setFocus()

    def _try_login(self) -> None:
        user = authenticate(self.conn, self.login.text(), self.password.text())
        if user is None:
            self.error.setText("Неверный логин или пароль, либо учётная запись отключена.")
            self.error.show()
            self.password.clear()
            self.password.setFocus()
            return
        self.user = user
        self.accept()
