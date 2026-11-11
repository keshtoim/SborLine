import re
import sqlite3
from datetime import date, datetime

from . import codes
from .workcal import shift_hours

SHORT_NAME = "e.last_name || ' ' || substr(e.first_name, 1, 1) || '.' || COALESCE(substr(e.middle_name, 1, 1) || '.', '')"
NAME_RE = re.compile(r"^[А-ЯЁA-Z][а-яёa-z]+(-[А-ЯЁA-Z][а-яёa-z]+)?$")
TAB_RE = re.compile(r"^Т-\d{4}$")


class ValidationError(Exception):
    pass


def audit(conn, user_id, action, entity, entity_id, details=None):
    # локальное время: CURRENT_TIMESTAMP в SQLite — UTC
    conn.execute(
        "INSERT INTO audit_log (user_id, ts, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, datetime.now().isoformat(sep=" ", timespec="seconds"), action, entity, entity_id, details))


def _dmy(d: date | str) -> str:
    return (date.fromisoformat(d) if isinstance(d, str) else d).strftime("%d.%m.%Y")


def _month(year, month):
    return f"{year:04d}-{month:02d}"


def employees(conn) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT e.*, {SHORT_NAME} AS short_name, p.name AS position, s.name AS section
        FROM employees e
        JOIN positions p ON p.id = e.position_id
        JOIN sections s ON s.id = e.section_id
        ORDER BY e.last_name""").fetchall()


def workers(conn) -> list[sqlite3.Row]:
    """Сотрудники, которым выдаются наряды: работающие, кроме мастеров."""
    return [e for e in employees(conn) if e["dismissal_date"] is None and e["position"] != "Мастер участка"]


def employee(conn, employee_id) -> sqlite3.Row:
    return conn.execute(f"""
        SELECT e.*, {SHORT_NAME} AS short_name, s.name AS section
        FROM employees e JOIN sections s ON s.id = e.section_id WHERE e.id = ?""", (employee_id,)).fetchone()


def products(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM products ORDER BY article").fetchall()


def route(conn, product_id) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT rr.*, o.code, o.name, o.requires_permit
        FROM v_route_rates rr JOIN operations o ON o.id = rr.operation_id
        WHERE rr.product_id = ? ORDER BY rr.seq_no""", (product_id,)).fetchall()


def route_step(conn, product_id, operation_id) -> sqlite3.Row | None:
    return conn.execute("""
        SELECT rr.*, o.code, o.name, o.requires_permit
        FROM v_route_rates rr JOIN operations o ON o.id = rr.operation_id
        WHERE rr.product_id = ? AND rr.operation_id = ?""", (product_id, operation_id)).fetchone()


def defect_reasons(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM defect_reasons ORDER BY id").fetchall()


def grades(conn) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT g.grade, g.hourly_rate, COUNT(e.id) AS employees
        FROM grades g LEFT JOIN employees e ON e.grade = g.grade
        GROUP BY g.grade ORDER BY g.grade""").fetchall()


def users(conn) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT u.id, u.login, u.is_active, r.name AS role, {SHORT_NAME} AS short_name
        FROM users u JOIN roles r ON r.id = u.role_id
        LEFT JOIN employees e ON e.id = u.employee_id
        ORDER BY u.id""").fetchall()


def orders(conn, statuses=None, employee_id=None) -> list[sqlite3.Row]:
    where, args = [], []
    if statuses:
        where.append(f"wo.status_id IN ({','.join('?' * len(statuses))})")
        args += statuses
    if employee_id:
        where.append("wo.employee_id = ?")
        args.append(employee_id)
    return conn.execute(f"""
        SELECT wo.*, {SHORT_NAME} AS short_name, p.name AS product, o.code AS op_code, o.name AS op_name,
               st.name AS status, rr.piece_rate,
               COALESCE(SUM(wr.qty_good), 0) AS good, COALESCE(SUM(wr.qty_defect), 0) AS defect
        FROM work_orders wo
        JOIN employees e ON e.id = wo.employee_id
        JOIN products p ON p.id = wo.product_id
        JOIN operations o ON o.id = wo.operation_id
        JOIN order_statuses st ON st.id = wo.status_id
        JOIN v_route_rates rr ON rr.product_id = wo.product_id AND rr.operation_id = wo.operation_id
        LEFT JOIN work_results wr ON wr.work_order_id = wo.id
        {'WHERE ' + ' AND '.join(where) if where else ''}
        GROUP BY wo.id
        ORDER BY wo.issue_date DESC, wo.id DESC""", args).fetchall()


def order(conn, order_id) -> sqlite3.Row:
    return next(o for o in orders(conn) if o["id"] == order_id)


def create_order(conn, user_id, employee_id, product_id, operation_id, qty, today: date) -> str:
    if not isinstance(qty, int) or qty < 1:
        raise ValidationError("Укажите количество целым числом больше нуля.")
    step = route_step(conn, product_id, operation_id)
    if step is None:
        raise ValidationError("Операции нет в техмаршруте выбранного изделия.")
    emp = employee(conn, employee_id)
    if emp["grade"] < step["required_grade"]:
        raise ValidationError(
            f"У сотрудника {emp['grade']} разряд, а операция «{step['name']}» требует {step['required_grade']}. "
            "Выберите другого исполнителя.")
    if step["requires_permit"] and not has_valid_permit(conn, employee_id, operation_id, today):
        raise ValidationError(f"У {emp['short_name']} нет действующего допуска к операции «{step['name']}». "
                              "Оформите его в справочнике «Допуски».")
    next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM work_orders").fetchone()[0]
    number = f"Н-{1100 + next_id}"
    cur = conn.execute(
        """INSERT INTO work_orders (number, issue_date, employee_id, product_id, operation_id,
                                    planned_qty, status_id, issued_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (number, today.isoformat(), employee_id, product_id, operation_id, qty, codes.ST_ISSUED, user_id))
    audit(conn, user_id, "INSERT", "work_orders", cur.lastrowid,
          f"Выдан наряд {number}: {emp['short_name']}, {step['name']} × {qty}")
    conn.commit()
    return number


def add_result(conn, user_id, order_id, good, defect, reason_id, today: date) -> int:
    """Отчёт о выполнении. Возвращает новый статус наряда."""
    o = order(conn, order_id)
    if o["status_id"] not in codes.OPEN_STATUSES:
        raise ValidationError(f"Наряд {o['number']} уже закрыт.")
    left = o["planned_qty"] - o["good"]
    if good < 0 or defect < 0:
        raise ValidationError("Количество — целые числа от нуля.")
    if good + defect == 0:
        raise ValidationError("Отчёт пустой: укажите годные или брак.")
    if good > left:
        raise ValidationError(f"Годных больше, чем осталось по наряду (осталось {left}).")
    if defect and not reason_id:
        raise ValidationError("При браке нужно указать причину.")
    cur = conn.execute(
        """INSERT INTO work_results (work_order_id, report_date, qty_good, qty_defect, defect_reason_id)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, today.isoformat(), good, defect, reason_id if defect else None))
    status = codes.ST_DONE if good == left else codes.ST_PROGRESS
    conn.execute("UPDATE work_orders SET status_id = ? WHERE id = ?", (status, order_id))
    audit(conn, user_id, "INSERT", "work_results", cur.lastrowid,
          f"Отчёт по {o['number']}: годных {good}, брак {defect}")
    conn.commit()
    return status


def accept_order(conn, user_id, order_id) -> None:
    o = order(conn, order_id)
    if o["status_id"] != codes.ST_DONE:
        raise ValidationError(f"Принять можно только выполненный наряд, а {o['number']} — «{o['status']}».")
    conn.execute("UPDATE work_orders SET status_id = ? WHERE id = ?", (codes.ST_ACCEPTED, order_id))
    conn.execute("UPDATE work_results SET accepted_by = ? WHERE work_order_id = ?", (user_id, order_id))
    audit(conn, user_id, "UPDATE", "work_orders", order_id, f"Наряд {o['number']} принят")
    conn.commit()


def bonus_settings(conn) -> sqlite3.Row:
    return conn.execute("SELECT * FROM bonus_settings WHERE id = 1").fetchone()


def set_bonus(conn, user_id, threshold, per_pct, cap) -> None:
    if not 50 <= threshold <= 150:
        raise ValidationError("Порог выполнения нормы — от 50 до 150%.")
    if not 0 <= per_pct <= 10:
        raise ValidationError("Премия за процент сверх порога — от 0 до 10%.")
    if not 0 <= cap <= 100:
        raise ValidationError("Максимальная премия — от 0 до 100%.")
    conn.execute("UPDATE bonus_settings SET threshold = ?, per_pct = ?, cap = ? WHERE id = 1", (threshold, per_pct, cap))
    audit(conn, user_id, "UPDATE", "bonus_settings", 1,
          f"Премирование: порог {threshold:g}%, {per_pct:g}% за каждый процент сверх, максимум {cap:g}%")
    conn.commit()


def calc_bonus(pct: float, earned: float, truancy: int, settings) -> tuple[float, float]:
    """Премия растёт с перевыполнением нормы; прогул лишает премии за месяц. Возвращает (%, ₽)."""
    if truancy or pct <= settings["threshold"]:
        return 0.0, 0.0
    bonus_pct = min(settings["cap"], round((pct - settings["threshold"]) * settings["per_pct"], 1))
    return bonus_pct, round(earned * bonus_pct / 100, 2)


def month_stats(conn, year, month) -> list[dict]:
    """Строки ведомости: часы по табелю, сдельная выработка и премия за месяц."""
    ym = _month(year, month)
    hours = dict(conn.execute(
        "SELECT employee_id, SUM(hours_worked) FROM timesheet WHERE strftime('%Y-%m', work_date) = ? GROUP BY employee_id",
        (ym,)).fetchall())
    truancy = dict(conn.execute(
        """SELECT employee_id, COUNT(*) FROM timesheet
           WHERE strftime('%Y-%m', work_date) = ? AND absence_code = 'П' GROUP BY employee_id""", (ym,)).fetchall())
    output = {r["employee_id"]: r for r in conn.execute("""
        SELECT employee_id, SUM(norm_hours) AS norm_hours, SUM(earned) AS earned,
               SUM(qty_good) AS good, SUM(qty_defect) AS defect
        FROM v_result_earnings WHERE strftime('%Y-%m', report_date) = ?
        GROUP BY employee_id""", (ym,)).fetchall()}
    settings = bonus_settings(conn)
    rows = []
    # уволенные попадают в ведомость, только если работали в этом месяце
    for e in employees(conn):
        if e["position"] == "Мастер участка" or (e["dismissal_date"] and e["id"] not in hours and e["id"] not in output):
            continue
        out = output.get(e["id"])
        h = hours.get(e["id"]) or 0
        norm_h = out["norm_hours"] if out else 0.0
        earned = round(out["earned"], 2) if out else 0.0
        pct = norm_h / h * 100 if h else 0.0
        bonus_pct, bonus = calc_bonus(pct, earned, truancy.get(e["id"], 0), settings)
        rows.append({
            "employee": e,
            "hours": h,
            "norm_hours": norm_h,
            "pct": pct,
            "good": out["good"] if out else 0,
            "defect": out["defect"] if out else 0,
            "earned": earned,
            "truancy": truancy.get(e["id"], 0),
            "bonus_pct": bonus_pct,
            "bonus": bonus,
            "total": round(earned + bonus, 2),
        })
    return rows


def employee_results(conn, employee_id, year, month) -> list[sqlite3.Row]:
    """Выработка сотрудника по отчётам за месяц — для карточки."""
    return conn.execute("""
        SELECT ve.report_date, wo.number, p.name AS product, o.name AS op_name,
               ve.qty_good, ve.qty_defect, ve.norm_hours, ve.earned
        FROM v_result_earnings ve
        JOIN work_orders wo ON wo.id = ve.work_order_id
        JOIN products p ON p.id = wo.product_id
        JOIN operations o ON o.id = wo.operation_id
        WHERE ve.employee_id = ? AND strftime('%Y-%m', ve.report_date) = ?
        ORDER BY ve.report_date, ve.result_id""", (employee_id, _month(year, month))).fetchall()


def defects_by_reason(conn, year, month) -> list[tuple[str, int]]:
    return [tuple(r) for r in conn.execute("""
        SELECT dr.name, COALESCE(SUM(ve.qty_defect), 0)
        FROM defect_reasons dr
        LEFT JOIN v_result_earnings ve ON ve.defect_reason_id = dr.id AND strftime('%Y-%m', ve.report_date) = ?
        GROUP BY dr.id ORDER BY dr.id""", (_month(year, month),)).fetchall()]


def timesheet_month(conn, year, month) -> dict[tuple[int, str], tuple[str, float]]:
    rows = conn.execute(
        "SELECT employee_id, work_date, absence_code, hours_worked FROM timesheet WHERE strftime('%Y-%m', work_date) = ?",
        (_month(year, month),)).fetchall()
    return {(r[0], r[1]): (r[2], r[3]) for r in rows}


def cycle_timesheet(conn, user_id, employee_id, day: date, today: date) -> str:
    """Следующий код явки по кругу Я → Б → О → П → В."""
    if day > today:
        raise ValidationError("Табель нельзя заполнять на будущие дни.")
    row = conn.execute("SELECT id, absence_code FROM timesheet WHERE employee_id = ? AND work_date = ?",
                       (employee_id, day.isoformat())).fetchone()
    if row is None:
        code = codes.PRESENT
        cur = conn.execute(
            "INSERT INTO timesheet (employee_id, work_date, shift_id, absence_code, hours_worked) VALUES (?, ?, 1, ?, ?)",
            (employee_id, day.isoformat(), code, shift_hours(day)))
        row_id, action = cur.lastrowid, "INSERT"
    else:
        cycle = codes.ABSENCE_CYCLE
        code = cycle[(cycle.index(row["absence_code"]) + 1) % len(cycle)]
        conn.execute("UPDATE timesheet SET absence_code = ?, hours_worked = ? WHERE id = ?",
                     (code, shift_hours(day) if code == codes.PRESENT else 0, row["id"]))
        row_id, action = row["id"], "UPDATE"
    audit(conn, user_id, action, "timesheet", row_id,
          f"Табель: {employee(conn, employee_id)['short_name']}, {day:%d.%m} → {code}")
    conn.commit()
    return code


def set_grade_rate(conn, user_id, grade, rate) -> None:
    if rate <= 0:
        raise ValidationError("Ставка должна быть больше нуля.")
    old = conn.execute("SELECT hourly_rate FROM grades WHERE grade = ?", (grade,)).fetchone()[0]
    conn.execute("UPDATE grades SET hourly_rate = ? WHERE grade = ?", (rate, grade))
    audit(conn, user_id, "UPDATE", "grades", grade, f"Ставка {grade} разряда: {old:g} → {rate:g} ₽/ч")
    conn.commit()


def add_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29 февраля
        return d.replace(year=d.year + 1, day=28)


def permit_state(valid_until: str, today: date) -> tuple[str, str]:
    days = (date.fromisoformat(valid_until) - today).days
    if days < 0:
        return "bad", "Истёк"
    if days <= 30:
        return "warn", f"Истекает через {days} дн."
    return "good", "Действует"


def has_valid_permit(conn, employee_id, operation_id, today: date) -> bool:
    return conn.execute(
        "SELECT 1 FROM employee_permits WHERE employee_id = ? AND operation_id = ? AND valid_until >= ?",
        (employee_id, operation_id, today.isoformat())).fetchone() is not None


def permit_operations(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM operations WHERE requires_permit = 1 ORDER BY code").fetchall()


def permits(conn, employee_id=None) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT ep.*, {SHORT_NAME} AS short_name, e.dismissal_date, o.code, o.name
        FROM employee_permits ep
        JOIN employees e ON e.id = ep.employee_id
        JOIN operations o ON o.id = ep.operation_id
        WHERE ? IS NULL OR ep.employee_id = ?
        ORDER BY ep.valid_until""", (employee_id, employee_id)).fetchall()


def grant_permit(conn, user_id, employee_id, operation_id, valid_until: date, today: date) -> None:
    """Выдаёт допуск; если он уже есть, заменяет срок."""
    if valid_until <= today:
        raise ValidationError("Срок действия должен быть позже сегодняшней даты.")
    op = conn.execute("SELECT * FROM operations WHERE id = ?", (operation_id,)).fetchone()
    if not op["requires_permit"]:
        raise ValidationError(f"Для операции «{op['name']}» допуск не требуется.")
    emp = employee(conn, employee_id)
    if emp["grade"] < op["required_grade"]:
        raise ValidationError(f"Для операции «{op['name']}» нужен {op['required_grade']} разряд, у сотрудника — {emp['grade']}.")
    conn.execute(
        """INSERT INTO employee_permits (employee_id, operation_id, valid_until) VALUES (?, ?, ?)
           ON CONFLICT (employee_id, operation_id) DO UPDATE SET valid_until = excluded.valid_until""",
        (employee_id, operation_id, valid_until.isoformat()))
    permit_id = conn.execute("SELECT id FROM employee_permits WHERE employee_id = ? AND operation_id = ?",
                             (employee_id, operation_id)).fetchone()[0]
    audit(conn, user_id, "UPDATE", "employee_permits", permit_id,
          f"Допуск {emp['short_name']} к «{op['name']}» до {_dmy(valid_until)}")
    conn.commit()


def extend_permit(conn, user_id, permit_id, today: date) -> date:
    """Продление на год: от текущего срока, а истёкшего — от сегодня."""
    p = next(p for p in permits(conn) if p["id"] == permit_id)
    new = add_year(max(date.fromisoformat(p["valid_until"]), today))
    conn.execute("UPDATE employee_permits SET valid_until = ? WHERE id = ?", (new.isoformat(), permit_id))
    audit(conn, user_id, "UPDATE", "employee_permits", permit_id,
          f"Допуск {p['short_name']} к «{p['name']}» продлён до {_dmy(new)}")
    conn.commit()
    return new


def positions(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM positions ORDER BY id").fetchall()


def sections(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM sections ORDER BY id").fetchall()


def next_personnel_number(conn) -> str:
    numbers = [int(r[0][2:]) for r in conn.execute("SELECT personnel_number FROM employees") if r[0][2:].isdigit()]
    return f"Т-{max(numbers, default=0) + 1:04d}"


def save_employee(conn, user_id, data: dict, today: date, employee_id=None) -> int:
    """Создаёт или изменяет сотрудника. data: personnel_number, last_name, first_name, middle_name,
    position_id, section_id, grade, hire_date (date)."""
    tab = data["personnel_number"].strip()
    if tab[:1] in ("T", "t"):  # латинская T вместо кириллической
        tab = "Т" + tab[1:]
    last, first, middle = (data[k].strip() for k in ("last_name", "first_name", "middle_name"))
    if not TAB_RE.match(tab):
        raise ValidationError("Табельный номер — в формате Т-0000.")
    taken = conn.execute("SELECT id FROM employees WHERE personnel_number = ?", (tab,)).fetchone()
    if taken and taken[0] != employee_id:
        raise ValidationError(f"Табельный номер {tab} уже занят.")
    if not NAME_RE.match(last) or not NAME_RE.match(first):
        raise ValidationError("Фамилия и имя — с заглавной буквы, только буквы и дефис.")
    if middle and not NAME_RE.match(middle):
        raise ValidationError("Отчество — с заглавной буквы, только буквы и дефис.")
    if data["hire_date"] > today:
        raise ValidationError("Дата приёма не может быть позже сегодняшней.")
    values = (tab, last, first, middle or None, data["position_id"], data["section_id"], data["grade"],
              data["hire_date"].isoformat())
    if employee_id:
        conn.execute(
            """UPDATE employees SET personnel_number = ?, last_name = ?, first_name = ?, middle_name = ?,
                      position_id = ?, section_id = ?, grade = ?, hire_date = ? WHERE id = ?""",
            (*values, employee_id))
        action = "UPDATE"
    else:
        employee_id = conn.execute(
            """INSERT INTO employees (personnel_number, last_name, first_name, middle_name,
                                      position_id, section_id, grade, hire_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values).lastrowid
        action = "INSERT"
    short = employee(conn, employee_id)["short_name"]
    audit(conn, user_id, action, "employees", employee_id,
          f"{'Изменены данные сотрудника' if action == 'UPDATE' else 'Принят сотрудник'} {short} ({tab})")
    conn.commit()
    return employee_id


def fire_employee(conn, user_id, employee_id, today: date) -> None:
    e = employee(conn, employee_id)
    if e["dismissal_date"]:
        raise ValidationError(f"{e['short_name']} уже уволен {_dmy(e['dismissal_date'])}.")
    open_orders = conn.execute(
        f"SELECT COUNT(*) FROM work_orders WHERE employee_id = ? AND status_id IN ({','.join('?' * len(codes.OPEN_STATUSES))})",
        (employee_id, *codes.OPEN_STATUSES)).fetchone()[0]
    if open_orders:
        raise ValidationError(f"Нельзя уволить {e['short_name']}: открытых нарядов — {open_orders}. "
                              "Закройте их или выдайте другому исполнителю.")
    conn.execute("UPDATE employees SET dismissal_date = ? WHERE id = ?", (today.isoformat(), employee_id))
    conn.execute("UPDATE users SET is_active = 0 WHERE employee_id = ?", (employee_id,))
    audit(conn, user_id, "UPDATE", "employees", employee_id,
          f"Уволен сотрудник {e['short_name']} ({e['personnel_number']}), учётная запись отключена")
    conn.commit()


def audit_entries(conn, limit=500) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT a.ts, COALESCE(u.login, '—') AS login, a.action, a.entity, a.entity_id, a.details
        FROM audit_log a LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.ts DESC, a.id DESC LIMIT ?""", (limit,)).fetchall()


def alerts(conn, today: date) -> list[tuple[str, str]]:
    """Что требует внимания мастера: (уровень, текст)."""
    out = []
    for p in permits(conn):
        level, text = permit_state(p["valid_until"], today)
        if level != "good" and not p["dismissal_date"]:
            out.append((level, f"{text}: допуск {p['short_name']} к операции «{p['name']}», срок {_dmy(p['valid_until'])}"))
    waiting = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status_id = ?", (codes.ST_DONE,)).fetchone()[0]
    if waiting:
        out.append(("info", f"Выполненных нарядов ждут приёмки: {waiting}"))
    for s in month_stats(conn, today.year, today.month):
        if s["truancy"]:
            out.append(("bad", f"Прогул: {s['employee']['short_name']} — премия за месяц не начисляется"))
    return out
