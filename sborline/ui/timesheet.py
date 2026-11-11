from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView

from .. import services
from ..services import ValidationError
from ..workcal import HOLIDAYS, is_day_off, month_days
from .widgets import Context, MonthBar, Page, item, label, make_table, page_header, warn

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
CODE_COLORS = {"Б": "#3a5f9a", "О": "#2c7a4b", "П": "#b2362e", "В": "#9aa5ab"}
WEEKEND_BG = QColor("#eef1f2")
HOLIDAY_BG = QColor("#f6dcd9")
TODAY_BG = QColor("#d8ecec")
TOTALS = 5  # колонки итогов после ФИО


class TimesheetPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.editable = ctx.user["role"] == "master"
        self.month_bar = MonthBar(ctx.today)
        self.month_bar.changed.connect(lambda *_: self.refresh())
        header, *_ = page_header("Учёт рабочего времени", "Табель", self.month_bar)
        self.root.addLayout(header)
        hint = "Двойной щелчок по дню меняет код: Я → Б → О → П → В." if self.editable else "Только просмотр."
        self.root.addWidget(label(f"{hint}  Число — часы явки; Б — больничный, О — отпуск, П — прогул, "
                                  "В — выходной. Розовым отмечены праздники.", "muted", wrap=True))
        self.table = make_table([])
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(self.table.SelectionMode.NoSelection)
        self.table.cellDoubleClicked.connect(self._cycle)
        self.root.addWidget(self.table, 1)
        self.days: list[date] = []
        self.emp_ids: list[int] = []

    def refresh(self) -> None:
        y, m = self.month_bar.year, self.month_bar.month
        self.days = month_days(y, m)
        grid = services.timesheet_month(self.ctx.conn, y, m)
        emps = services.employees(self.ctx.conn)
        self.emp_ids = [e["id"] for e in emps]

        # итоги сразу после ФИО, чтобы не уезжали за край при 31 дне
        headers = ["Сотрудник", "Дн.", "Часы", "Б", "О", "П"] + [f"{d.day}\n{WEEKDAYS[d.weekday()]}" for d in self.days]
        t = self.table
        t.clear()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(len(emps))
        for r, e in enumerate(emps):
            t.setItem(r, 0, item(e["short_name"]))
            t.item(r, 0).setToolTip(e["personnel_number"])
            counts = {"Я": 0, "Б": 0, "О": 0, "П": 0}
            hours = 0
            for c, d in enumerate(self.days, start=TOTALS + 1):
                rec = grid.get((e["id"], d.isoformat()))
                if rec is None:
                    cell = item("·" if d > self.ctx.today else "", color="#c3ccd0")
                else:
                    code, h = rec
                    counts[code] = counts.get(code, 0) + 1
                    hours += h
                    cell = item(f"{h:g}" if code == "Я" else code, color=CODE_COLORS.get(code), bold=code in "БОП")
                cell.setTextAlignment(Qt.AlignCenter)
                if d in HOLIDAYS:
                    cell.setBackground(HOLIDAY_BG)
                elif is_day_off(d):
                    cell.setBackground(WEEKEND_BG)
                if d == self.ctx.today:
                    cell.setBackground(TODAY_BG)
                t.setItem(r, c, cell)
            totals = [counts["Я"], f"{hours:g}", counts["Б"] or "", counts["О"] or "", counts["П"] or ""]
            for i, v in enumerate(totals, start=1):
                t.setItem(r, i, item(v, right=True, bold=i == 2, color="#b2362e" if i == 5 else None))

        t.resizeColumnsToContents()
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Fixed)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, len(headers)):
            t.setColumnWidth(c, 48 if c <= TOTALS else 30)

    def _cycle(self, row: int, col: int) -> None:
        if not self.editable or col <= TOTALS:
            return
        try:
            services.cycle_timesheet(self.ctx.conn, self.ctx.user["id"], self.emp_ids[row], self.days[col - TOTALS - 1],
                                     self.ctx.today)
        except ValidationError as e:
            warn(self, str(e))
            return
        self.refresh()
