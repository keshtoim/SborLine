from openpyxl import load_workbook

from sborline import services
from sborline.export import export_payroll


def test_export_payroll(conn, tmp_path):
    rows = services.month_stats(conn, 2026, 11)
    path = tmp_path / "payroll.xlsx"
    export_payroll(path, rows, 2026, 11)

    ws = load_workbook(path).active
    assert ws["A1"].value == "Ведомость сдельного заработка за ноябрь 2026"
    first, total = 4, 4 + len(rows)
    assert ws.cell(first, 1).value == rows[0]["employee"]["personnel_number"]
    assert ws[f"A{total}"].value == "Итого"
    assert ws[f"J{total}"].value == f"=SUM(J{first}:J{total - 1})"
    assert sum(ws[f"J{r}"].value for r in range(first, total)) == sum(r["earned"] for r in rows)
