PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sections (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS positions (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

-- тарифная сетка
CREATE TABLE IF NOT EXISTS grades (
    grade        INTEGER PRIMARY KEY CHECK (grade BETWEEN 1 AND 6),
    hourly_rate  NUMERIC NOT NULL CHECK (hourly_rate > 0)
);

CREATE TABLE IF NOT EXISTS employees (
    id               INTEGER PRIMARY KEY,
    personnel_number TEXT    NOT NULL UNIQUE,
    last_name        TEXT    NOT NULL,
    first_name       TEXT    NOT NULL,
    middle_name      TEXT,
    position_id      INTEGER NOT NULL REFERENCES positions(id),
    section_id       INTEGER NOT NULL REFERENCES sections(id),
    grade            INTEGER NOT NULL REFERENCES grades(grade),
    hire_date        DATE    NOT NULL,
    dismissal_date   DATE,
    CHECK (dismissal_date IS NULL OR dismissal_date >= hire_date)
);

CREATE TABLE IF NOT EXISTS products (
    id       INTEGER PRIMARY KEY,
    article  TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
    id               INTEGER PRIMARY KEY,
    code             TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    required_grade   INTEGER NOT NULL REFERENCES grades(grade),
    requires_permit  INTEGER NOT NULL DEFAULT 0
);

-- допуск сотрудника к операции, для которой requires_permit = 1
CREATE TABLE IF NOT EXISTS employee_permits (
    id            INTEGER PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(id),
    operation_id  INTEGER NOT NULL REFERENCES operations(id),
    valid_until   DATE    NOT NULL,
    UNIQUE (employee_id, operation_id)
);

-- условия премирования: одна строка
CREATE TABLE IF NOT EXISTS bonus_settings (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    threshold  NUMERIC NOT NULL CHECK (threshold BETWEEN 50 AND 150),
    per_pct    NUMERIC NOT NULL CHECK (per_pct BETWEEN 0 AND 10),
    cap        NUMERIC NOT NULL CHECK (cap BETWEEN 0 AND 100)
);

-- норма времени зависит от пары (изделие, операция)
CREATE TABLE IF NOT EXISTS product_operations (
    product_id    INTEGER NOT NULL REFERENCES products(id),
    operation_id  INTEGER NOT NULL REFERENCES operations(id),
    seq_no        INTEGER NOT NULL,
    norm_minutes  NUMERIC NOT NULL CHECK (norm_minutes > 0),
    PRIMARY KEY (product_id, operation_id),
    UNIQUE (product_id, seq_no)
);

CREATE TABLE IF NOT EXISTS shifts (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL
);

CREATE TABLE IF NOT EXISTS absence_types (
    code  TEXT PRIMARY KEY,
    name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_statuses (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS defect_reasons (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS roles (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    login          TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    role_id        INTEGER NOT NULL REFERENCES roles(id),
    employee_id    INTEGER UNIQUE REFERENCES employees(id),
    is_active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS timesheet (
    id            INTEGER PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(id),
    work_date     DATE    NOT NULL,
    shift_id      INTEGER REFERENCES shifts(id),
    absence_code  TEXT    NOT NULL REFERENCES absence_types(code),
    hours_worked  NUMERIC NOT NULL DEFAULT 0 CHECK (hours_worked BETWEEN 0 AND 24),
    UNIQUE (employee_id, work_date)
);

CREATE TABLE IF NOT EXISTS work_orders (
    id            INTEGER PRIMARY KEY,
    number        TEXT    NOT NULL UNIQUE,
    issue_date    DATE    NOT NULL,
    employee_id   INTEGER NOT NULL REFERENCES employees(id),
    product_id    INTEGER NOT NULL,
    operation_id  INTEGER NOT NULL,
    planned_qty   INTEGER NOT NULL CHECK (planned_qty > 0),
    status_id     INTEGER NOT NULL REFERENCES order_statuses(id),
    issued_by     INTEGER NOT NULL REFERENCES users(id),
    FOREIGN KEY (product_id, operation_id)
        REFERENCES product_operations(product_id, operation_id)
);

CREATE TABLE IF NOT EXISTS work_results (
    id               INTEGER PRIMARY KEY,
    work_order_id    INTEGER NOT NULL REFERENCES work_orders(id),
    report_date      DATE    NOT NULL,
    qty_good         INTEGER NOT NULL CHECK (qty_good >= 0),
    qty_defect       INTEGER NOT NULL DEFAULT 0 CHECK (qty_defect >= 0),
    defect_reason_id INTEGER REFERENCES defect_reasons(id),
    accepted_by      INTEGER REFERENCES users(id),
    CHECK (qty_defect = 0 OR defect_reason_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    ts         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    details    TEXT
);

-- системные справочники: код в приложении опирается на эти id
INSERT OR IGNORE INTO roles (id, name) VALUES
    (1, 'admin'), (2, 'master'), (3, 'worker'), (4, 'accountant');

INSERT OR IGNORE INTO order_statuses (id, name) VALUES
    (1, 'Выдан'), (2, 'В работе'), (3, 'Выполнен'), (4, 'Принят');

INSERT OR IGNORE INTO absence_types (code, name) VALUES
    ('Я', 'Явка'), ('Б', 'Больничный'), ('О', 'Отпуск'), ('П', 'Прогул'), ('В', 'Выходной');

INSERT OR IGNORE INTO bonus_settings (id, threshold, per_pct, cap) VALUES (1, 100, 1.5, 25);

-- расценка не хранится, а выводится из нормы и ставки разряда операции
CREATE VIEW IF NOT EXISTS v_route_rates AS
SELECT po.product_id,
       po.operation_id,
       po.seq_no,
       po.norm_minutes,
       o.required_grade,
       ROUND(po.norm_minutes / 60.0 * g.hourly_rate, 2) AS piece_rate
FROM product_operations po
JOIN operations o ON o.id = po.operation_id
JOIN grades g     ON g.grade = o.required_grade;

CREATE VIEW IF NOT EXISTS v_result_earnings AS
SELECT wr.id AS result_id,
       wo.id AS work_order_id,
       wo.employee_id,
       wr.report_date,
       wr.qty_good,
       wr.qty_defect,
       wr.defect_reason_id,
       wr.qty_good * rr.norm_minutes / 60.0 AS norm_hours,
       wr.qty_good * rr.piece_rate          AS earned
FROM work_results wr
JOIN work_orders wo  ON wo.id = wr.work_order_id
JOIN v_route_rates rr ON rr.product_id = wo.product_id
                     AND rr.operation_id = wo.operation_id;
