from datetime import date, timedelta

import pytest

from sborline import auth, services
from sborline.services import ValidationError

from .conftest import TODAY

ADMIN, MASTER = 1, 2


def _emp_data(**over):
    data = {"personnel_number": "Т-0200", "last_name": "Соколова", "first_name": "Мария", "middle_name": "",
            "position_id": 1, "section_id": 1, "grade": 3, "hire_date": TODAY}
    data.update(over)
    return data


def test_order_requires_valid_permit(conn):
    # Кузнецов, 5 разряд, но без допуска к монтажу жгута
    with pytest.raises(ValidationError, match="допуска"):
        services.create_order(conn, MASTER, 3, 3, 3, 10, TODAY)
    services.grant_permit(conn, MASTER, 3, 3, TODAY + timedelta(days=30), TODAY)
    assert services.create_order(conn, MASTER, 3, 3, 3, 10, TODAY)


def test_grant_permit_validation(conn):
    with pytest.raises(ValidationError, match="позже"):
        services.grant_permit(conn, MASTER, 1, 3, TODAY, TODAY)
    with pytest.raises(ValidationError, match="нужен 5 разряд"):
        services.grant_permit(conn, MASTER, 2, 4, TODAY + timedelta(days=10), TODAY)
    with pytest.raises(ValidationError, match="не требуется"):
        services.grant_permit(conn, MASTER, 1, 1, TODAY + timedelta(days=10), TODAY)


def test_extend_expired_permit_counts_from_today(conn):
    expired = next(p for p in services.permits(conn) if p["employee_id"] == 4)
    assert services.permit_state(expired["valid_until"], TODAY) == ("bad", "Истёк")
    assert services.extend_permit(conn, MASTER, expired["id"], TODAY) == date(2027, 11, 11)


def test_bonus_and_truancy(conn):
    stats = {s["employee"]["id"]: s for s in services.month_stats(conn, 2026, 11)}
    petrov, morozov = stats[1], stats[5]
    assert petrov["pct"] > 100
    assert petrov["bonus_pct"] == min(25, round((petrov["pct"] - 100) * 1.5, 1))
    assert petrov["total"] == round(petrov["earned"] + petrov["bonus"], 2)
    assert morozov["truancy"] == 1 and morozov["bonus"] == 0

    services.set_bonus(conn, ADMIN, 100, 1.5, 5)
    assert services.month_stats(conn, 2026, 11)[0]["bonus_pct"] <= 5
    with pytest.raises(ValidationError, match="от 50 до 150"):
        services.set_bonus(conn, ADMIN, 200, 1, 10)


def test_save_employee(conn):
    with pytest.raises(ValidationError, match="Т-0000"):
        services.save_employee(conn, ADMIN, _emp_data(personnel_number="123"), TODAY)
    with pytest.raises(ValidationError, match="занят"):
        services.save_employee(conn, ADMIN, _emp_data(personnel_number="Т-0142"), TODAY)
    with pytest.raises(ValidationError, match="заглавной"):
        services.save_employee(conn, ADMIN, _emp_data(last_name="<b>"), TODAY)
    new_id = services.save_employee(conn, ADMIN, _emp_data(personnel_number="T-0200"), TODAY)
    e = services.employee(conn, new_id)
    assert e["personnel_number"] == "Т-0200" and e["short_name"] == "Соколова М."
    services.save_employee(conn, ADMIN, _emp_data(grade=4), TODAY, new_id)
    assert services.employee(conn, new_id)["grade"] == 4
    assert services.next_personnel_number(conn) == "Т-0201"


def test_fire_employee(conn):
    with pytest.raises(ValidationError, match="открытых нарядов"):
        services.fire_employee(conn, ADMIN, 1, TODAY)
    services.fire_employee(conn, ADMIN, 7, TODAY)  # Белова: нарядов нет, есть учётка
    assert auth.authenticate(conn, "belova", "belova") is None
    assert all(w["id"] != 7 for w in services.workers(conn))


def test_alerts_and_audit(conn):
    texts = [t for _, t in services.alerts(conn, TODAY)]
    assert any(t.startswith("Истёк: допуск Галиева") for t in texts)
    assert any(t.startswith("Прогул: Морозов") for t in texts)
    services.accept_order(conn, MASTER, services.orders(conn, (3,))[0]["id"])
    assert services.audit_entries(conn)[0]["details"].endswith("принят")
