"""İş günü hesabı (hafta sonu + opsiyonel tatil listesi)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable


def _to_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def parse_holidays(holidays: Iterable[str] | None) -> set[date]:
    """config'teki 'YYYY-MM-DD' listesini date kümesine çevirir."""
    result: set[date] = set()
    for item in holidays or []:
        try:
            result.add(datetime.strptime(str(item).strip(), "%Y-%m-%d").date())
        except ValueError:
            continue
    return result


def is_working_day(day: date, holidays: set[date]) -> bool:
    """Hafta içi (Pzt-Cum) ve tatil değilse iş günüdür."""
    return day.weekday() < 5 and day not in holidays


def working_days_between(
    start: datetime | date,
    end: datetime | date,
    holidays: Iterable[str] | set[date] | None = None,
) -> int:
    """start ile end arasındaki TAM iş günü sayısı (start hariç, end dahil mantığı).

    Negatif aralıkta 0 döner. 'start'ın kendisi sayılmaz; aradaki ve end'e kadar
    olan iş günleri sayılır. Bu, "son yorumdan bu yana kaç iş günü geçti"
    sorusuna uygundur.
    """
    start_d = _to_date(start)
    end_d = _to_date(end)
    if end_d <= start_d:
        return 0

    if isinstance(holidays, set):
        holiday_set = holidays
    else:
        holiday_set = parse_holidays(holidays)  # type: ignore[arg-type]

    count = 0
    cursor = start_d + timedelta(days=1)
    while cursor <= end_d:
        if is_working_day(cursor, holiday_set):
            count += 1
        cursor += timedelta(days=1)
    return count
