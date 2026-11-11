import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sborline import auth, codes, db, services  # noqa: E402
from sborline.ui.dialogs import NewOrderDialog, ReportDialog  # noqa: E402
from sborline.ui.main_window import ROLE_PAGES, MainWindow  # noqa: E402
from sborline.ui.widgets import Context  # noqa: E402

from .conftest import TODAY  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(db._resource("ui/style.qss").read_text(encoding="utf-8"))
    return a


def _ctx(conn, login):
    return Context(conn, auth.authenticate(conn, login, login), TODAY)


@pytest.mark.parametrize("login", ["belova", "petrov", "buh", "admin"])
def test_every_page_renders(app, conn, login):
    win = MainWindow(_ctx(conn, login))
    assert len(win.pages) == len(ROLE_PAGES[win.ctx.user["role"]])
    for i in range(len(win.pages)):
        win._open(i)


def test_timesheet_double_click_cycles_code(app, conn):
    from sborline.ui.timesheet import TOTALS, TimesheetPage
    page = TimesheetPage(_ctx(conn, "belova"))
    page.refresh()
    row = page.emp_ids.index(1)
    page._cycle(row, TOTALS + 2)  # 2 ноября
    assert services.timesheet_month(conn, 2026, 11)[(1, "2026-11-02")][0] == "Б"
    assert page.table.item(row, TOTALS + 2).text() == "Б"


def test_dialogs_save(app, conn):
    ctx = _ctx(conn, "belova")
    dlg = NewOrderDialog(ctx)
    dlg.qty.setValue(15)
    # первая в списке — Галиева (3 разряд), первая операция БУ-3 требует 4
    dlg._submit()
    assert "требует 4" in dlg.error.text()
    dlg.emp.setCurrentIndex(dlg.emp.findText("Петров", Qt.MatchStartsWith))
    dlg._submit()
    assert dlg.number

    order = next(o for o in services.orders(conn) if o["number"] == dlg.number)
    rep = ReportDialog(ctx, order["id"])
    rep.defect.setValue(1)
    rep._submit()
    assert rep.error.text() == "При браке нужно указать причину."
    rep.reason.setCurrentIndex(1)
    rep._submit()
    assert rep.status == codes.ST_DONE
