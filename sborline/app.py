import sys
from datetime import date

from PySide6.QtWidgets import QApplication, QDialog

from . import db
from .seed import seed_demo
from .ui.login import LoginDialog
from .ui.main_window import MainWindow
from .ui.widgets import Context


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(db._resource("ui/style.qss").read_text(encoding="utf-8"))
    conn = db.connect(db.default_path())
    db.init_schema(conn)
    today = date.today()
    # первый запуск: пустая база заполняется демо-данными за текущий месяц
    if db.is_empty(conn):
        seed_demo(conn, today)

    # после «Выйти» снова показываем окно входа
    while True:
        login = LoginDialog(conn)
        if login.exec() != QDialog.Accepted:
            break
        window = MainWindow(Context(conn, login.user, today))
        window.show()
        app.exec()
        if not window.logged_out:
            break
    conn.close()


if __name__ == "__main__":
    main()
