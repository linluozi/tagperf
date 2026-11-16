import statistics

from tagperf.analyze import bootstrap_ratio_ci, find_changepoints, summarize


def arm(median, spread=0.01, n=7):
    samples = [median * (1 + spread * (i - n // 2) / n) for i in range(n)]
    return {"median_us": statistics.median(samples), "samples_us": samples,
            "p25_us": min(samples), "p75_us": max(samples), "rsd": 0.01}


def test_changepoint_detects_18_percent_jump():
    traj = {"v1": arm(100), "v2": arm(102), "v3": arm(121), "v4": arm(120)}
    order = ["v1", "v2", "v3", "v4"]
    cps = find_changepoints(traj, order, min_ratio=1.10)
    assert [(c["from"], c["to"]) for c in cps] == [("v2", "v3")]
    assert 1.17 < cps[0]["ratio"] < 1.20
    lo, hi = cps[0]["ci95"]
    assert lo <= cps[0]["ratio"] <= hi


def test_flat_trajectory_and_noise_do_not_flag():
    traj = {"v1": arm(100, 0.05), "v2": arm(104, 0.05), "v3": arm(99, 0.05)}
    assert find_changepoints(traj, ["v1", "v2", "v3"], min_ratio=1.10) == []


def test_bootstrap_is_deterministic():
    a, b = arm(100, 0.02), arm(130, 0.02)
    first = bootstrap_ratio_ci(a, b, n=500, seed=7)
    second = bootstrap_ratio_ci(a, b, n=500, seed=7)
    assert first == second
    assert first[0] <= 1.30 <= first[1]


def test_summary_reports_extremes():
    traj = {"v1": arm(100), "v2": arm(150), "v3": arm(80)}
    s = summarize(traj, ["v1", "v2", "v3"])
    assert s["min"] == "v3" and s["max"] == "v2" and s["tag_count"] == 3