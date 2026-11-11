from sborline import db


def test_schema_is_idempotent():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM order_statuses").fetchone()[0] == 4
    assert conn.execute("SELECT threshold FROM bonus_settings").fetchone()[0] == 100
    assert db.is_empty(conn)


def test_migrates_first_version_db():
    conn = db.connect(":memory:")
    conn.executescript("""
        CREATE TABLE operations (id INTEGER PRIMARY KEY, code TEXT, name TEXT, required_grade INTEGER);
        CREATE TABLE audit_log (id INTEGER PRIMARY KEY, user_id INTEGER, ts DATETIME, action TEXT, entity TEXT, entity_id INTEGER);
        INSERT INTO operations VALUES (1, 'О-010', 'Запрессовка', 3);""")
    db.init_schema(conn)
    assert conn.execute("SELECT requires_permit FROM operations").fetchone()[0] == 0
    conn.execute("INSERT INTO audit_log (action, entity, details) VALUES ('LOGIN', 'users', 'x')")
