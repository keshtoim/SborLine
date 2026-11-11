from PySide6.QtWidgets import QDoubleSpinBox, QTabWidget, QVBoxLayout, QWidget

from .. import services
from ..services import ValidationError
from .widgets import Context, Page, fill_table, item, label, make_table, num, page_header, rub, warn


class RefsPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.is_admin = ctx.user["role"] == "admin"
        self.root.addLayout(page_header("Нормативно-справочная информация", "Справочники")[0])
        self.tabs = QTabWidget()
        self.emp_table = make_table(["Таб. №", "ФИО", "Должность", "Участок", "Разряд", "Принят"])
        self.route_table = make_table(["Изделие", "№ оп.", "Код", "Операция", "Норма, мин", "Разряд", "Расценка"])
        self.grade_table = make_table(["Разряд", "Ставка, ₽/ч", "Сотрудников"])
        grades_tab = QWidget()
        g_lay = QVBoxLayout(grades_tab)
        g_lay.setContentsMargins(0, 0, 0, 8)
        g_lay.addWidget(self.grade_table)
        g_lay.addWidget(label("Изменение ставки сразу пересчитывает расценки и ведомость." if self.is_admin
                              else "Ставки меняет администратор.", "muted"))
        self.tabs.addTab(self.emp_table, "Сотрудники")
        self.tabs.addTab(self.route_table, "Техмаршруты")
        self.tabs.addTab(grades_tab, "Тарифная сетка")
        self.root.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        conn = self.ctx.conn
        fill_table(self.emp_table, [[
            item(e["personnel_number"]),
            item(f"{e['last_name']} {e['first_name']} {e['middle_name']}"),
            item(e["position"]), item(e["section"]), item(e["grade"], right=True),
            item(".".join(reversed(e["hire_date"].split("-")))),
        ] for e in services.employees(conn)], stretch_col=1)

        rows = []
        for p in services.products(conn):
            for step in services.route(conn, p["id"]):
                rows.append([
                    item(f"{p['article']} {p['name']}"), item(f"{step['seq_no']:03d}"), item(step["code"]),
                    item(step["name"]), item(num(step["norm_minutes"], 0), right=True),
                    item(step["required_grade"], right=True), item(rub(step["piece_rate"]), right=True),
                ])
        fill_table(self.route_table, rows, stretch_col=3)

        grades = services.grades(conn)
        fill_table(self.grade_table, [[
            item(g["grade"]),
            item("" if self.is_admin else num(g["hourly_rate"], 2), right=True),
            item(g["employees"], right=True),
        ] for g in grades], stretch_col=2)
        if self.is_admin:
            for r, g in enumerate(grades):
                spin = QDoubleSpinBox()
                spin.setRange(1, 10_000)
                spin.setDecimals(2)
                spin.setSingleStep(5)
                spin.setValue(g["hourly_rate"])
                spin.editingFinished.connect(lambda s=spin, gr=g["grade"]: self._set_rate(gr, s.value()))
                self.grade_table.setCellWidget(r, 1, spin)
            self.grade_table.setColumnWidth(1, 140)

    def _set_rate(self, grade: int, rate: float) -> None:
        current = next(g["hourly_rate"] for g in services.grades(self.ctx.conn) if g["grade"] == grade)
        if current == rate:
            return
        try:
            services.set_grade_rate(self.ctx.conn, self.ctx.user["id"], grade, rate)
        except ValidationError as e:
            warn(self, str(e))
        self.refresh()
