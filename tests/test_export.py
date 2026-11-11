from openpyxl import load_workbook

from sborline import services
from sborline.export import export_payroll


def test_export_payroll(conn, tmp_path):
    rows = services.month_stats(conn, 2026, 11)
    path = tmp_path / "payroll.xlsx"
    export_payroll(path, rows, 2026, 11)

    ws = load_workbook(path).active
    assert ws["A1"].value == "Ведомость заработка за ноябрь 2026"
    first, total = 4, 4 + len(rows)
    assert ws.cell(first, 1).value == rows[0]["employee"]["personnel_number"]
    assert ws[f"A{total}"].value == "Итого"
    assert ws[f"M{total}"].value == f"=SUM(M{first}:M{total - 1})"
    assert ws[f"M{first}"].value == f"=J{first}+L{first}"
    assert sum(ws[f"J{r}"].value for r in range(first, total)) == sum(r["earned"] for r in rows)
    assert round(sum(ws[f"L{r}"].value for r in range(first, total)), 2) == round(sum(r["bonus"] for r in rows), 2)
    morozov = next(r for r in range(first, total) if ws[f"B{r}"].value.startswith("Морозов"))
    assert ws[f"K{morozov}"].value == "прогул"
