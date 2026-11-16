"""Bisect a performance regression to one commit, then prove it causally
by reverse-applying that commit and measuring again.
"""

from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path

from .measure import MeasureError, _git, measure_source, release_worktree, source_at


def commits_between(repo: str, good: str, bad: str) -> list[str]:
    """First-parent commits after `good` up to and including `bad`, oldest first."""
    out = _git(repo, "rev-list", "--first-parent", "--reverse", f"{bad}", f"^{good}")
    return [line for line in out.splitlines() if line]


def is_merge(repo: str, rev: str) -> bool:
    return len(_git(repo, "rev-list", "--parents", "-n", "1", rev).split()) > 2


class _Trees:
    """Temp worktrees for one bisect session; every tree is removed on exit."""

    def __init__(self, repo: str):
        self.repo = str(repo)
        self.root = Path(tempfile.mkdtemp(prefix="tagperf-bisect-"))
        self.cache = {}
        self.trees = []

    def src(self, rev: str) -> str:
        if rev not in self.cache:
            tree = self.root / rev
            self.cache[rev] = str(source_at(self.repo, rev, tree))
            self.trees.append(tree)
        return self.cache[rev]

    def close(self):
        for tree in self.trees:
            release_worktree(self.repo, tree)
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def bisect(repo: str, good: str, bad: str, workload: str, iters: int, repeats: int,
           threshold_ratio: float, max_steps: int = 12) -> dict:
    """Binary search for the first commit whose cost crosses the midpoint.

    The classifier is fixed up front from the two endpoint medians:
    a commit is "bad" when its median reaches the geometric midpoint between
    the good and bad release medians.  No measurement taken during the search
    can move the goalposts.
    """
    def attempt(reps: int) -> dict:
        with _Trees(repo) as trees:
            good_m = measure_source(workload, trees.src(good), iters, reps)
            bad_m = measure_source(workload, trees.src(bad), iters, reps)
            midpoint = math.sqrt(good_m["median_us"] * bad_m["median_us"])
            rising = bad_m["median_us"] > good_m["median_us"]
            revs = commits_between(repo, good, bad)
            if not revs:
                raise MeasureError(f"no commits between {good} and {bad}")

            def value(rev: str) -> float:
                return measure_source(workload, trees.src(rev), iters, reps)["median_us"]

            def crossed(m: float) -> bool:
                return m >= midpoint if rising else m <= midpoint

            lo, hi = -1, len(revs) - 1
            steps = []
            while hi - lo > 1 and len(steps) < max_steps:
                mid = (lo + hi) // 2
                m = value(revs[mid])
                is_bad = crossed(m)
                steps.append({"commit": revs[mid], "median_us": m,
                              "class": "bad" if is_bad else "good",
                              "ratio_vs_good": m / good_m["median_us"]})
                if is_bad:
                    hi = mid
                else:
                    lo = mid

            culprit = revs[hi]
            before = revs[hi - 1] if hi > 0 else good
            previous_us = good_m["median_us"] if before == good else value(before)
            culprit_us = value(culprit)
            return {
                "good_tag": good, "bad_tag": bad,
                "good_median_us": good_m["median_us"], "bad_median_us": bad_m["median_us"],
                "midpoint_us": midpoint, "commits_in_range": len(revs),
                "steps": steps, "builds": len(steps),
                "culprit": culprit,
                "culprit_subject": _git(repo, "log", "-1", "--format=%s", culprit),
                "culprit_date": _git(repo, "log", "-1", "--format=%cI", culprit),
                "previous_commit": before, "previous_median_us": previous_us,
                "culprit_median_us": culprit_us,
                "culprit_is_merge": is_merge(repo, culprit),
                "direction": "slowdown" if rising else "speedup",
                "previous_is_good": not crossed(previous_us),
                "culprit_is_bad": crossed(culprit_us),
                "threshold_ratio": threshold_ratio,
            }

    def verified(r: dict) -> bool:
        return r["previous_is_good"] and r["culprit_is_bad"]

    result = attempt(repeats)
    attempts = [{"repeats": repeats, "verified": verified(result), "culprit": result["culprit"]}]
    if not verified(result):
        # The result failed its own verification: re-measure every step with a
        # doubled repeat budget before reporting anything.
        result = attempt(repeats * 2)
        attempts.append({"repeats": repeats * 2, "verified": verified(result),
                         "culprit": result["culprit"]})
    result["attempts"] = attempts
    return result


def revert_check(repo: str, commit: str, workload: str, iters: int, repeats: int,
                 baseline_us: float, tolerance: float = 0.02) -> dict:
    """Reverse-apply `commit` on top of itself and re-measure.

    If the commit caused the regression, removing it must land back within
    `tolerance` of the pre-regression baseline.
    """
    tmp = Path(tempfile.mkdtemp(prefix="tagperf-revert-"))
    tree = tmp / "tree"
    try:
        src = source_at(repo, commit, tree)
        if is_merge(repo, commit):
            return {"commit": commit, "ok": False, "reason": "merge commit: reverse diff is ambiguous"}
        diff = _git(repo, "diff", f"{commit}^1", commit)
        patch = tmp / "culprit.patch"
        patch.write_text(diff + "\n")
        _git(tree, "apply", "-R", str(patch))
        after = measure_source(workload, src, iters, repeats)
        ratio = after["median_us"] / baseline_us
        return {
            "commit": commit, "baseline_us": baseline_us,
            "reverted_us": after["median_us"], "ratio_vs_baseline": ratio,
            "tolerance": tolerance, "ok": abs(ratio - 1.0) <= tolerance,
            "patch_lines": len(diff.splitlines()), "samples_us": after["samples_us"],
        }
    finally:
        release_worktree(repo, tree)
        shutil.rmtree(tmp, ignore_errors=True)