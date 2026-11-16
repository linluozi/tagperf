"""Execute one workload against one source tree and report per-operation timings."""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import time


def load_workload(path):
    spec = importlib.util.spec_from_file_location("tagperf_workload", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv):
    workload_path, src, iters = argv[0], argv[1], int(argv[2])
    sys.path.insert(0, src)
    module = load_workload(workload_path)
    if hasattr(module, "setup"):
        once = module.setup()
    else:
        raise SystemExit("workload must define setup() returning a zero-argument callable")
    for _ in range(getattr(module, "WARMUP", 3)):
        once()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        once()
        samples.append((time.perf_counter() - t0) * 1e6)
    print(json.dumps({
        "per_op_us_median": statistics.median(samples),
        "per_op_us_min": min(samples),
        "iters": iters,
        "workload": getattr(module, "NAME", workload_path),
    }))


if __name__ == "__main__":
    main(sys.argv[1:])
