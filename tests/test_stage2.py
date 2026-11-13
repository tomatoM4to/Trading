import copy
import sqlite3
from datetime import datetime, timedelta

import pytest
from core import database

from tests.data import (
    daily_series,
    daily_wire,
    ma_reference,
    minute_series,
    minute_wire,
)
from tests.transport import FakeTransport, response

pytestmark = pytest.mark.stage2


async def test_minute_empty_search_budget_and_cumulative_reset_between_days(
    sandbox, candles
):
    from tasks.minute_ohlcv_scheduler import process_ticker

    with FakeTransport([response([])] * 3) as transport:
        assert await process_ticker("A", max_steps=3) == (False, None)
    assert [c.params["FID_INPUT_DATE_1"] for c in transport.calls] == [
        "20261112",
        "20261111",
        "20261110",
    ]
    assert sandbox.rows("minute_ohlcv") == []
    raw, expected = ([], [])
    for date in (20261112, 20261111):
        for item in candles["minute"][-2:]:
            raw.append({**item, "stck_bsop_date": str(date)})
        expected.extend([(r[0], date, *r[2:]) for r in candles["minute_expected"][:2]])
    with FakeTransport([response(raw)]):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == sorted(expected)
    assert sandbox.rows("minute_ma") == ma_reference(sorted(expected), minute=True)


async def test_minute_overlapping_newest_to_oldest_pages_preserve_every_record(sandbox):
    from tasks.minute_ohlcv_scheduler import process_ticker

    rows = [(r[0], 20261112, *r[2:]) for r in minute_series(240)]
    raw = minute_wire(rows)
    pages = [raw[120:][::-1], raw[1:121][::-1], raw[:2][::-1]]
    with FakeTransport([response(p) for p in pages]) as transport:
        assert await process_ticker("A", max_steps=3) == (True, "20261112125900")
    assert len(transport.calls) == 3
    assert transport.calls[1].params["FID_INPUT_HOUR_1"] == "110000"
    assert transport.calls[2].params["FID_INPUT_HOUR_1"] == "090100"
    assert sandbox.rows("minute_ohlcv") == rows
    assert sandbox.rows("minute_ma") == ma_reference(rows, minute=True)


async def test_minute_write_failure_rolls_back_page_and_can_retry(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    sandbox.write(
        "CREATE TRIGGER reject_minute BEFORE INSERT ON minute_ohlcv WHEN NEW.time=90100 BEGIN SELECT RAISE(ABORT,'injected minute write failure'); END"
    )
    with (
        FakeTransport([response(candles["minute"])]),
        pytest.raises(sqlite3.IntegrityError),
    ):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == []
    sandbox.write("DROP TRIGGER reject_minute")
    with FakeTransport([response(candles["minute"])]):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == [
        tuple(r) for r in candles["minute_expected"]
    ]


async def test_daily_cold_duplicate_revision_and_ma(sandbox):
    from tasks.daily_ohlcv_scheduler import process_ticker

    rows = daily_series(220)
    pages = [rows[120:][::-1], rows[20:120][::-1], rows[:20][::-1]]
    with FakeTransport([response(daily_wire(p)) for p in pages]) as transport:
        assert await process_ticker("A", target_api_calls=3)
    assert sandbox.rows("daily_ohlcv") == rows
    assert sandbox.rows("daily_ma") == ma_reference(rows)
    assert [c.timeout for c in transport.calls] == [10, 10, 10]
    expected_end = datetime(2026, 11, 12)
    for call, page in zip(transport.calls, pages, strict=True):
        assert (
            call.url
            == "https://fixture.invalid/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        )
        assert call.tr_id == "FHKST03010100"
        assert call.params == {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "A",
            "FID_INPUT_DATE_1": (expected_end - timedelta(days=200)).strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": expected_end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        expected_end = datetime.strptime(
            str(min(row[1] for row in page)), "%Y%m%d"
        ) - timedelta(days=1)
    for _ in range(2):
        with FakeTransport([response(daily_wire(p)) for p in pages]) as transport:
            await process_ticker("A", last_date=rows[-1][1])
        assert len(transport.calls) == 3
        assert sandbox.rows("daily_ohlcv") == rows
        assert sandbox.rows("daily_ma") == ma_reference(rows)
    changed = list(rows[-1])
    changed[5] += 1
    rows[-1] = tuple(changed)
    pages[0][0] = changed
    with FakeTransport([response(daily_wire(p)) for p in pages]):
        await process_ticker("A", last_date=changed[1])
    assert sandbox.rows("daily_ohlcv") == rows
    assert sandbox.rows("daily_ma") == ma_reference(rows)


async def test_daily_unordered_duplicate_page_and_latest_gap(sandbox, candles):
    from tasks.daily_ohlcv_scheduler import process_ticker

    raw = candles["daily"]
    expected = [tuple(r) for r in candles["daily_expected"]]
    with FakeTransport([response([raw[2], raw[0], raw[1], raw[2], raw[3]])]):
        await process_ticker("A", target_api_calls=1)
    assert sandbox.rows("daily_ohlcv") == expected
    sandbox.write("DELETE FROM daily_ohlcv WHERE date=?", [(20261112,)])
    with FakeTransport([response(raw)]):
        await process_ticker("A", last_date=20261111)
    assert sandbox.rows("daily_ohlcv") == expected


async def test_daily_empty_error_and_malformed_are_not_committed(sandbox, candles):
    from tasks.daily_ohlcv_scheduler import process_ticker

    with FakeTransport([response([])]):
        await process_ticker("A")
    assert sandbox.rows("daily_ohlcv") == []
    with (
        FakeTransport([response(status=503)]),
        pytest.raises(Exception, match="API Error"),
    ):
        await process_ticker("A")
    bad = copy.deepcopy(candles["daily"])
    bad[1]["stck_clpr"] = "bad-price"
    with FakeTransport([response(bad)]), pytest.raises(ValueError):
        await process_ticker("A", target_api_calls=1)
    assert sandbox.rows("daily_ohlcv") == []


async def test_daily_store_failure_rolls_back_and_retry_restores_all_records(
    sandbox, candles
):
    from tasks.daily_ohlcv_scheduler import process_ticker

    sandbox.write(
        "CREATE TRIGGER reject_daily BEFORE INSERT ON daily_ohlcv WHEN NEW.date=20261111 BEGIN SELECT RAISE(ABORT,'injected write failure'); END"
    )
    with (
        FakeTransport([response(candles["daily"])]),
        pytest.raises(sqlite3.IntegrityError),
    ):
        await process_ticker("A", target_api_calls=1)
    assert sandbox.rows("daily_ohlcv") == []
    sandbox.write("DROP TRIGGER reject_daily")
    with FakeTransport([response(candles["daily"])]):
        await process_ticker("A", target_api_calls=1)
    assert sandbox.rows("daily_ohlcv") == [tuple(r) for r in candles["daily_expected"]]


async def test_minute_cold_start_full_records_and_idempotency(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    for _ in range(2):
        with FakeTransport([response(candles["minute"])]) as transport:
            assert await process_ticker("A", max_steps=1) == (True, "20261112090300")
        call = transport.calls[0]
        assert len(transport.calls) == 1
        assert (
            call.url
            == "https://fixture.invalid/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
        )
        assert call.tr_id == "FHKST03010230"
        assert call.timeout == 10
        assert call.params == {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "A",
            "FID_INPUT_HOUR_1": "153000",
            "FID_INPUT_DATE_1": "20261112",
            "FID_PW_DATA_INCU_YN": "N",
            "FID_FAKE_TICK_INCU_YN": "N",
        }
        assert sandbox.rows("minute_ohlcv") == [
            tuple(r) for r in candles["minute_expected"]
        ]
        assert sandbox.rows("minute_ma") == ma_reference(
            candles["minute_expected"], minute=True
        )


async def test_minute_latest_candle_revision_is_upserted(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    rows = candles["minute_expected"]
    sandbox.write("INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", rows)
    changed = copy.deepcopy(candles["minute"])
    changed[0]["stck_prpr"] = "121"
    changed[0]["cntg_vol"] = "5"
    changed[0]["acml_tr_pbmn"] = "1243"
    expected = copy.deepcopy(rows)
    expected[-1][6:] = [121, 5, 587]
    with FakeTransport([response(changed)]):
        await process_ticker("A", last_datetime="20261112090300", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == [tuple(r) for r in expected]


async def test_minute_increment_preserves_cumulative_baseline(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    sandbox.write(
        "INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
        candles["minute_expected"][:1],
    )
    with FakeTransport([response(candles["minute"])]):
        await process_ticker("A", last_datetime="20261112090000", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == [
        tuple(r) for r in candles["minute_expected"]
    ]


@pytest.mark.parametrize("with_amount", (True, False))
async def test_minute_amount_without_baseline_is_unknown(sandbox, candles, with_amount):
    from tasks.minute_ohlcv_scheduler import process_ticker

    raw = copy.deepcopy(candles["minute"][:2])
    if not with_amount:
        for row in raw:
            del row["acml_tr_pbmn"]
    with FakeTransport([response(raw)]):
        assert (await process_ticker("A", max_steps=1))[0]
    expected = copy.deepcopy(candles["minute_expected"][2:])
    expected[0][-1] = None
    if not with_amount:
        expected[1][-1] = None
    assert sandbox.rows("minute_ohlcv") == [tuple(row) for row in expected]


async def test_minute_same_timestamp_revision_recomputes_ma(sandbox):
    from tasks.minute_ohlcv_scheduler import process_ticker

    rows = minute_series(10)
    sandbox.write("INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", rows)
    changed = list(rows[-1])
    changed[6] += 1
    changed[8] += changed[7]
    rows[-1] = tuple(changed)
    raw = minute_wire(rows)[::-1]
    newest = f"{changed[1]}{changed[2]:06d}"
    with FakeTransport([response(raw)]):
        assert await process_ticker("A", last_datetime=newest, max_steps=1) == (
            True,
            newest,
        )
    assert sandbox.rows("minute_ohlcv") == rows
    assert sandbox.rows("minute_ma") == ma_reference(rows, minute=True)


async def test_minute_page_order_does_not_change_data(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    with FakeTransport([response(candles["minute"][::-1])]):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == [
        tuple(r) for r in candles["minute_expected"]
    ]


async def test_minute_partial_bad_close_must_report_failure(sandbox, candles):
    from tasks.minute_ohlcv_scheduler import process_ticker

    bad = copy.deepcopy(candles["minute"])
    bad[1]["stck_prpr"] = "bad-price"
    with (
        FakeTransport([response(bad)]),
        pytest.raises(ValueError, match="Invalid minute OHLCV response"),
    ):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == []
    assert sandbox.rows("minute_ma") == []


@pytest.mark.parametrize("invalid_price", ("bad-price", "121"))
@pytest.mark.parametrize("reverse", (True, False))
async def test_minute_conflicting_duplicates_cannot_hide_invalid_rows(
    sandbox, candles, invalid_price, reverse
):
    from tasks.minute_ohlcv_scheduler import process_ticker

    raw = copy.deepcopy(candles["minute"])
    raw.append({**raw[0], "stck_prpr": invalid_price})
    if reverse:
        raw.reverse()
    with (
        FakeTransport([response(raw)]),
        pytest.raises(ValueError, match="Invalid minute OHLCV response"),
    ):
        await process_ticker("A", max_steps=1)
    assert sandbox.rows("minute_ohlcv") == []


async def test_minute_ma_retention_has_warmup_for_every_retained_row(sandbox):
    from tasks.minute_ohlcv_scheduler import rebuild_minute_ma_for_ticker

    rows = minute_series(850)
    sandbox.write("INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", rows[::-1])
    conn, ma = (database.connect_sqlite(), database.connect_ma_db())
    try:
        rebuild_minute_ma_for_ticker(conn, ma, "A")
    finally:
        conn.close()
        ma.close()
    assert sandbox.rows("minute_ma") == ma_reference(rows, minute=True, retention=391)


async def test_daily_internal_gap_before_overlap_page_is_recovered(sandbox):
    from tasks.daily_ohlcv_scheduler import process_ticker

    rows = daily_series(110)
    sandbox.write(
        "INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)",
        [row for index, row in enumerate(rows) if index != 5],
    )
    with FakeTransport(
        [response(daily_wire(rows[10:][::-1])), response(daily_wire(rows[:10][::-1]))]
    ):
        await process_ticker("A", last_date=rows[-1][1], target_api_calls=2)
    assert sandbox.rows("daily_ohlcv") == rows


async def test_daily_history_verification_cannot_succeed_beyond_request_budget(sandbox):
    from tasks.daily_ohlcv_scheduler import process_ticker

    rows = daily_series(110)
    stored = [row for index, row in enumerate(rows) if index != 5]
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", stored)
    with (
        FakeTransport([response(daily_wire(rows[10:][::-1]))]) as transport,
        pytest.raises(RuntimeError, match="verification incomplete"),
    ):
        await process_ticker("A", last_date=rows[-1][1], target_api_calls=1)
    assert len(transport.calls) == 1
    assert sandbox.rows("daily_ohlcv") == stored


async def test_daily_new_candle_keeps_history_audit_within_five_pages(sandbox):
    from tasks.daily_ohlcv_scheduler import process_ticker

    rows = daily_series(501)
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", rows[:-1])
    pages = [rows[end - 100 : end][::-1] for end in range(501, 1, -100)]
    with FakeTransport([response(daily_wire(page)) for page in pages]) as transport:
        assert await process_ticker("A", last_date=rows[-2][1])
    assert len(transport.calls) == 5
    assert sandbox.rows("daily_ohlcv") == rows
    assert sandbox.rows("daily_ma") == ma_reference(rows, retention=301)
