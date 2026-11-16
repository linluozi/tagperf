import json
import subprocess
import sys
from pathlib import Path

from tagperf.bisect import bisect, commits_between, revert_check

WORKLOAD = """\
import mod

NAME = "fixture"
WARMUP = 1

def setup():
    return lambda: mod.f(5000)
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def build_repo(tmp_path, mode="slowdown"):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    fast = "def f(n):\n    return sum(range(n))\n"
    slow = "def f(n):\n    return sum(range(n)) + len([str(i) for i in range(40000)])\n"
    (repo / "mod.py").write_text(slow if mode == "speedup" else fast)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    git(repo, "tag", "v1")
    for i in range(4):
        (repo / "notes.txt").write_text(str(i))
        git(repo, "add", "-A")
        git(repo, "commit", "-m", f"noise {i}")
    (repo / "mod.py").write_text(fast if mode == "speedup" else slow)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "PERF: change the hot loop")
    changed = git(repo, "rev-parse", "HEAD")
    for i in range(3):
        (repo / "notes.txt").write_text(f"tail {i}")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", f"tail {i}")
    git(repo, "tag", "v2")
    return repo, changed


def test_commits_between_is_oldest_first(tmp_path):
    repo, _ = build_repo(tmp_path)
    revs = commits_between(repo, "v1", "v2")
    assert len(revs) == 8
    assert revs[-1] == git(repo, "rev-parse", "v2")
    assert revs[0] == git(repo, "rev-list", "--reverse", "v2", "^v1").splitlines()[0]


def test_bisect_finds_single_culprit_and_revert_restores_baseline(tmp_path):
    repo, slow = build_repo(tmp_path, mode="slowdown")
    wl = tmp_path / "workload.py"
    wl.write_text(WORKLOAD)
    result = bisect(str(repo), "v1", "v2", str(wl), iters=200, repeats=3,
                    threshold_ratio=1.10, max_steps=8)
    assert result["culprit"] == slow
    assert result["previous_is_good"] and result["culprit_is_bad"]
    assert result["attempts"][-1]["verified"] is True
    assert result["builds"] <= 5
    rev = revert_check(str(repo), slow, str(wl), iters=200, repeats=3,
                       baseline_us=result["good_median_us"], tolerance=0.10)
    assert rev["ok"], json.dumps(rev, indent=2)
    assert rev["ratio_vs_baseline"] < 1.10

def test_bisect_localises_a_speedup(tmp_path):
    repo, fast = build_repo(tmp_path, mode="speedup")
    wl = tmp_path / "workload.py"
    wl.write_text(WORKLOAD)
    result = bisect(str(repo), "v1", "v2", str(wl), iters=200, repeats=3,
                    threshold_ratio=1.10, max_steps=8)
    assert result["direction"] == "speedup"
    assert result["culprit"] == fast
    assert result["attempts"][-1]["verified"] is True
