#!/usr/bin/env python3
"""Unit tests for the pure numerical core of the study. No network.

Run: python -m pytest tests/ -q      (or: python tests/test_core.py)
These lock down the executable-price logic every finding depends on: order-book
VWAP walking, complete-field lock cost, expiry filtering, and Kalshi fees.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def _load(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


depth = _load("analyze_depth", "analyze_depth.py")
fwd = _load("collect_forward", "collect_forward.py")
loop = _load("analyze_loop", "analyze_loop.py")
hy = _load("hygiene", "hygiene.py")


# ---- hygiene: the single source of truth for data cleaning ----
def test_hygiene_to_float():
    assert hy.to_float("0.5") == 0.5
    assert hy.to_float(None) is None
    assert hy.to_float("") is None
    assert hy.to_float("abc") is None

def test_hygiene_clean_price_valid_range():
    assert hy.clean_price(0.5) == 0.5
    assert hy.clean_price(0.001) == 0.001
    assert hy.clean_price(0.999) == 0.999

def test_hygiene_clean_price_rejects_degenerate():
    assert hy.clean_price(0.0) is None      # resolved/placeholder
    assert hy.clean_price(1.0) is None      # resolved
    assert hy.clean_price(-0.1) is None     # corrupt
    assert hy.clean_price(1.5) is None      # corrupt
    assert hy.clean_price(None) is None
    assert hy.clean_price(float("nan")) is None

def test_hygiene_is_zombie_by_id():
    assert hy.is_zombie({"id": "831375"}) is True   # known Ethiopia zombie
    assert hy.is_zombie({"id": "999999", "endDate": "2099-01-01T00:00:00Z"}) is False

def test_hygiene_is_zombie_by_expiry():
    assert hy.is_zombie({"id": "x", "endDate": "2020-01-01T00:00:00Z"}) is True
    assert hy.is_zombie({"id": "x"}) is False  # no date -> keep

def test_hygiene_live_negrisk_filters_all():
    events = [
        {"id": "1", "negRisk": True,  "markets": [1, 2, 3], "endDate": "2099-01-01T00:00:00Z"},  # keep
        {"id": "2", "negRisk": False, "markets": [1, 2, 3]},                                       # not negRisk
        {"id": "3", "negRisk": True,  "markets": [1]},                                             # too small
        {"id": "831375", "negRisk": True, "markets": [1, 2, 3, 4]},                                # zombie id
        {"id": "5", "negRisk": True,  "markets": [1, 2, 3], "endDate": "2000-01-01T00:00:00Z"},   # expired
    ]
    kept = hy.live_negrisk_events(events, min_outcomes=3)
    assert [e["id"] for e in kept] == ["1"]


# ---- vwap_buy: walk the ask side cheapest-first ----
def test_vwap_single_level():
    avg, filled = depth.vwap_buy([(0.50, 100)], 10)
    assert filled == 10 and abs(avg - 0.50) < 1e-9

def test_vwap_walks_multiple_levels():
    # buy 150: 100@0.40 then 50@0.60 -> (40 + 30)/150
    avg, filled = depth.vwap_buy([(0.40, 100), (0.60, 100)], 150)
    assert filled == 150 and abs(avg - (70.0 / 150)) < 1e-9

def test_vwap_cheapest_first_regardless_of_order():
    avg, filled = depth.vwap_buy([(0.90, 100), (0.10, 100)], 100)
    assert filled == 100 and abs(avg - 0.10) < 1e-9  # took the cheap level

def test_vwap_partial_fill_reports_shortfall():
    avg, filled = depth.vwap_buy([(0.50, 30)], 100)
    assert filled == 30 and abs(avg - 0.50) < 1e-9  # thin book, under-fills


# ---- field_cost: a lock needs EVERY declared outcome ----
def test_field_cost_complete_when_all_legs_fill():
    ev = {"asks": [[(0.50, 10)], [(0.55, 10)]], "n_markets": 2}
    cost, filled, fsize, complete = depth.field_cost(ev, 5)
    assert complete is True and filled == 2 and abs(cost - 1.05) < 1e-9

def test_field_cost_incomplete_when_a_declared_leg_missing():
    # 3 declared outcomes but only 2 have books -> cannot lock
    ev = {"asks": [[(0.40, 10)], [(0.30, 10)]], "n_markets": 3}
    cost, filled, fsize, complete = depth.field_cost(ev, 5)
    assert complete is False and filled == 2 and fsize == 3

def test_field_cost_incomplete_when_book_too_thin():
    ev = {"asks": [[(0.50, 3)], [(0.55, 10)]], "n_markets": 2}
    cost, filled, fsize, complete = depth.field_cost(ev, 5)
    assert complete is False  # first leg can't fill 5 shares


# ---- is_expired: reject zombie markets ----
def test_is_expired_past_date():
    assert hy.is_expired("2020-01-01T00:00:00Z") is True

def test_is_expired_future_date():
    assert hy.is_expired("2099-01-01T00:00:00Z") is False

def test_is_expired_missing_or_garbage_kept():
    assert hy.is_expired(None) is False
    assert hy.is_expired("not-a-date") is False


# ---- kalshi_fee: round_up(0.07 * p*(1-p)) ----
def test_kalshi_fee_at_half_is_max():
    # 0.07 * 0.25 = 0.0175 -> ceil to cents = 0.02
    assert abs(loop.kalshi_fee(0.50) - 0.02) < 1e-9

def test_kalshi_fee_at_extremes_small():
    assert loop.kalshi_fee(0.01) <= 0.01
    assert loop.kalshi_fee(0.99) <= 0.01

def test_kalshi_fee_none_is_zero():
    assert loop.kalshi_fee(None) == 0.0


# ---- loop_edge: cross-venue arbitrage after fees ----
def test_loop_edge_none_when_missing_quote():
    eg, en, dr = loop.loop_edge(None, 0.5, 0.5, 0.6)
    assert eg is None and en is None and dr is None

def test_loop_edge_no_arbitrage_when_quotes_agree():
    # both venues 0.50/0.51 -> no gap, fees make net negative
    eg, en, dr = loop.loop_edge(0.50, 0.51, 0.50, 0.51)
    assert en < 0

def test_loop_edge_gross_positive_but_fee_kills_it():
    # buy Kalshi ask 0.66, sell Polymarket bid 0.67 -> gross +0.01, fee ~0.02 -> net<0
    eg, en, dr = loop.loop_edge(0.67, 0.68, 0.65, 0.66)
    assert eg > 0 and en < 0

def test_loop_edge_direction_reported():
    eg, en, dr = loop.loop_edge(0.90, 0.91, 0.10, 0.11)
    # Polymarket dear, Kalshi cheap -> buy Kalshi, sell Polymarket
    assert dr == "buy_kalshi_sell_poly" and en > 0


# --- window_stats: the two claims that were wrong in the prose -------------
#
# Both defects were in the WRITEUP, not the math, and both traced to the summary
# under-reporting: only one sub-$1 field title was kept, and the longest run was
# tracked with no record of what it actually paid. A reader then sees "31.2h"
# beside "2.7%" and concludes the deep edge lasted a day and a half.

site = _load("generate_site_data", "generate_site_data.py")


def _rec(ts, event_id, title, cost, end_date="2026-11-03T00:00:00Z"):
    return {"ts": ts, "event_id": event_id, "title": title, "n_markets": 5,
            "complete": True, "lock_cost": cost, "size": 100, "fill_ratio": 1.0,
            "filled_legs": 5, "end_date": end_date}


def test_window_stats_keeps_every_sub_dollar_field():
    """397 sub-$1 observations spanned TWO fields; reporting one is the bug."""
    rows = [
        _rec("2026-08-21T00:00:00Z", "a", "Balance of Power: 2026 Midterms", 0.97),
        _rec("2026-08-21T00:00:00Z", "b", "Fed Decision in September?", 0.99,
             "2026-09-16T00:00:00Z"),
    ]
    ws = site.window_stats(rows)
    assert ws["sub_dollar_titles"] == {
        "Balance of Power: 2026 Midterms", "Fed Decision in September?"}, ws["sub_dollar_titles"]
    assert ws["ever_exec"] == 2, ws["ever_exec"]


def test_longest_run_reports_the_edge_it_actually_paid():
    """The longest run and the deepest print can be different episodes.

    Long run of 3 shallow snapshots (best 0.994 = 0.6% gross), then a break,
    then a single deep snapshot (0.973 = 2.7%). The summary must not let the
    2.7% be read as lasting the length of the 3-snapshot run.
    """
    rows = [_rec("2026-08-21T0%d:00:00Z" % i, "a", "F", c)
            for i, c in enumerate([0.994, 0.996, 0.995])]
    rows.append(_rec("2026-08-22T00:00:00Z", "a", "F", 1.01))   # breaks the run
    rows.append(_rec("2026-08-23T00:00:00Z", "a", "F", 0.973))  # deep, short
    ws = site.window_stats(rows)

    assert ws["best_run_snaps"] == 3, ws["best_run_snaps"]
    assert abs(ws["best_run_snaps_cost"] - 0.994) < 1e-9, ws["best_run_snaps_cost"]
    assert abs(ws["best_lock_cost"] - 0.973) < 1e-9, ws["best_lock_cost"]
    # the whole point: what the long run paid is WORSE than the deepest print
    assert ws["best_run_snaps_cost"] > ws["best_lock_cost"]


def test_run_length_resets_on_a_break():
    """A run is consecutive; two short runs must not add up to a long one."""
    rows = [_rec("2026-08-21T00:00:00Z", "a", "F", 0.98),
            _rec("2026-08-21T01:00:00Z", "a", "F", 1.02),
            _rec("2026-08-21T02:00:00Z", "a", "F", 0.98)]
    ws = site.window_stats(rows)
    assert ws["best_run_snaps"] == 1, ws["best_run_snaps"]


def test_committed_panel_still_has_two_sub_dollar_fields():
    """Regression against the real data the findings are written from."""
    path = os.path.join(ROOT, "data", "panel.jsonl")
    if not os.path.exists(path):
        return
    import json
    rows = [json.loads(l) for l in open(path) if l.strip()]
    ws = site.window_stats(rows)
    assert len(ws["sub_dollar_titles"]) == 2, sorted(ws["sub_dollar_titles"])
    assert ws["sub_dollar_obs"] == 397, ws["sub_dollar_obs"]
    # 31.2h run pays 0.6%, the 0.973 print is elsewhere
    assert abs(ws["best_run_snaps_cost"] - 0.994) < 1e-6, ws["best_run_snaps_cost"]
    assert abs(ws["best_lock_cost"] - 0.973) < 1e-6, ws["best_lock_cost"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
