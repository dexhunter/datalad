"""Baseline for datalad.local.addurls.Formatter.format.

addurls formats one URL template and one filename template per input row.
string.Formatter reparses that template on every call.
"""
from __future__ import annotations

import json
import statistics
import time

from datalad.local.addurls import Formatter

N = 40000
TEMPLATE = (
    "{subject}/ses-{session}/func/{subject}_ses-{session}"
    "_task-{task}_run-{run}_{suffix}.nii.gz"
)
ROWS = [
    {
        "subject": f"sub-{i:05d}",
        "session": "01",
        "task": "rest",
        "run": "01",
        "suffix": "bold",
    }
    for i in range(N)
]
RUNS = 5


def once(fmt: Formatter) -> int:
    acc = 0
    for row in ROWS:
        text = fmt.format(TEMPLATE, row)
        acc = (acc + len(text) + ord(text[-1])) & 0xFFFFFFFF
    return acc


def main() -> None:
    fmt = Formatter({})
    expected = once(fmt)
    # A BIDS filename for the first row. Guards against a bench that stops
    # calling the real formatter.
    first = fmt.format(TEMPLATE, ROWS[0])
    if not first.startswith("sub-00000/ses-01/func/sub-00000_ses-01_task-rest"):
        raise SystemExit(f"unexpected format result: {first}")
    samples = []
    for _ in range(RUNS):
        start = time.perf_counter()
        got = once(fmt)
        samples.append((time.perf_counter() - start) * 1000.0)
        if got != expected:
            raise SystemExit("formatter result changed between runs")
    median = statistics.median(samples)
    noise = (max(samples) - min(samples)) / median * 100.0
    print(json.dumps({
        "median_ms": median,
        "noise_pct": noise,
        "samples_ms": samples,
    }))


if __name__ == "__main__":
    main()
