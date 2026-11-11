from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QPushButton, QSpinBox,
                               QVBoxLayout)

from .. import services
from ..services import ValidationError
from .widgets import Context, label, num, primary, rub


class _FormDialog(QDialog):
    def __init__(self, ctx: Context, title: str, ok_text: str):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, 18, 20, 18)
        self.lay.setSpacing(12)
        self.lay.addWidget(label(title, "h2"))
        self.form = QFormLayout()
        self.lay.addLayout(self.form)
        self.calc_frame = QFrame()
        self.calc_frame.setObjectName("calc")
        calc_lay = QVBoxLayout(self.calc_frame)
        self.calc = label("", wrap=True)
        calc_lay.addWidget(self.calc)
        self.lay.addWidget(self.calc_frame)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        self.lay.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = primary(ok_text)
        ok.setDefault(True)
        ok.clicked.connect(self._submit)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        self.lay.addLayout(buttons)

    def _submit(self) -> None:
        try:
            self.save()
        except ValidationError as e:
            self.error.setText(str(e))
            self.error.show()
            return
        self.accept()

    def save(self) -> None:
        raise NotImplementedError


def _spin(value: int) -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 100_000)
    s.setValue(value)
    return s


class NewOrderDialog(_FormDialog):
    def __init__(self, ctx: Context):
        super().__init__(ctx, "Новый наряд", "Выдать наряд")
        self.number = None
        self.emp = QComboBox()
        for e in services.workers(ctx.conn):
            self.emp.addItem(f"{e['short_name']} — {e['grade']} разряд, {e['section']}", e["id"])
        self.product = QComboBox()
        for p in services.products(ctx.conn):
            self.product.addItem(f"{p['article']} {p['name']}", p["id"])
        self.operation = QComboBox()
        self.qty = _spin(20)
        self.qty.setMinimum(1)
        self.form.addRow("Сотрудник", self.emp)
        self.form.addRow("Изделие", self.product)
        self.form.addRow("Операция", self.operation)
        self.form.addRow("Количество, шт.", self.qty)

        self.product.currentIndexChanged.connect(self._fill_operations)
        self.operation.currentIndexChanged.connect(self._recalc)
        self.qty.valueChanged.connect(self._recalc)
        self._fill_operations()

    def _fill_operations(self) -> None:
        self.operation.blockSignals(True)
        self.operation.clear()
        for step in services.route(self.ctx.conn, self.product.currentData()):
            self.operation.addItem(f"{step['code']} {step['name']}", step["operation_id"])
        self.operation.blockSignals(False)
        self._recalc()

    def _recalc(self) -> None:
        step = services.route_step(self.ctx.conn, self.product.currentData(), self.operation.currentData())
        qty = self.qty.value()
        self.calc.setText(
            f"Норма: <b>{num(step['norm_minutes'], 0)} мин/шт</b> · требуется <b>{step['required_grade']} разряд</b><br>"
            f"Расценка: <b>{rub(step['piece_rate'])}</b> · на весь наряд: "
            f"<b>{num(qty * step['norm_minutes'] / 60)} нормо-ч</b>, <b>{rub(qty * step['piece_rate'])}</b>")
        self.error.hide()

    def save(self) -> None:
        self.number = services.create_order(
            self.ctx.conn, self.ctx.user["id"], self.emp.currentData(), self.product.currentData(),
            self.operation.currentData(), self.qty.value(), self.ctx.today)


class ReportDialog(_FormDialog):
    def __init__(self, ctx: Context, order_id: int):
        self.order = services.order(ctx.conn, order_id)
        super().__init__(ctx, f"Отчёт по наряду {self.order['number']}", "Сохранить отчёт")
        o = self.order
        left = o["planned_qty"] - o["good"]
        self.calc.setText(f"{o['short_name']} · {o['product']}<br>{o['op_code']} {o['op_name']} · "
                          f"сделано {o['good']} из {o['planned_qty']}, осталось <b>{left}</b>")
        self.lay.insertWidget(1, self.calc_frame)
        self.good = _spin(left)
        self.defect = _spin(0)
        self.reason = QComboBox()
        self.reason.addItem("— не указана —", None)
        for r in services.defect_reasons(ctx.conn):
            self.reason.addItem(r["name"], r["id"])
        self.form.addRow("Годных, шт.", self.good)
        self.form.addRow("Брак, шт.", self.defect)
        self.form.addRow("Причина брака", self.reason)
        self.status = None

    def save(self) -> None:
        self.status = services.add_result(
            self.ctx.conn, self.ctx.user["id"], self.order["id"], self.good.value(), self.defect.value(),
            self.reason.currentData(), self.ctx.today)
