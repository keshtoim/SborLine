from .. import services
from .widgets import Context, MonthBar, Page, fill_table, item, label, make_table, num, page_header, rub

HEADERS = ["Таб. №", "Сотрудник", "Участок", "Разряд", "Отработано, ч", "Нормо-ч", "% нормы", "Годных", "Брак",
           "Начислено"]


class ReportsPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.month_bar = MonthBar(ctx.today)
        self.month_bar.changed.connect(lambda *_: self.refresh())
        header, *_ = page_header("Расчётный период", "Ведомость сдельного заработка", self.month_bar)
        self.header = header
        self.root.addLayout(header)
        self.root.addWidget(label("Расценка = норма времени × часовая ставка разряда, который требует операция. "
                                  "Оранжевым — выполнение нормы ниже 95%.", "muted", wrap=True))
        self.table = make_table(HEADERS)
        self.root.addWidget(self.table, 1)
        self.rows: list[dict] = []

    def refresh(self) -> None:
        self.rows = services.month_stats(self.ctx.conn, self.month_bar.year, self.month_bar.month)
        lines = []
        for s in self.rows:
            e = s["employee"]
            lines.append([
                item(e["personnel_number"]), item(e["short_name"]), item(e["section"]),
                item(e["grade"], right=True), item(num(s["hours"], 0), right=True),
                item(num(s["norm_hours"]), right=True),
                item(f"{num(s['pct'])}%", right=True, color="#a8690f" if s["hours"] and s["pct"] < 95 else None),
                item(s["good"], right=True), item(s["defect"], right=True),
                item(rub(s["earned"]), right=True, bold=True),
            ])
        hours = sum(s["hours"] for s in self.rows)
        norm_h = sum(s["norm_hours"] for s in self.rows)
        lines.append([
            item("Итого", bold=True), item(""), item(""), item(""),
            item(num(hours, 0), right=True, bold=True), item(num(norm_h), right=True, bold=True),
            item(f"{num(norm_h / hours * 100 if hours else 0)}%", right=True, bold=True),
            item(sum(s["good"] for s in self.rows), right=True, bold=True),
            item(sum(s["defect"] for s in self.rows), right=True, bold=True),
            item(rub(sum(s["earned"] for s in self.rows)), right=True, bold=True),
        ])
        fill_table(self.table, lines, stretch_col=1)
