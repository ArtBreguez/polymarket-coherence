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
    assert fwd.is_expired("2020-01-01T00:00:00Z") is True

def test_is_expired_future_date():
    assert fwd.is_expired("2099-01-01T00:00:00Z") is False

def test_is_expired_missing_or_garbage_kept():
    assert fwd.is_expired(None) is False
    assert fwd.is_expired("not-a-date") is False


# ---- kalshi_fee: round_up(0.07 * p*(1-p)) ----
def test_kalshi_fee_at_half_is_max():
    # 0.07 * 0.25 = 0.0175 -> ceil to cents = 0.02
    assert abs(loop.kalshi_fee(0.50) - 0.02) < 1e-9

def test_kalshi_fee_at_extremes_small():
    assert loop.kalshi_fee(0.01) <= 0.01
    assert loop.kalshi_fee(0.99) <= 0.01

def test_kalshi_fee_none_is_zero():
    assert loop.kalshi_fee(None) == 0.0


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
