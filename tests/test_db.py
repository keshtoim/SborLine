from sborline import db


def test_schema_is_idempotent():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM order_statuses").fetchone()[0] == 4
    assert db.is_empty(conn)
