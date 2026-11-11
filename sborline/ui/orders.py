from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QDialog, QHBoxLayout, QPushButton, QTableWidget

from .. import codes, services
from .dialogs import NewOrderDialog, ReportDialog
from .widgets import (STATUS_COLORS, Context, Page, Tile, ddmm, fill_table, item, make_table, num, page_header,
                      primary, rub)

FILTERS = [
    ("Открытые", (codes.ST_ISSUED, codes.ST_PROGRESS, codes.ST_DONE)),
    ("Выдан", (codes.ST_ISSUED,)),
    ("В работе", (codes.ST_PROGRESS,)),
    ("Выполнен", (codes.ST_DONE,)),
    ("Принят", (codes.ST_ACCEPTED,)),
    ("Все", None),
]


def orders_table(with_employee: bool) -> QTableWidget:
    headers = ["№", "Дата"] + (["Сотрудник"] if with_employee else []) + \
              ["Изделие", "Операция", "Выполнено", "Брак", "Расценка", "Статус"]
    return make_table(headers)


def fill_orders(table: QTableWidget, orders, with_employee: bool) -> None:
    rows = []
    for o in orders:
        row = [item(o["number"], data=o["id"]), item(ddmm(o["issue_date"]))]
        if with_employee:
            row.append(item(o["short_name"]))
        row += [
            item(o["product"]),
            item(f"{o['op_code']} {o['op_name']}"),
            item(f"{o['good']} / {o['planned_qty']}", right=True),
            item(o["defect"], right=True, color="#b2362e" if o["defect"] else "#9aa5ab"),
            item(rub(o["piece_rate"]), right=True),
            item(o["status"], color=STATUS_COLORS[o["status_id"]], bold=True),
        ]
        rows.append(row)
    fill_table(table, rows, stretch_col=3 if with_employee else 2)


class OrdersPage(Page):
    """Наряды цеха для мастера; с worker=True — только свои наряды сборщика."""

    def __init__(self, ctx: Context, worker: bool = False):
        super().__init__(ctx)
        self.worker = worker
        self.is_master = ctx.user["role"] == "master"
        self.statuses = FILTERS[0][1]

        new_btn = primary("Новый наряд")
        new_btn.clicked.connect(self._new_order)
        new_btn.setVisible(self.is_master)
        header, self.eyebrow, self.title = page_header("Сменные задания", "Наряды", new_btn)
        self.root.addLayout(header)

        if worker:
            tiles = QHBoxLayout()
            self.t_earned, self.t_pct, self.t_good = Tile("Начислено за месяц"), Tile("Выполнение нормы"), Tile("Сдано годных")
            for t in (self.t_earned, self.t_pct, self.t_good):
                tiles.addWidget(t)
            self.root.addLayout(tiles)

        bar = QHBoxLayout()
        group = QButtonGroup(self)
        for i, (name, _) in enumerate(FILTERS):
            chip = QPushButton(name)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(i == 0)
            group.addButton(chip, i)
            bar.addWidget(chip)
        group.idClicked.connect(self._set_filter)
        bar.addStretch()
        self.report_btn = QPushButton("Отчёт о выполнении")
        self.report_btn.clicked.connect(self._report)
        self.accept_btn = primary("Принять")
        self.accept_btn.clicked.connect(self._accept)
        self.accept_btn.setVisible(self.is_master)
        bar.addWidget(self.report_btn)
        bar.addWidget(self.accept_btn)
        self.root.addLayout(bar)

        self.table = orders_table(with_employee=not worker)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self._report())
        self.root.addWidget(self.table, 1)

    def refresh(self) -> None:
        emp_id = self.ctx.user["employee_id"] if self.worker else None
        if self.worker:
            e = services.employee(self.ctx.conn, emp_id)
            self.eyebrow.setText(f"{e['personnel_number']} · {e['grade']} разряд · {e['section']}".upper())
            self.title.setText(f"{e['last_name']} {e['first_name']} {e['middle_name']}")
            stats = next(s for s in services.month_stats(self.ctx.conn, self.ctx.today.year, self.ctx.today.month)
                         if s["employee"]["id"] == emp_id)
            bonus = "премии нет: прогул" if stats["truancy"] else f"премия {rub(stats['bonus'])}"
            self.t_earned.set(rub(stats["total"]), f"сдельно {rub(stats['earned'])}, {bonus}")
            self.t_pct.set(f"{num(stats['pct'])}%", f"{num(stats['norm_hours'])} нормо-ч за {num(stats['hours'], 0)} ч")
            self.t_good.set(str(stats["good"]), f"брак: {stats['defect']} ед.")
        fill_orders(self.table, services.orders(self.ctx.conn, self.statuses, emp_id), not self.worker)
        self._update_buttons()

    def _set_filter(self, index: int) -> None:
        self.statuses = FILTERS[index][1]
        self.refresh()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return services.order(self.ctx.conn, self.table.item(rows[0].row(), 0).data(Qt.UserRole))

    def _update_buttons(self) -> None:
        o = self._selected()
        can_report = self.ctx.user["role"] in ("master", "worker")
        self.report_btn.setEnabled(bool(o) and can_report and o["status_id"] in codes.OPEN_STATUSES)
        self.accept_btn.setEnabled(bool(o) and o["status_id"] == codes.ST_DONE)

    def _new_order(self) -> None:
        if NewOrderDialog(self.ctx).exec() == QDialog.Accepted:
            self.refresh()

    def _report(self) -> None:
        if not self.report_btn.isEnabled():
            return
        if ReportDialog(self.ctx, self._selected()["id"]).exec() == QDialog.Accepted:
            self.refresh()

    def _accept(self) -> None:
        services.accept_order(self.ctx.conn, self.ctx.user["id"], self._selected()["id"])
        self.refresh()
