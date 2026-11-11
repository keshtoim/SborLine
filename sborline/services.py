import sqlite3
from datetime import date

from . import codes
from .workcal import shift_hours

SHORT_NAME = "e.last_name || ' ' || substr(e.first_name, 1, 1) || '.' || COALESCE(substr(e.middle_name, 1, 1) || '.', '')"


class ValidationError(Exception):
    pass


def _audit(conn, user_id, action, entity, entity_id):
    conn.execute("INSERT INTO audit_log (user_id, action, entity, entity_id) VALUES (?, ?, ?, ?)",
                 (user_id, action, entity, entity_id))


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
        SELECT rr.*, o.code, o.name
        FROM v_route_rates rr JOIN operations o ON o.id = rr.operation_id
        WHERE rr.product_id = ? ORDER BY rr.seq_no""", (product_id,)).fetchall()


def route_step(conn, product_id, operation_id) -> sqlite3.Row | None:
    return conn.execute("""
        SELECT rr.*, o.code, o.name
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
    next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM work_orders").fetchone()[0]
    number = f"Н-{1100 + next_id}"
    cur = conn.execute(
        """INSERT INTO work_orders (number, issue_date, employee_id, product_id, operation_id,
                                    planned_qty, status_id, issued_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (number, today.isoformat(), employee_id, product_id, operation_id, qty, codes.ST_ISSUED, user_id))
    _audit(conn, user_id, "INSERT", "work_orders", cur.lastrowid)
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
    _audit(conn, user_id, "INSERT", "work_results", cur.lastrowid)
    conn.commit()
    return status


def accept_order(conn, user_id, order_id) -> None:
    o = order(conn, order_id)
    if o["status_id"] != codes.ST_DONE:
        raise ValidationError(f"Принять можно только выполненный наряд, а {o['number']} — «{o['status']}».")
    conn.execute("UPDATE work_orders SET status_id = ? WHERE id = ?", (codes.ST_ACCEPTED, order_id))
    conn.execute("UPDATE work_results SET accepted_by = ? WHERE work_order_id = ?", (user_id, order_id))
    _audit(conn, user_id, "UPDATE", "work_orders", order_id)
    conn.commit()


def month_stats(conn, year, month) -> list[dict]:
    """Строки ведомости: часы по табелю и сдельная выработка за месяц."""
    ym = _month(year, month)
    hours = dict(conn.execute(
        "SELECT employee_id, SUM(hours_worked) FROM timesheet WHERE strftime('%Y-%m', work_date) = ? GROUP BY employee_id",
        (ym,)).fetchall())
    output = {r["employee_id"]: r for r in conn.execute("""
        SELECT employee_id, SUM(norm_hours) AS norm_hours, SUM(earned) AS earned,
               SUM(qty_good) AS good, SUM(qty_defect) AS defect
        FROM v_result_earnings WHERE strftime('%Y-%m', report_date) = ?
        GROUP BY employee_id""", (ym,)).fetchall()}
    rows = []
    for e in workers(conn):
        out = output.get(e["id"])
        h = hours.get(e["id"]) or 0
        norm_h = out["norm_hours"] if out else 0.0
        rows.append({
            "employee": e,
            "hours": h,
            "norm_hours": norm_h,
            "pct": norm_h / h * 100 if h else 0.0,
            "good": out["good"] if out else 0,
            "defect": out["defect"] if out else 0,
            "earned": round(out["earned"], 2) if out else 0.0,
        })
    return rows


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
    _audit(conn, user_id, action, "timesheet", row_id)
    conn.commit()
    return code


def set_grade_rate(conn, user_id, grade, rate) -> None:
    if rate <= 0:
        raise ValidationError("Ставка должна быть больше нуля.")
    conn.execute("UPDATE grades SET hourly_rate = ? WHERE grade = ?", (rate, grade))
    _audit(conn, user_id, "UPDATE", "grades", grade)
    conn.commit()
