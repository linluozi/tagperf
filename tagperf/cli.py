"""Command line entry point for tagperf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import find_changepoints, summarize
from .bisect import bisect, revert_check
from .measure import collect, null_control

__version__ = "0.1.0"


def _dump(obj, out):
    text = json.dumps(obj, indent=2, sort_keys=False)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n")
        print(f"wrote {out}")
    else:
        print(text)


def main(argv=None):
    p = argparse.ArgumentParser(prog="tagperf", description=__doc__)
    p.add_argument("--version", action="version", version=f"tagperf {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="measure a release trajectory")
    r.add_argument("--repo", required=True)
    r.add_argument("--workload", required=True)
    r.add_argument("--tags", required=True, help="comma separated, oldest first")
    r.add_argument("--iters", type=int, default=100)
    r.add_argument("--repeats", type=int, default=5)
    r.add_argument("--out")

    a = sub.add_parser("analyze", help="find changepoints in a trajectory")
    a.add_argument("--input", required=True)
    a.add_argument("--order", help="comma separated tag order; defaults to insertion order")
    a.add_argument("--min-ratio", type=float, default=1.10)
    a.add_argument("--out")

    c = sub.add_parser("control", help="A/A null control on one tree")
    c.add_argument("--repo", required=True)
    c.add_argument("--tag", required=True)
    c.add_argument("--workload", required=True)
    c.add_argument("--iters", type=int, default=100)
    c.add_argument("--pairs", type=int, default=4)
    c.add_argument("--out")

    b = sub.add_parser("bisect", help="bisect a regression between two tags")
    b.add_argument("--repo", required=True)
    b.add_argument("--good", required=True)
    b.add_argument("--bad", required=True)
    b.add_argument("--workload", required=True)
    b.add_argument("--iters", type=int, default=100)
    b.add_argument("--repeats", type=int, default=5)
    b.add_argument("--threshold-ratio", type=float, default=1.10)
    b.add_argument("--out")

    v = sub.add_parser("revert", help="reverse-apply a culprit commit and re-measure")
    v.add_argument("--repo", required=True)
    v.add_argument("--commit", required=True)
    v.add_argument("--workload", required=True)
    v.add_argument("--iters", type=int, default=100)
    v.add_argument("--repeats", type=int, default=5)
    v.add_argument("--baseline-us", type=float, required=True)
    v.add_argument("--tolerance", type=float, default=0.02)
    v.add_argument("--out")

    args = p.parse_args(argv)

    if args.command == "run":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        _dump(collect(args.repo, tags, args.workload, args.iters, args.repeats), args.out)
    elif args.command == "analyze":
        data = json.loads(Path(args.input).read_text())
        tags = data["tags"]
        order = ([t.strip() for t in args.order.split(",") if t.strip()]
                 if args.order else list(tags))
        cps = find_changepoints(tags, order, min_ratio=args.min_ratio)
        _dump({"input": args.input, "order": order, "min_ratio": args.min_ratio,
               "summary": summarize(tags, order), "changepoints": cps}, args.out)
    elif args.command == "control":
        from .measure import source_at
        import tempfile
        with tempfile.TemporaryDirectory(prefix="tagperf-aa-") as tmp:
            src = source_at(args.repo, args.tag, Path(tmp) / "tree")
            _dump(null_control(args.workload, str(src), args.iters, args.pairs), args.out)
    elif args.command == "bisect":
        _dump(bisect(args.repo, args.good, args.bad, args.workload, args.iters,
                     args.repeats, args.threshold_ratio), args.out)
    elif args.command == "revert":
        _dump(revert_check(args.repo, args.commit, args.workload, args.iters,
                           args.repeats, args.baseline_us, args.tolerance), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())