from datetime import date

import pytest

from sborline import codes, services
from sborline.services import ValidationError

from .conftest import TODAY

MASTER = 2  # belova


def test_piece_rate_from_norm_and_grade(conn):
    # 1,2 мин × 265 ₽/ч (3 разряд)
    assert services.route_step(conn, 1, 1)["piece_rate"] == 5.3


def test_grade_rate_change_recalculates_rate(conn):
    services.set_grade_rate(conn, 1, 3, 300)
    assert services.route_step(conn, 1, 1)["piece_rate"] == 6.0


def test_order_rejects_low_grade(conn):
    # Морозов, 2 разряд; запрессовка требует 3
    with pytest.raises(ValidationError, match="разряд"):
        services.create_order(conn, MASTER, 5, 1, 1, 10, TODAY)


def test_order_lifecycle(conn):
    number = services.create_order(conn, MASTER, 1, 2, 1, 10, TODAY)
    o = next(o for o in services.orders(conn) if o["number"] == number)
    assert o["status_id"] == codes.ST_ISSUED

    with pytest.raises(ValidationError, match="причину"):
        services.add_result(conn, MASTER, o["id"], 3, 1, None, TODAY)
    assert services.add_result(conn, MASTER, o["id"], 4, 1, 2, TODAY) == codes.ST_PROGRESS
    with pytest.raises(ValidationError, match="осталось 6"):
        services.add_result(conn, MASTER, o["id"], 7, 0, None, TODAY)
    with pytest.raises(ValidationError, match="только выполненный"):
        services.accept_order(conn, MASTER, o["id"])
    assert services.add_result(conn, MASTER, o["id"], 6, 0, None, TODAY) == codes.ST_DONE

    services.accept_order(conn, MASTER, o["id"])
    assert services.order(conn, o["id"])["status_id"] == codes.ST_ACCEPTED
    with pytest.raises(ValidationError, match="закрыт"):
        services.add_result(conn, MASTER, o["id"], 1, 0, None, TODAY)


def test_month_stats_matches_results(conn):
    rows = services.month_stats(conn, 2026, 11)
    total = conn.execute("SELECT SUM(earned), SUM(qty_good) FROM v_result_earnings").fetchone()
    assert round(sum(r["earned"] for r in rows), 2) == round(total[0], 2)
    assert sum(r["good"] for r in rows) == total[1]
    assert all(r["employee"]["position"] != "Мастер участка" for r in rows)
    assert all(70 < r["pct"] < 130 for r in rows)


def test_timesheet_cycle(conn):
    day = date(2026, 11, 2)
    assert services.cycle_timesheet(conn, MASTER, 1, day, TODAY) == "Б"
    assert services.timesheet_month(conn, 2026, 11)[(1, "2026-11-02")] == ("Б", 0)
    with pytest.raises(ValidationError, match="будущие"):
        services.cycle_timesheet(conn, MASTER, 1, date(2026, 11, 20), TODAY)
