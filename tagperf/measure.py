"""Process-isolated measurement: one subprocess per repeat, median of repeats.

Every repeat is a fresh interpreter, so import caches, GC state and allocator
history never leak between samples.  The reported value is the median of the
per-run medians, never the single fastest run.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

PKG_ROOT = str(Path(__file__).resolve().parent.parent)


class MeasureError(RuntimeError):
    pass


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = PKG_ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def run_worker(workload: str, src: str, iters: int, timeout: int = 600) -> dict:
    cmd = [sys.executable, "-m", "tagperf._worker", str(workload), str(src), str(iters)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env())
    if proc.returncode != 0:
        raise MeasureError(f"worker failed ({proc.returncode}): {proc.stderr.strip()[-800:]}")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise MeasureError(f"bad worker output: {proc.stdout[-400:]!r}") from exc


def _quantile(values, q):
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def measure_source(workload: str, src: str, iters: int, repeats: int = 5) -> dict:
    """Run `repeats` independent processes over the same source tree."""
    runs = [run_worker(workload, src, iters) for _ in range(repeats)]
    samples = [r["per_op_us_median"] for r in runs]
    med = statistics.median(samples)
    sd = statistics.stdev(samples) if len(samples) > 1 else 0.0
    return {
        "src": str(src),
        "workload": str(workload),
        "iters": iters,
        "repeats": repeats,
        "samples_us": samples,
        "median_us": med,
        "p25_us": _quantile(samples, 0.25),
        "p75_us": _quantile(samples, 0.75),
        "rsd": (sd / med) if med else None,
        "raw_runs": runs,
    }


def null_control(workload: str, src: str, iters: int, pairs: int = 4) -> dict:
    """A/A control: two arms over the *same* tree, alternating, in one session.

    Reports the per-pair ratio B/A and the ratio of arm medians.  A value
    outside +/-2% means the environment is drifting and no verdict may be
    issued from measurements taken in that window.
    """
    arm_a, arm_b, pair_ratios = [], [], []
    for _ in range(pairs):
        a = run_worker(workload, src, iters)["per_op_us_median"]
        b = run_worker(workload, src, iters)["per_op_us_median"]
        arm_a.append(a)
        arm_b.append(b)
        pair_ratios.append(b / a)
    ratio = statistics.median(arm_b) / statistics.median(arm_a)
    return {
        "src": str(src),
        "workload": str(workload),
        "iters": iters,
        "pairs": pairs,
        "arm_a_us": arm_a,
        "arm_b_us": arm_b,
        "pair_ratios": pair_ratios,
        "ratio": ratio,
        "deviation": abs(ratio - 1.0),
        "stable": abs(ratio - 1.0) <= 0.02,
    }


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise MeasureError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def release_worktree(repo: str, workdir) -> None:
    """Unregister a worktree so `git worktree list` does not accumulate entries."""
    try:
        _git(repo, "worktree", "remove", "--force", str(workdir))
    except MeasureError:
        try:
            _git(repo, "worktree", "prune")
        except MeasureError:
            pass


def source_at(repo: str, rev: str, workdir: Path) -> Path:
    _git(repo, "worktree", "add", "--detach", str(workdir), rev)
    for candidate in ("src", "."):
        if (workdir / candidate).is_dir():
            return workdir / candidate
    return workdir


def collect(repo: str, tags: list[str], workload: str, iters: int, repeats: int) -> dict:
    """Measure every tag of `repo` in a throwaway worktree per tag."""
    tmp = Path(tempfile.mkdtemp(prefix="tagperf-"))
    out = {"repo": str(repo), "workload": str(workload), "iters": iters,
           "repeats": repeats, "tags": {}}
    try:
        for tag in tags:
            tree = tmp / tag
            src = source_at(repo, tag, tree)
            try:
                out["tags"][tag] = measure_source(workload, str(src), iters, repeats)
            finally:
                _git(repo, "worktree", "remove", "--force", str(tree))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out