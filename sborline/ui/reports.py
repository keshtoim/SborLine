from PySide6.QtWidgets import QDialog, QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout

from .. import services
from ..export import export_payroll
from .widgets import (MONTHS, Context, MonthBar, Page, Tile, ddmm, fill_table, item, label, make_table, num,
                      page_header, rub, warn)

HEADERS = ["Таб. №", "Сотрудник", "Разряд", "Часы", "Нормо-ч", "% нормы", "Годных", "Брак", "Сдельно", "Премия",
           "Итого"]
PERMIT_COLORS = {"good": "#2c7a4b", "warn": "#a8690f", "bad": "#b2362e"}


class EmployeeCardDialog(QDialog):
    """Карточка: итоги месяца, допуски и выработка по каждому отчёту."""

    def __init__(self, ctx: Context, stats: dict, year: int, month: int):
        super().__init__()
        e = stats["employee"]
        self.setWindowTitle(f"Карточка — {e['short_name']}")
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(label(f"{e['personnel_number']} · {e['grade']} разряд · {e['section']} · "
                            f"{MONTHS[month - 1]} {year}".upper(), "eyebrow"))
        lay.addWidget(label(" ".join(filter(None, (e["last_name"], e["first_name"], e["middle_name"]))), "h2"))

        tiles = QGridLayout()
        bonus = "нет: прогул" if stats["truancy"] else rub(stats["bonus"])
        for i, (title, value) in enumerate([
            ("Отработано", f"{num(stats['hours'], 0)} ч"), ("Нормо-часы", num(stats["norm_hours"])),
            ("Выполнение нормы", f"{num(stats['pct'])}%"), ("Сдельно", rub(stats["earned"])),
            ("Премия", bonus), ("Итого", rub(stats["total"])),
        ]):
            t = Tile(title)
            t.set(value)
            tiles.addWidget(t, i // 3, i % 3)
        lay.addLayout(tiles)

        permits = services.permits(ctx.conn, e["id"])
        if permits:
            parts = []
            for p in permits:
                level, text = services.permit_state(p["valid_until"], ctx.today)
                parts.append(f"<span style='color:{PERMIT_COLORS[level]}'>{p['name']} — {text.lower()} "
                             f"({ddmm(p['valid_until'])}.{p['valid_until'][:4]})</span>")
            lay.addWidget(label("Допуски: " + "; ".join(parts), wrap=True))

        table = make_table(["Дата", "Наряд", "Изделие", "Операция", "Годных", "Брак", "Нормо-ч", "Сумма"])
        results = services.employee_results(ctx.conn, e["id"], year, month)
        fill_table(table, [[
            item(ddmm(r["report_date"])), item(r["number"]), item(r["product"]), item(r["op_name"]),
            item(r["qty_good"], right=True), item(r["qty_defect"], right=True, color="#b2362e" if r["qty_defect"] else "#9aa5ab"),
            item(num(r["norm_hours"]), right=True), item(rub(r["earned"]), right=True),
        ] for r in results], stretch_col=2)
        lay.addWidget(table, 1)
        if not results:
            lay.addWidget(label("Отчётов за месяц нет.", "muted"))

        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)


class ReportsPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.month_bar = MonthBar(ctx.today)
        self.month_bar.changed.connect(lambda *_: self.refresh())
        export_btn = QPushButton("Экспорт в Excel")
        export_btn.clicked.connect(self._export)
        header, *_ = page_header("Расчётный период", "Ведомость заработка", self.month_bar, export_btn)
        self.root.addLayout(header)
        self.note = label("", "muted", wrap=True)
        self.root.addWidget(self.note)
        self.table = make_table(HEADERS)
        self.table.cellDoubleClicked.connect(self._open_card)
        self.root.addWidget(self.table, 1)
        self.rows: list[dict] = []

    def refresh(self) -> None:
        b = services.bonus_settings(self.ctx.conn)
        self.note.setText(
            f"Расценка = норма времени × часовая ставка разряда операции. Премия: {num(b['per_pct'])}% сдельного "
            f"заработка за каждый процент нормы сверх {num(b['threshold'], 0)}%, не больше {num(b['cap'], 0)}%; "
            "прогул лишает премии. Двойной щелчок по строке открывает карточку сотрудника.")
        self.rows = services.month_stats(self.ctx.conn, self.month_bar.year, self.month_bar.month)
        lines = []
        for s in self.rows:
            e = s["employee"]
            if s["truancy"]:
                bonus = item("прогул", right=True, color="#b2362e", bold=True)
            elif s["bonus"]:
                bonus = item(f"{rub(s['bonus'])}  ({num(s['bonus_pct'])}%)", right=True)
            else:
                bonus = item("—", right=True, color="#9aa5ab")
            lines.append([
                item(e["personnel_number"], data=e["id"]), item(e["short_name"]),
                item(e["grade"], right=True), item(num(s["hours"], 0), right=True),
                item(num(s["norm_hours"]), right=True),
                item(f"{num(s['pct'])}%", right=True, color="#a8690f" if s["hours"] and s["pct"] < 95 else None),
                item(s["good"], right=True), item(s["defect"], right=True),
                item(rub(s["earned"]), right=True), bonus,
                item(rub(s["total"]), right=True, bold=True),
            ])
        hours = sum(s["hours"] for s in self.rows)
        norm_h = sum(s["norm_hours"] for s in self.rows)
        lines.append([
            item("Итого", bold=True), item(""), item(""),
            item(num(hours, 0), right=True, bold=True), item(num(norm_h), right=True, bold=True),
            item(f"{num(norm_h / hours * 100 if hours else 0)}%", right=True, bold=True),
            item(sum(s["good"] for s in self.rows), right=True, bold=True),
            item(sum(s["defect"] for s in self.rows), right=True, bold=True),
            item(rub(sum(s["earned"] for s in self.rows)), right=True, bold=True),
            item(rub(sum(s["bonus"] for s in self.rows)), right=True, bold=True),
            item(rub(sum(s["total"] for s in self.rows)), right=True, bold=True),
        ])
        fill_table(self.table, lines, stretch_col=1)

    def _open_card(self, row: int, _col: int) -> None:
        if row >= len(self.rows):  # строка «Итого»
            return
        EmployeeCardDialog(self.ctx, self.rows[row], self.month_bar.year, self.month_bar.month).exec()

    def _export(self) -> None:
        y, m = self.month_bar.year, self.month_bar.month
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить ведомость", f"Ведомость_{m:02d}_{y}.xlsx",
                                              "Книга Excel (*.xlsx)")
        if not path:
            return
        try:
            export_payroll(path, self.rows, y, m)
        except PermissionError:
            warn(self, "Не удалось записать файл: возможно, он открыт в Excel. Закройте его и повторите.")
            return
        QMessageBox.information(self, "СборЛайн", f"Ведомость сохранена:\n{path}")
