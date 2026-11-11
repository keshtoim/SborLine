from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QMessageBox, QPushButton,
                               QTabWidget, QTableWidget, QVBoxLayout, QWidget)

from .. import services
from ..services import ValidationError
from .dialogs import EmployeeDialog, PermitDialog
from .widgets import Context, Page, fill_table, item, label, make_table, num, page_header, primary, rub, warn

LEVEL_COLORS = {"good": "#2c7a4b", "warn": "#a8690f", "bad": "#b2362e"}


def _selected_id(table: QTableWidget):
    rows = table.selectionModel().selectedRows()
    return table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None


def _tab(table: QTableWidget, toolbar: QHBoxLayout | None = None, note: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(8, 8, 8, 8)
    if toolbar:
        lay.addLayout(toolbar)
    lay.addWidget(table)
    if note:
        lay.addWidget(label(note, "muted", wrap=True))
    return w


def _spin(value: float, maximum: float, step: float) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(1)
    s.setSingleStep(step)
    s.setValue(value)
    s.setMaximumWidth(140)
    return s


class RefsPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.is_admin = ctx.user["role"] == "admin"
        self.can_permit = ctx.user["role"] in ("admin", "master")
        self.root.addLayout(page_header("Нормативно-справочная информация", "Справочники")[0])
        self.tabs = QTabWidget()

        self.emp_table = make_table(["Таб. №", "ФИО", "Должность", "Участок", "Разряд", "Принят", "Статус"])
        emp_bar = None
        if self.is_admin:
            emp_bar = QHBoxLayout()
            add_btn, self.edit_btn, self.fire_btn = primary("Добавить сотрудника"), QPushButton("Изменить"), QPushButton("Уволить")
            add_btn.clicked.connect(lambda: self._edit_employee(None))
            self.edit_btn.clicked.connect(lambda: self._edit_employee(_selected_id(self.emp_table)))
            self.fire_btn.clicked.connect(self._fire)
            self.emp_table.itemSelectionChanged.connect(self._update_emp_buttons)
            self.emp_table.cellDoubleClicked.connect(lambda *_: self._edit_employee(_selected_id(self.emp_table)))
            for b in (add_btn, self.edit_btn, self.fire_btn):
                emp_bar.addWidget(b)
            emp_bar.addStretch()
        self.tabs.addTab(_tab(self.emp_table, emp_bar, "Уволенные остаются в табеле и ведомостях прошлых периодов."),
                         "Сотрудники")

        self.route_table = make_table(["Изделие", "№ оп.", "Код", "Операция", "Норма, мин", "Разряд", "Допуск", "Расценка"])
        self.tabs.addTab(_tab(self.route_table), "Техмаршруты")

        self.grade_table = make_table(["Разряд", "Ставка, ₽/ч", "Сотрудников"])
        self.tabs.addTab(_tab(self.grade_table, note="Изменение ставки сразу пересчитывает расценки и ведомость."
                              if self.is_admin else "Ставки меняет администратор."), "Тарифная сетка")

        self.permit_table = make_table(["Сотрудник", "Операция", "Действует до", "Состояние"])
        permit_bar = None
        if self.can_permit:
            permit_bar = QHBoxLayout()
            grant_btn, self.extend_btn = primary("Выдать допуск"), QPushButton("Продлить на год")
            grant_btn.clicked.connect(self._grant)
            self.extend_btn.clicked.connect(self._extend)
            self.permit_table.itemSelectionChanged.connect(
                lambda: self.extend_btn.setEnabled(_selected_id(self.permit_table) is not None))
            permit_bar.addWidget(grant_btn)
            permit_bar.addWidget(self.extend_btn)
            permit_bar.addStretch()
        self.permit_note = label("", "muted", wrap=True)
        permits_tab = _tab(self.permit_table, permit_bar)
        permits_tab.layout().addWidget(self.permit_note)
        self.tabs.addTab(permits_tab, "Допуски")

        self.tabs.addTab(self._bonus_tab(), "Премирование")
        self.root.addWidget(self.tabs, 1)

    def _bonus_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        form = QFormLayout()
        self.threshold, self.per_pct, self.cap = _spin(0, 150, 1), _spin(0, 10, 0.5), _spin(0, 100, 1)
        form.addRow("Порог выполнения нормы, %", self.threshold)
        form.addRow("Премия за каждый процент сверх порога, %", self.per_pct)
        form.addRow("Максимальная премия, %", self.cap)
        lay.addLayout(form)
        self.bonus_example = label("", "muted", wrap=True)
        lay.addWidget(self.bonus_example)
        for s in (self.threshold, self.per_pct, self.cap):
            s.setEnabled(self.is_admin)
            s.valueChanged.connect(self._bonus_example)
        if self.is_admin:
            save = primary("Сохранить условия")
            save.clicked.connect(self._save_bonus)
            lay.addWidget(save, alignment=Qt.AlignLeft)
        else:
            lay.addWidget(label("Условия меняет администратор.", "muted"))
        lay.addStretch()
        return w

    def refresh(self) -> None:
        conn, today = self.ctx.conn, self.ctx.today
        fill_table(self.emp_table, [[
            item(e["personnel_number"], data=e["id"]),
            item(" ".join(filter(None, (e["last_name"], e["first_name"], e["middle_name"])))),
            item(e["position"]), item(e["section"]), item(e["grade"], right=True),
            item(".".join(reversed(e["hire_date"].split("-")))),
            item(f"Уволен {'.'.join(reversed(e['dismissal_date'].split('-')))}", color="#b2362e")
            if e["dismissal_date"] else item("Работает", color="#2c7a4b"),
        ] for e in services.employees(conn)], stretch_col=1)
        if self.is_admin:
            self._update_emp_buttons()

        rows = []
        for p in services.products(conn):
            for step in services.route(conn, p["id"]):
                rows.append([
                    item(f"{p['article']} {p['name']}"), item(f"{step['seq_no']:03d}"), item(step["code"]),
                    item(step["name"]), item(num(step["norm_minutes"]), right=True),
                    item(step["required_grade"], right=True),
                    item("нужен" if step["requires_permit"] else "", color="#a8690f"),
                    item(rub(step["piece_rate"]), right=True),
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

        permit_rows = []
        for p in services.permits(conn):
            if p["dismissal_date"]:
                continue
            level, text = services.permit_state(p["valid_until"], today)
            permit_rows.append([
                item(p["short_name"], data=p["id"]), item(f"{p['code']} {p['name']}"),
                item(".".join(reversed(p["valid_until"].split("-")))), item(text, color=LEVEL_COLORS[level], bold=True),
            ])
        fill_table(self.permit_table, permit_rows, stretch_col=1)
        ops = ", ".join(f"«{o['name']}»" for o in services.permit_operations(conn))
        self.permit_note.setText(f"Допуск обязателен для операций {ops}. Без действующего допуска наряд не выдаётся.")
        if self.can_permit:
            self.extend_btn.setEnabled(False)

        b = services.bonus_settings(conn)
        for spin, key in ((self.threshold, "threshold"), (self.per_pct, "per_pct"), (self.cap, "cap")):
            spin.blockSignals(True)
            spin.setValue(b[key])
            spin.blockSignals(False)
        self._bonus_example()

    def _bonus_example(self) -> None:
        settings = {"threshold": self.threshold.value(), "per_pct": self.per_pct.value(), "cap": self.cap.value()}
        pct, _ = services.calc_bonus(108, 0, 0, settings)
        self.bonus_example.setText(f"Пример: при выполнении нормы на 108% премия составит {num(pct)}% сдельного "
                                   "заработка. Прогул в месяце лишает премии полностью.")

    def _update_emp_buttons(self) -> None:
        emp_id = _selected_id(self.emp_table)
        active = emp_id is not None and services.employee(self.ctx.conn, emp_id)["dismissal_date"] is None
        self.edit_btn.setEnabled(emp_id is not None)
        self.fire_btn.setEnabled(active)

    def _edit_employee(self, employee_id) -> None:
        if not self.is_admin:
            return
        if EmployeeDialog(self.ctx, employee_id).exec() == QDialog.Accepted:
            self.refresh()

    def _fire(self) -> None:
        e = services.employee(self.ctx.conn, _selected_id(self.emp_table))
        answer = QMessageBox.question(self, "Увольнение", f"Уволить {e['short_name']} сегодняшним днём? "
                                      "Учётная запись сотрудника будет отключена.")
        if answer != QMessageBox.Yes:
            return
        try:
            services.fire_employee(self.ctx.conn, self.ctx.user["id"], e["id"], self.ctx.today)
        except ValidationError as err:
            warn(self, str(err))
        self.refresh()

    def _grant(self) -> None:
        if PermitDialog(self.ctx).exec() == QDialog.Accepted:
            self.refresh()

    def _extend(self) -> None:
        services.extend_permit(self.ctx.conn, self.ctx.user["id"], _selected_id(self.permit_table), self.ctx.today)
        self.refresh()

    def _save_bonus(self) -> None:
        try:
            services.set_bonus(self.ctx.conn, self.ctx.user["id"], self.threshold.value(), self.per_pct.value(),
                               self.cap.value())
        except ValidationError as e:
            warn(self, str(e))
            return
        QMessageBox.information(self, "СборЛайн", "Условия премирования сохранены.")

    def _set_rate(self, grade: int, rate: float) -> None:
        current = next(g["hourly_rate"] for g in services.grades(self.ctx.conn) if g["grade"] == grade)
        if current == rate:
            return
        try:
            services.set_grade_rate(self.ctx.conn, self.ctx.user["id"], grade, rate)
        except ValidationError as e:
            warn(self, str(e))
        self.refresh()
