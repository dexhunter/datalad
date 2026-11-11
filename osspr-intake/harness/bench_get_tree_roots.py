"""Baseline for datalad.interface.utils.get_tree_roots.

save() hands this the paths of datasets that contain changes. When those
paths are sibling subdatasets (the superdataset root is not in the list),
none is a parent of another, and the current scan is quadratic.
"""
from __future__ import annotations

import json
import statistics
import time

from datalad.interface.utils import get_tree_roots

N = 6000
PATHS = [f"/data/study/sub-{i:05d}/ses-01" for i in range(N)]
RUNS = 5


def check(result: dict) -> None:
    if len(result) != N or set(result) != set(PATHS):
        raise SystemExit(f"unexpected roots: {len(result)}")
    if any(result[p] for p in PATHS):
        raise SystemExit("sibling datasets should not collect children")


def once() -> None:
    check(get_tree_roots(PATHS))


def main() -> None:
    once()
    samples = []
    for _ in range(RUNS):
        start = time.perf_counter()
        once()
        samples.append((time.perf_counter() - start) * 1000.0)
    median = statistics.median(samples)
    noise = (max(samples) - min(samples)) / median * 100.0
    print(json.dumps({
        "median_ms": median,
        "noise_pct": noise,
        "samples_ms": samples,
    }))


if __name__ == "__main__":
    main()
