#!/usr/bin/env python3
"""Frozen baselines for osspr-intake targets on upstream datalad maint.

Each target times one function on a fixed in-memory workload. Setup is
outside the clock. Garbage collection is disabled while sampling.
baseline_noise_pct is the coefficient of variation: pstdev / median * 100.

Run from the repository root:

    python3 osspr-intake/harness/bench_targets.py <target>

Prints one JSON object. <target> is the ``function`` value from INTAKE.json.
"""

from __future__ import annotations

import gc
import json
import os
import re
import statistics
import sys
import tempfile
import time

os.environ.setdefault("DATALAD_LOG_LEVEL", "error")

WARMUP = 3
REPEATS = 15
N_FILES = 8000


def _sample(fn):
    for _ in range(WARMUP):
        fn()
    gc.collect()
    gc.disable()
    samples = []
    try:
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000.0)
    finally:
        gc.enable()
    samples.sort()
    median = statistics.median(samples)
    noise = (statistics.pstdev(samples) / median * 100.0) if median else 0.0
    return {
        "baseline_median_ms": round(median, 3),
        "baseline_noise_pct": round(noise, 2),
        "samples_ms": [round(s, 3) for s in samples],
        "warmup": WARMUP,
        "repeats": REPEATS,
    }


def _ls_files_stage_line(i: int) -> str:
    return (
        "100644 e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 0\t"
        f"d{i // 100}/s{i // 10}/f{i}.txt"
    )


def bench_get_content_info_line_helper():
    """GitRepo._get_content_info_line_helper on 8000 ls-files --stage lines.

    Same regex and record shape as get_content_info() for a work tree.
    Matched lines carry a type, so the helper does not stat the filesystem.
    """
    from datalad.support.gitrepo import GitRepo

    td = tempfile.mkdtemp(prefix="osspr-intake-")
    # GitRepo() only needs a repo root for path joins; no commits required.
    repo = GitRepo(td, create=True)
    props_re = re.compile(
        r"(?P<type>[0-9]+) (?P<sha>[^ ]*) ([^\t]*)\t(?P<fname>.*)$"
    )
    lines = [_ls_files_stage_line(i) for i in range(N_FILES)]
    lines.append("")

    def run():
        info: dict = {}
        repo._get_content_info_line_helper(None, info, lines, props_re)
        return len(info)

    out = _sample(run)
    out["check_n"] = run()
    if out["check_n"] != N_FILES:
        raise SystemExit(f"content helper returned {out['check_n']} records")
    return out


def bench_line_splitter_process():
    """LineSplitter.process(separator=None) on chunked NUL-separated output.

    call_git() splits with separator=None, then get_content_info() splits
    the joined text on NUL. git ls-files -z has no newlines, so each chunk
    is one unterminated line and the splitter rescans the accumulated buffer.
    """
    from datalad.runner.utils import LineSplitter

    raw = "\0".join(_ls_files_stage_line(i) for i in range(N_FILES)) + "\0"
    chunks = [raw[i : i + 4096] for i in range(0, len(raw), 4096)]

    def run():
        splitter = LineSplitter(separator=None)
        n = 0
        for chunk in chunks:
            n += len(splitter.process(chunk))
        splitter.finish_processing()
        return n

    out = _sample(run)
    out["check_n"] = run()
    out["n_chunks"] = len(chunks)
    out["nbytes"] = len(raw)
    return out


def bench_get_filtered_paths():
    """get_filtered_paths_ over 8000 repo-relative paths and 20 directory filters."""
    from datalad.support.path import get_filtered_paths_

    paths = [f"d{i // 100}/s{i // 10}/f{i}.txt" for i in range(N_FILES)]
    filters = [f"d{i}" for i in range(0, 80, 4)]

    def run():
        return sum(
            1
            for _ in get_filtered_paths_(
                paths, filters, include_within_path=True
            )
        )

    out = _sample(run)
    out["check_n"] = run()
    if out["check_n"] <= 0:
        raise SystemExit("get_filtered_paths_ yielded nothing")
    return out


def bench_split_ext():
    """split_ext on 20000 filenames, the git-annex short-extension rule."""
    from datalad.support.path import split_ext

    names = []
    for i in range(20000):
        if i % 3 == 0:
            names.append(f"file{i}.tar.gz")
        elif i % 3 == 1:
            names.append(f"file{i}.nii.gz")
        else:
            names.append(f"file{i}.txt")

    def run():
        n = 0
        for name in names:
            root, ext = split_ext(name)
            n += len(ext)
        return n

    out = _sample(run)
    out["check_n"] = run()
    if out["check_n"] <= 0:
        raise SystemExit("split_ext produced no extensions")
    return out


def bench_proc_json_record():
    """AnnexJsonProtocol._proc_json_record on 8000 non-progress find records.

    This is the per-record path of ``git annex find --json`` (no total bar).
    """
    from datalad.support.annexrepo import AnnexJsonProtocol

    records = [
        {
            "command": "find",
            "file": f"d{i // 100}/s{i // 10}/f{i}.txt",
            "key": f"MD5-s{1000 + i}--{i:032x}",
            "bytesize": str(1000 + i),
            "success": True,
        }
        for i in range(N_FILES)
    ]
    proto = AnnexJsonProtocol()
    proto._init_total_pbar_state()

    def run():
        proto.json_out = []
        for rec in records:
            proto._proc_json_record(rec)
        return len(proto.json_out)

    out = _sample(run)
    out["check_n"] = run()
    if out["check_n"] != N_FILES:
        raise SystemExit(f"_proc_json_record kept {out['check_n']} records")
    return out


def bench_parse_gitconfig_dump():
    """parse_gitconfig_dump on a 4000-key ``git config -z --list --show-origin`` dump."""
    from datalad.config import parse_gitconfig_dump

    parts = [
        f"file:.git/config\0section{i % 50}.key{i}=value-{i}-{'x' * 40}"
        for i in range(4000)
    ]
    dump = "\0".join(parts) + "\0"

    def run():
        parsed, files = parse_gitconfig_dump(
            dump, cwd="/tmp/osspr-intake-cfg", multi_value=True
        )
        return len(parsed), len(files)

    out = _sample(run)
    n_keys, n_files = run()
    out["check_n"] = n_keys
    if n_keys != 4000 or n_files != 1:
        raise SystemExit(f"parse_gitconfig_dump -> keys={n_keys} files={n_files}")
    return out


TARGETS = {
    "_get_content_info_line_helper": bench_get_content_info_line_helper,
    "LineSplitter.process": bench_line_splitter_process,
    "get_filtered_paths_": bench_get_filtered_paths,
    "split_ext": bench_split_ext,
    "_proc_json_record": bench_proc_json_record,
    "parse_gitconfig_dump": bench_parse_gitconfig_dump,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TARGETS:
        names = ", ".join(TARGETS)
        print(f"usage: bench_targets.py <{'|'.join(TARGETS)}>", file=sys.stderr)
        print(f"known: {names}", file=sys.stderr)
        return 2
    name = argv[1]
    result = TARGETS[name]()
    result["function"] = name
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
