from .. import services
from ..codes import ROLE_TITLES
from .widgets import Context, Page, fill_table, item, make_table, page_header


class UsersPage(Page):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.root.addLayout(page_header("Администрирование", "Пользователи")[0])
        self.table = make_table(["Логин", "Роль", "Сотрудник", "Статус"])
        self.root.addWidget(self.table)

    def refresh(self) -> None:
        fill_table(self.table, [[
            item(u["login"]),
            item(ROLE_TITLES[u["role"]]),
            item(u["short_name"] or "—", color=None if u["short_name"] else "#5d6a71"),
            item("активна" if u["is_active"] else "отключена", color="#2c7a4b" if u["is_active"] else "#b2362e"),
        ] for u in services.users(self.ctx.conn)], stretch_col=2)
