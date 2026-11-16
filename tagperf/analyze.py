"""Changepoint detection on a release trajectory, with bootstrap intervals."""

from __future__ import annotations

import random
import statistics


def median_ratio(a: dict, b: dict) -> float:
    return b["median_us"] / a["median_us"]


def bootstrap_ratio_ci(a: dict, b: dict, n: int = 4000, seed: int = 20261117,
                       level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap over the per-repeat samples of both arms."""
    rng = random.Random(seed)
    sa, sb = a["samples_us"], b["samples_us"]
    ratios = []
    for _ in range(n):
        ra = [rng.choice(sa) for _ in sa]
        rb = [rng.choice(sb) for _ in sb]
        ratios.append(statistics.median(rb) / statistics.median(ra))
    ratios.sort()
    lo = ratios[int((1 - level) / 2 * n)]
    hi = ratios[min(int((1 + level) / 2 * n), n - 1)]
    return lo, hi


def find_changepoints(trajectory: dict, order: list[str], min_ratio: float = 1.10,
                      direction: str = "up") -> list[dict]:
    """Return adjacent-release changes whose median ratio crosses `min_ratio`.

    `trajectory` maps tag -> measurement dict; `order` is the release order.
    The bootstrap interval is reported but not used as a veto: with 5-7
    repeats it is deliberately wide.  A/A control (measure.null_control) is
    the stability gate instead.
    """
    found = []
    for good, bad in zip(order, order[1:]):
        a, b = trajectory[good], trajectory[bad]
        ratio = median_ratio(a, b)
        flag = ratio >= min_ratio if direction == "up" else ratio <= 1 / min_ratio
        if not flag:
            continue
        lo, hi = bootstrap_ratio_ci(a, b)
        found.append({
            "from": good, "to": bad, "ratio": ratio,
            "ci95": [lo, hi],
            "from_median_us": a["median_us"], "to_median_us": b["median_us"],
            "direction": "up" if ratio > 1 else "down",
        })
    return found


def summarize(trajectory: dict, order: list[str]) -> dict:
    rows = []
    for tag in order:
        m = trajectory[tag]
        rows.append({"tag": tag, "median_us": m["median_us"], "p25_us": m["p25_us"],
                     "p75_us": m["p75_us"], "rsd": m["rsd"]})
    return {"tag_count": len(order), "rows": rows,
            "min": min(rows, key=lambda r: r["median_us"])["tag"],
            "max": max(rows, key=lambda r: r["median_us"])["tag"]}