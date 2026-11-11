import hashlib
import hmac
import os
import sqlite3

from .services import audit

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, iterations, salt, expected = stored.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def authenticate(conn: sqlite3.Connection, login: str, password: str) -> sqlite3.Row | None:
    user = conn.execute(
        """SELECT u.id, u.login, u.password_hash, u.employee_id, r.name AS role
           FROM users u JOIN roles r ON r.id = u.role_id
           WHERE u.login = ? AND u.is_active = 1""",
        (login.strip(),),
    ).fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    audit(conn, user["id"], "LOGIN", "users", user["id"], "Вход в систему")
    conn.commit()
    return user
