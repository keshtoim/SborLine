from calendar import monthrange
from datetime import date

# производственный календарь РФ на 2026 год
HOLIDAYS = {date(2026, 1, d) for d in range(1, 9)} | {
    date(2026, 2, 23), date(2026, 3, 9), date(2026, 5, 1), date(2026, 5, 11),
    date(2026, 6, 12), date(2026, 11, 4), date(2026, 12, 31),
}
SHORT_DAYS = {date(2026, 4, 30), date(2026, 5, 8), date(2026, 6, 11), date(2026, 11, 3)}
SHIFT_HOURS = 8


def is_day_off(d: date) -> bool:
    return d.weekday() >= 5 or d in HOLIDAYS


def shift_hours(d: date) -> int:
    return SHIFT_HOURS - 1 if d in SHORT_DAYS else SHIFT_HOURS


def month_days(year: int, month: int) -> list[date]:
    return [date(year, month, d) for d in range(1, monthrange(year, month)[1] + 1)]
