from datetime import datetime, timedelta
from fractions import Fraction


def daily_series(count, ticker="A", end_date=datetime(2026, 11, 12)):
    result = []
    for i in range(count):
        date = int((end_date - timedelta(days=count - 1 - i)).strftime("%Y%m%d"))
        close = 100 + (i * 19) % 71
        result.append(
            (
                ticker,
                date,
                close - 1,
                close + 3,
                close - 4,
                close,
                i + 1,
                close * (i + 1),
            )
        )
    return result


def daily_wire(rows):
    keys = (
        "stck_bsop_date",
        "stck_oprc",
        "stck_hgpr",
        "stck_lwpr",
        "stck_clpr",
        "acml_vol",
        "acml_tr_pbmn",
    )
    return [dict(zip(keys, map(str, row[1:]), strict=True)) for row in rows]


def minute_series(count, ticker="A"):
    result = []
    for i in range(count):
        day, minute = divmod(i, 391)
        at = datetime(2026, 11, 9, 9) + timedelta(days=day, minutes=minute)
        close = 100 + (i * 11) % 67
        result.append(
            (
                ticker,
                int(at.strftime("%Y%m%d")),
                int(at.strftime("%H%M%S")),
                close,
                close + 1,
                close - 1,
                close,
                i + 1,
                close * (i + 1),
            )
        )
    return result


def minute_wire(rows):
    cumulative = {}
    result = []
    for row in rows:
        ticker, date, time, open_, high, low, close, volume, amount = row
        cumulative[date] = cumulative.get(date, 0) + amount
        result.append(
            dict(
                zip(
                    (
                        "stck_bsop_date",
                        "stck_cntg_hour",
                        "stck_oprc",
                        "stck_hgpr",
                        "stck_lwpr",
                        "stck_prpr",
                        "cntg_vol",
                        "acml_tr_pbmn",
                    ),
                    (
                        str(date),
                        f"{time:06}",
                        str(open_),
                        str(high),
                        str(low),
                        str(close),
                        str(volume),
                        str(cumulative[date]),
                    ),
                    strict=True,
                )
            )
        )
    return result


def ma_reference(rows, minute=False, retention=None):
    result = []
    closes = []
    for row in rows:
        closes.append(row[6 if minute else 5])
        values = [
            round(float(Fraction(sum(closes[-p:]), p)), 2) if len(closes) >= p else None
            for p in (5, 10, 20, 60, 120, 200)
        ]
        result.append((*row[: 3 if minute else 2], *values))
    return result[-retention:] if retention else result
