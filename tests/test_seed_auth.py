from sborline import auth


def test_seed_fills_month_up_to_today(conn):
    rows = conn.execute("SELECT MIN(work_date), MAX(work_date) FROM timesheet").fetchone()
    assert tuple(rows) == ("2026-11-01", "2026-11-11")
    holiday = conn.execute("SELECT DISTINCT absence_code FROM timesheet WHERE work_date = '2026-11-04'").fetchall()
    assert [r[0] for r in holiday] == ["В"]


def test_seed_results_never_exceed_plan(conn):
    over = conn.execute(
        """SELECT wo.number FROM work_orders wo JOIN work_results wr ON wr.work_order_id = wo.id
           GROUP BY wo.id HAVING SUM(wr.qty_good) > wo.planned_qty""").fetchall()
    assert over == []


def test_authenticate(conn):
    assert auth.authenticate(conn, "belova", "belova")["role"] == "master"
    assert auth.authenticate(conn, "belova", "wrong") is None
    assert auth.authenticate(conn, "nobody", "x") is None
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'LOGIN'").fetchone()[0] == 1
