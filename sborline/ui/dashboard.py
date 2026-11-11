from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QWidget

from .. import codes, services
from .orders import fill_orders, orders_table
from .widgets import MONTHS, Context, Page, Panel, Tile, label, num, page_header

NORM_SCALE = 130  # шкала выполнения норм, %


def _clear(layout) -> None:
    while layout.count():
        w = layout.takeAt(0).widget()
        if w:
            w.deleteLater()


def _bar(value: float, maximum: float, name: str = "") -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, int(maximum))
    bar.setValue(int(min(value, maximum)))
    bar.setTextVisible(False)
    if name:
        bar.setObjectName(name)
    return bar


class DashboardPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        header, self.eyebrow, _ = page_header("", "Сводка по цеху")
        self.root.addLayout(header)

        tiles = QHBoxLayout()
        self.t_active, self.t_good, self.t_defect, self.t_norm = (
            Tile("Наряды в работе"), Tile("Годных за месяц"), Tile("Брак"), Tile("Выполнение норм"))
        for t in (self.t_active, self.t_good, self.t_defect, self.t_norm):
            tiles.addWidget(t)
        self.root.addLayout(tiles)

        panels = QHBoxLayout()
        norms = Panel("Выполнение норм по сотрудникам", "шкала до 130%, оранжевым — ниже 95%")
        self.norm_grid = QGridLayout()
        norms.body.addLayout(self.norm_grid)
        defects = Panel("Брак по причинам", "ед. за месяц")
        self.defect_grid = QGridLayout()
        defects.body.addLayout(self.defect_grid)
        defects.body.addStretch()
        panels.addWidget(norms, 3)
        panels.addWidget(defects, 2)
        self.root.addLayout(panels)

        active = Panel("Наряды в работе")
        self.table = orders_table(with_employee=True)
        self.table.setMinimumHeight(260)
        active.body.addWidget(self.table)
        self.root.addWidget(active, 1)

    def refresh(self) -> None:
        conn, today = self.ctx.conn, self.ctx.today
        self.eyebrow.setText(f"{MONTHS[today.month - 1]} {today.year} · на {today:%d.%m}".upper())
        stats = services.month_stats(conn, today.year, today.month)
        active = services.orders(conn, codes.OPEN_STATUSES)
        waiting = len(services.orders(conn, (codes.ST_DONE,)))
        good = sum(s["good"] for s in stats)
        defect = sum(s["defect"] for s in stats)
        hours = sum(s["hours"] for s in stats)
        norm_h = sum(s["norm_hours"] for s in stats)

        self.t_active.set(str(len(active)), f"{waiting} ждут приёмки")
        self.t_good.set(f"{good:,}".replace(",", " "), "единиц по всем операциям")
        self.t_defect.set(f"{num(defect / (good + defect) * 100 if good + defect else 0)}%", f"{defect} ед. из {good + defect}")
        self.t_norm.set(f"{num(norm_h / hours * 100 if hours else 0)}%", f"{num(norm_h)} нормо-ч за {num(hours, 0)} ч")

        _clear(self.norm_grid)
        for r, s in enumerate(sorted(stats, key=lambda s: -s["pct"])):
            self.norm_grid.addWidget(label(s["employee"]["short_name"]), r, 0)
            self.norm_grid.addWidget(_bar(s["pct"], NORM_SCALE, "low" if s["pct"] < 95 else ""), r, 1)
            self.norm_grid.addWidget(label(f"{num(s['pct'])}%"), r, 2)
        self.norm_grid.setColumnStretch(1, 1)

        _clear(self.defect_grid)
        reasons = services.defects_by_reason(conn, today.year, today.month)
        top = max([n for _, n in reasons] + [1])
        for r, (name, n) in enumerate(reasons):
            self.defect_grid.addWidget(label(name), r, 0)
            self.defect_grid.addWidget(_bar(n, top, "bad"), r, 1)
            self.defect_grid.addWidget(label(str(n)), r, 2)
        self.defect_grid.setColumnStretch(1, 1)

        fill_orders(self.table, active, with_employee=True)
