from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

HEADERS = ["Таб. №", "Сотрудник", "Участок", "Разряд", "Отработано, ч", "Нормо-ч", "% нормы", "Годных", "Брак",
           "Начислено, ₽"]
WIDTHS = [10, 22, 22, 9, 14, 11, 10, 10, 8, 15]
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def export_payroll(path: str | Path, rows: list[dict], year: int, month: int) -> None:
    """Ведомость сдельного заработка в .xlsx; итоги — формулами, чтобы правки в Excel пересчитывались."""
    wb = Workbook()
    ws = wb.active
    ws.title = f"{month:02d}.{year}"
    ws["A1"] = f"Ведомость сдельного заработка за {MONTHS[month - 1]} {year}"
    ws["A1"].font = Font(bold=True, size=13)

    head_row = 3
    thin = Side(style="thin", color="D3DADE")
    for c, (title, width) in enumerate(zip(HEADERS, WIDTHS), start=1):
        cell = ws.cell(head_row, c, title)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F4F6F7")
        cell.border = Border(bottom=thin)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = width

    first = head_row + 1
    for r, s in enumerate(rows, start=first):
        e = s["employee"]
        values = [e["personnel_number"], e["short_name"], e["section"], e["grade"], s["hours"],
                  round(s["norm_hours"], 2), None, s["good"], s["defect"], s["earned"]]
        for c, v in enumerate(values, start=1):
            ws.cell(r, c, v)
        ws.cell(r, 7, f"=IF(E{r}=0,0,F{r}/E{r})")
    last = first + len(rows) - 1
    total = last + 1

    ws.cell(total, 1, "Итого").font = Font(bold=True)
    for col in "EFHIJ":
        ws[f"{col}{total}"] = f"=SUM({col}{first}:{col}{last})"
    ws[f"G{total}"] = f"=IF(E{total}=0,0,F{total}/E{total})"
    for c in range(1, len(HEADERS) + 1):
        ws.cell(total, c).font = Font(bold=True)
        ws.cell(total, c).border = Border(top=thin)

    for r in range(first, total + 1):
        ws[f"F{r}"].number_format = "0.0"
        ws[f"G{r}"].number_format = "0.0%"
        ws[f"J{r}"].number_format = "#,##0.00"
    ws.freeze_panes = ws.cell(first, 1)
    wb.save(path)
