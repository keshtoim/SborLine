"""Демонстрационные данные цеха сборки мебельной фурнитуры: справочники и выработка за текущий месяц."""
import random
import sqlite3
from datetime import date, timedelta

from . import codes
from .auth import hash_password
from .workcal import is_day_off, month_days, shift_hours

# логин совпадает с паролем — только для демо-базы
DEMO_USERS = [
    ("admin", codes.ROLE_ADMIN, None),
    ("belova", codes.ROLE_MASTER, 7),
    ("petrov", codes.ROLE_WORKER, 1),
    ("buh", codes.ROLE_ACCOUNTANT, None),
]

EMPLOYEES = [
    (1, "Т-0142", "Петров", "Иван", "Сергеевич", 2, 1, 4, "2019-03-11"),
    (2, "Т-0157", "Сидорова", "Анна", "Викторовна", 1, 1, 3, "2021-08-02"),
    (3, "Т-0163", "Кузнецов", "Дмитрий", "Олегович", 2, 2, 5, "2016-05-16"),
    (4, "Т-0171", "Галиева", "Лейла", "Рашидовна", 1, 2, 3, "2022-02-14"),
    (5, "Т-0188", "Морозов", "Павел", "Андреевич", 1, 3, 2, "2024-09-09"),
    (6, "Т-0193", "Ершов", "Константин", "Ильич", 2, 2, 4, "2020-11-23"),
    (7, "Т-0105", "Белова", "Ольга", "Николаевна", 3, 1, 6, "2012-04-02"),
]

# допуск нужен для работы на прессе и испытательных стендах
OPERATIONS = [
    (1, "О-010", "Запрессовка осей и втулок", 3, 0),
    (2, "О-020", "Сборка корпуса", 3, 0),
    (3, "О-030", "Клёпка на пневмопрессе", 4, 1),
    (4, "О-040", "Испытание на ресурс открываний", 5, 1),
    (5, "О-050", "Контроль усилия газлифта", 4, 1),
    (6, "О-090", "Упаковка", 2, 0),
]

PRODUCTS = [
    (1, "ПТ-110.000", "Петля накладная с доводчиком"),
    (2, "НШ-450.000", "Направляющие шариковые 450 мм"),
    (3, "ГЛ-100.000", "Газлифт для фасада 100N"),
]

# допуски: (сотрудник, операция, дней до окончания); есть истёкший и истекающие
PERMITS = [(3, 4, 190), (6, 3, 14), (6, 5, 82), (1, 3, 23), (4, 3, -11)]

# норма времени на единицу, мин: фурнитура собирается сотнями штук за смену
ROUTES = [
    (1, 1, 10, 1.2), (1, 2, 20, 1.5), (1, 4, 30, 0.8), (1, 6, 40, 0.3),
    (2, 1, 10, 1.5), (2, 2, 20, 2.5), (2, 3, 30, 1.0), (2, 6, 40, 0.6),
    (3, 3, 10, 1.2), (3, 2, 20, 2.0), (3, 5, 30, 0.7), (3, 6, 40, 0.4),
]

# какие пары (изделие, операция) выполняет сборщик и его средний темп относительно нормы
WORK_PLAN = {
    1: ([(1, 1), (1, 2), (2, 3)], 1.08),
    2: ([(1, 1), (1, 2), (2, 1)], 0.94),
    3: ([(1, 4), (2, 2)], 1.12),
    4: ([(2, 1), (2, 2)], 0.87),
    5: ([(1, 6), (2, 6), (3, 6)], 1.00),
    6: ([(3, 3), (3, 5)], 1.02),
}

# неявки по номеру рабочего дня месяца
ABSENCES = {(4, 2): "Б", (4, 3): "Б", (2, 5): "О", (2, 6): "О", (5, 6): "П"}


def seed_demo(conn: sqlite3.Connection, today: date) -> None:
    rnd = random.Random(42)
    conn.executemany("INSERT INTO sections (id, name) VALUES (?, ?)",
                     [(1, "Сборка петель"), (2, "Сборка направляющих и газлифтов"), (3, "Упаковка")])
    conn.executemany("INSERT INTO positions (id, name) VALUES (?, ?)",
                     [(1, "Сборщик"), (2, "Слесарь-сборщик"), (3, "Мастер участка")])
    conn.executemany("INSERT INTO grades (grade, hourly_rate) VALUES (?, ?)",
                     [(1, 210), (2, 235), (3, 265), (4, 300), (5, 345), (6, 395)])
    conn.executemany(
        """INSERT INTO employees (id, personnel_number, last_name, first_name, middle_name,
                                  position_id, section_id, grade, hire_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", EMPLOYEES)
    conn.executemany("INSERT INTO products (id, article, name) VALUES (?, ?, ?)", PRODUCTS)
    conn.executemany("INSERT INTO operations (id, code, name, required_grade, requires_permit) VALUES (?, ?, ?, ?, ?)",
                     OPERATIONS)
    conn.executemany(
        "INSERT INTO product_operations (product_id, operation_id, seq_no, norm_minutes) VALUES (?, ?, ?, ?)",
        ROUTES)
    conn.execute("INSERT INTO shifts (id, name, start_time, end_time) VALUES (1, '1-я смена', '08:00', '16:30')")
    conn.executemany("INSERT INTO defect_reasons (id, name) VALUES (?, ?)",
                     [(1, "Дефект комплектующих"), (2, "Нарушение технологии"), (3, "Повреждение покрытия")])
    for login, role, emp in DEMO_USERS:
        conn.execute("INSERT INTO users (login, password_hash, role_id, employee_id) VALUES (?, ?, ?, ?)",
                     (login, hash_password(login), role, emp))
    master_id = conn.execute("SELECT id FROM users WHERE login = 'belova'").fetchone()[0]
    conn.executemany("INSERT INTO employee_permits (employee_id, operation_id, valid_until) VALUES (?, ?, ?)",
                     [(e, o, (today + timedelta(days=d)).isoformat()) for e, o, d in PERMITS])
    short_names = {e[0]: f"{e[2]} {e[3][0]}.{e[4][0]}." for e in EMPLOYEES}
    op_names = {o[0]: o[2] for o in OPERATIONS}

    days = [d for d in month_days(today.year, today.month) if d <= today]
    workdays_by_emp = {}
    for emp in EMPLOYEES:
        emp_id, workday_no, present = emp[0], 0, []
        for d in days:
            if is_day_off(d):
                code = codes.DAY_OFF
            else:
                workday_no += 1
                code = ABSENCES.get((emp_id, workday_no), codes.PRESENT)
            hours = shift_hours(d) if code == codes.PRESENT else 0
            conn.execute(
                "INSERT INTO timesheet (employee_id, work_date, shift_id, absence_code, hours_worked) VALUES (?, ?, 1, ?, ?)",
                (emp_id, d.isoformat(), code, hours))
            if code == codes.PRESENT:
                present.append(d)
        workdays_by_emp[emp_id] = present

    norms = {(p, o): n for p, o, _, n in ROUTES}
    orders = []
    for emp_id, (jobs, pace) in WORK_PLAN.items():
        workdays = workdays_by_emp[emp_id]
        if not workdays:
            continue

        def day_minutes(d):
            return 60 * shift_hours(d) * pace * rnd.uniform(0.92, 1.08)

        # остаток смены после закрытия наряда уходит на следующий наряд в тот же день
        i, job, minutes = 0, 0, day_minutes(workdays[0])
        while i < len(workdays):
            p, o = jobs[job % len(jobs)]
            job += 1
            norm = norms[(p, o)]
            qty = max(50, round(480 / norm * pace * rnd.choice((2, 3)) / 50) * 50)
            order = {"date": workdays[i], "emp": emp_id, "p": p, "o": o, "qty": qty, "results": []}
            left = qty
            while left > 0 and i < len(workdays):
                made = min(left, int(minutes // norm))
                if made > 0:
                    # брак — доли процента от партии, и не в каждом отчёте
                    defect = max(1, round(made * rnd.uniform(0.002, 0.008))) if rnd.random() < 0.35 else 0
                    order["results"].append((workdays[i], made, defect, rnd.randint(1, 3) if defect else None))
                    left -= made
                    minutes -= made * norm
                if left > 0 or minutes < norm:
                    i += 1
                    if i < len(workdays):
                        minutes = day_minutes(workdays[i])
            orders.append(order)

    orders.sort(key=lambda x: (x["date"], x["emp"]))
    orders.append({"date": today, "emp": 6, "p": 3, "o": 5, "qty": 600, "results": []})
    for n, o in enumerate(orders, start=1):
        good = sum(r[1] for r in o["results"])
        last = o["results"][-1][0] if o["results"] else None
        if good >= o["qty"]:
            status = codes.ST_ACCEPTED if last < today - timedelta(days=1) else codes.ST_DONE
        else:
            status = codes.ST_PROGRESS if good else codes.ST_ISSUED
        cur = conn.execute(
            """INSERT INTO work_orders (number, issue_date, employee_id, product_id, operation_id,
                                        planned_qty, status_id, issued_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"Н-{1100 + n}", o["date"].isoformat(), o["emp"], o["p"], o["o"], o["qty"], status, master_id))
        conn.execute(
            "INSERT INTO audit_log (user_id, ts, action, entity, entity_id, details) VALUES (?, ?, 'INSERT', 'work_orders', ?, ?)",
            (master_id, f"{o['date'].isoformat()} 07:{40 + o['emp']:02d}:00", cur.lastrowid,
             f"Выдан наряд Н-{1100 + n}: {short_names[o['emp']]}, {op_names[o['o']]} × {o['qty']}"))
        accepted_by = master_id if status == codes.ST_ACCEPTED else None
        conn.executemany(
            """INSERT INTO work_results (work_order_id, report_date, qty_good, qty_defect, defect_reason_id, accepted_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(cur.lastrowid, d.isoformat(), g, df, r, accepted_by) for d, g, df, r in o["results"]])
    conn.commit()
