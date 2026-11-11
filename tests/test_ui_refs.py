import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate  # noqa: E402

from sborline import services  # noqa: E402
from sborline.ui.dialogs import EmployeeDialog, PermitDialog  # noqa: E402
from sborline.ui.refs import RefsPage  # noqa: E402

from .conftest import TODAY  # noqa: E402
from .test_ui import _ctx, app  # noqa: E402,F401


def test_refs_page_for_admin_and_master(app, conn):
    for login in ("admin", "belova"):
        page = RefsPage(_ctx(conn, login))
        page.refresh()
        assert page.permit_table.rowCount() == 5
        assert "«Монтаж жгута»" in page.permit_note.text()


def test_employee_dialog_add_and_validate(app, conn):
    ctx = _ctx(conn, "admin")
    dlg = EmployeeDialog(ctx)
    assert dlg.tab.text() == "Т-0194"
    dlg._submit()
    assert "заглавной" in dlg.error.text()
    dlg.last.setText("Соколова")
    dlg.first.setText("Мария")
    dlg._submit()
    assert services.employee(conn, dlg.employee_id)["short_name"] == "Соколова М."


def test_permit_dialog(app, conn):
    ctx = _ctx(conn, "belova")
    dlg = PermitDialog(ctx)
    dlg.emp.setCurrentIndex(dlg.emp.findData(3))
    dlg.operation.setCurrentIndex(dlg.operation.findData(3))
    dlg.until.setDate(QDate(2027, 6, 1))
    dlg._submit()
    assert services.has_valid_permit(conn, 3, 3, TODAY)
