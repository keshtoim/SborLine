# id совпадают с INSERT в schema.sql
ROLE_ADMIN, ROLE_MASTER, ROLE_WORKER, ROLE_ACCOUNTANT = 1, 2, 3, 4
ROLE_TITLES = {
    "admin": "Администратор",
    "master": "Мастер участка",
    "worker": "Сборщик",
    "accountant": "Бухгалтер",
}

ST_ISSUED, ST_PROGRESS, ST_DONE, ST_ACCEPTED = 1, 2, 3, 4
OPEN_STATUSES = (ST_ISSUED, ST_PROGRESS)

PRESENT = "Я"
DAY_OFF = "В"
ABSENCE_CYCLE = ["Я", "Б", "О", "П", "В"]
