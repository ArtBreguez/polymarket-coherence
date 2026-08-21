#!/usr/bin/env python3
"""Single source of truth for data hygiene.

Every pull from an external venue (Polymarket Gamma, Polymarket CLOB, Kalshi)
routes through this module so the same integrity rules apply everywhere, instead
of being copy-pasted (and drifting) across collectors.

What it guarantees:
  * Zombie filtering — events whose endDate is in the past are dropped even when
    the venue still flags them closed=false (resolved/expired 'zombie' markets
    have degenerate prices and evaporating liquidity).
  * Known-bad exclusion — a curated ZOMBIE_EVENT_IDS set for events captured
    before the endDate filter existed.
  * Safe numeric parsing — never let a None/"" price crash a collector.
  * Price sanity — a probability quote must live in (0, 1); anything outside is
    rejected as corrupt, not silently averaged into a result.
  * Polite HTTP — retry with backoff + a real User-Agent (Gamma 403s otherwise).

Pure and dependency-free (stdlib only) so it is trivially unit-testable with no
network. Import it; do not reimplement these rules locally.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "polymarket-coherence/1.0"
HEADERS = {"Accept": "application/json", "User-Agent": UA}

# Events Polymarket kept flagged closed=false past their endDate, captured before
# the endDate filter landed. Excluded everywhere by event_id (stable), not title.
ZOMBIE_EVENT_IDS = {
    "831375",  # Next Prime Minister of Ethiopia? (endDate 2026-06-01)
    "411239",  # Elon Musk # tweets August 14 - August 21, 2026?
}


# --------------------------------------------------------------------------- #
# numeric hygiene
# --------------------------------------------------------------------------- #
def to_float(x):
    """Parse to float or return None. Never raises. Use for any external number."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def clean_price(x):
    """Return a probability price only if it is a real number in (0, 1).

    Prediction-market YES prices are probabilities: strictly between 0 and 1.
    A value of exactly 0 or 1, negative, >1, or NaN is degenerate/corrupt (a
    resolved leg, a placeholder, or a bad tick) and must NOT enter a coherence
    statistic. Returns None for anything that fails, so callers can skip it.
    """
    v = to_float(x)
    if v is None or v != v:  # None or NaN
        return None
    if v <= 0.0 or v >= 1.0:
        return None
    return v


# --------------------------------------------------------------------------- #
# event hygiene
# --------------------------------------------------------------------------- #
def is_expired(end_date, now=None):
    """True if end_date is in the past. Missing/garbage dates are kept (return
    False) since we cannot prove they are expired."""
    if not end_date:
        return False
    try:
        end = dt.datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return end < (now or dt.datetime.now(dt.timezone.utc))


def is_zombie(event, now=None):
    """True if a Polymarket event object should be dropped as a zombie:
    known-bad event_id OR an endDate already in the past."""
    eid = str(event.get("id") or event.get("event_id") or "")
    if eid in ZOMBIE_EVENT_IDS:
        return True
    return is_expired(event.get("endDate") or event.get("end_date"), now=now)


def live_negrisk_events(events, min_outcomes=3, now=None):
    """Filter a raw Gamma /events payload down to clean, live negRisk events.

    A single choke point every Polymarket pull passes through:
      * must be negRisk (mutually-exclusive by construction — the object of study)
      * must have >= min_outcomes child markets
      * must not be a zombie (expired / known-bad)
    Returns the surviving event objects, order preserved.
    """
    out = []
    for e in events or []:
        if not e.get("negRisk"):
            continue
        if len(e.get("markets", [])) < min_outcomes:
            continue
        if is_zombie(e, now=now):
            continue
        out.append(e)
    return out


# --------------------------------------------------------------------------- #
# polite HTTP
# --------------------------------------------------------------------------- #
def http_json(url, data=None, timeout=30, retries=4):
    """GET/POST JSON with backoff + User-Agent. data=dict -> POST JSON body.
    Raises after the final attempt; returns parsed JSON otherwise."""
    body = None
    headers = dict(HEADERS)
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 — transient; retry with backoff
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def gamma_events(limit=500, base="https://gamma-api.polymarket.com"):
    """Fetch open Gamma events, highest-volume first, through polite HTTP."""
    q = urllib.parse.urlencode({"closed": "false", "limit": limit,
                                "order": "volume", "ascending": "false"})
    return http_json(f"{base}/events?{q}") or []
