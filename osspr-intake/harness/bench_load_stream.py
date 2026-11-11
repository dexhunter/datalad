"""Baseline for datalad.support.json_py.load_stream.

git-annex --json and DataLad metadata exports are JSONL. load_stream wraps
every line in a codecs reader and json.loads helper.
"""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time

from datalad.support.json_py import load_stream

N = 50000
RUNS = 5


def write_jsonl(path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for i in range(N):
            record = {
                "command": "get",
                "file": f"sub-{i:05d}/anat/sub-{i:05d}_T1w.nii.gz",
                "key": "SHA256E-s123--" + ("ab" * 32),
                "success": True,
            }
            handle.write(json.dumps(record))
            handle.write("\n")


def once(path: str) -> int:
    count = 0
    acc = 0
    for record in load_stream(path):
        count += 1
        acc = (acc + len(record["file"])) & 0xFFFFFFFF
    if count != N:
        raise SystemExit(f"expected {N} records, got {count}")
    return acc


def main() -> None:
    fd, path = tempfile.mkstemp(prefix="osspr-load-stream-", suffix=".jsonl")
    os.close(fd)
    try:
        write_jsonl(path)
        expected = once(path)
        samples = []
        for _ in range(RUNS):
            start = time.perf_counter()
            got = once(path)
            samples.append((time.perf_counter() - start) * 1000.0)
            if got != expected:
                raise SystemExit("load_stream result changed between runs")
        median = statistics.median(samples)
        noise = (max(samples) - min(samples)) / median * 100.0
        print(json.dumps({
            "median_ms": median,
            "noise_pct": noise,
            "samples_ms": samples,
        }))
    finally:
        os.unlink(path)


if __name__ == "__main__":
    main()
