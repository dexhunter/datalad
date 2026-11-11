"""Baseline allocations for datalad.utils.path_startswith.

GitRepo path normalization and dataset-tree walks call this once per path.
Each call copies both strings via with_pathsep before the prefix test.
Allocations are PyObject malloc/calloc/realloc calls while the function runs.
"""
from __future__ import annotations

import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile

from datalad.utils import path_startswith

HERE = os.path.dirname(os.path.abspath(__file__))
N = 100000
PAIRS = [
    (f"/repo/ds/sub-{i % 4000:04d}/file_{i}.nii.gz", f"/repo/ds/sub-{i % 4000:04d}")
    for i in range(N)
]
RUNS = 5


class _PyMemAllocatorEx(ctypes.Structure):
    _fields_ = [
        ("ctx", ctypes.c_void_p),
        ("malloc", ctypes.c_void_p),
        ("calloc", ctypes.c_void_p),
        ("realloc", ctypes.c_void_p),
        ("free", ctypes.c_void_p),
    ]


def _load_counter() -> ctypes.CDLL:
    fd, so_path = tempfile.mkstemp(prefix="osspr-alloccount-", suffix=".so")
    os.close(fd)
    src = os.path.join(HERE, "alloccount.c")
    subprocess.check_call(
        ["gcc", "-shared", "-fPIC", "-O2", "-o", so_path, src],
        stdout=subprocess.DEVNULL,
    )
    return ctypes.CDLL(so_path)


def _count(lib: ctypes.CDLL, fn) -> int:
    domain_obj = 2
    pyapi = ctypes.pythonapi
    pyapi.PyMem_GetAllocator.argtypes = [
        ctypes.c_int, ctypes.POINTER(_PyMemAllocatorEx)]
    pyapi.PyMem_SetAllocator.argtypes = [
        ctypes.c_int, ctypes.POINTER(_PyMemAllocatorEx)]
    lib.alloccount_install.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.alloccount_read.restype = ctypes.c_uint64

    original = _PyMemAllocatorEx()
    pyapi.PyMem_GetAllocator(domain_obj, ctypes.byref(original))
    out_malloc = ctypes.c_void_p()
    out_calloc = ctypes.c_void_p()
    out_realloc = ctypes.c_void_p()
    out_free = ctypes.c_void_p()
    lib.alloccount_install(
        original.ctx, original.malloc, original.calloc,
        original.realloc, original.free,
        ctypes.byref(out_malloc), ctypes.byref(out_calloc),
        ctypes.byref(out_realloc), ctypes.byref(out_free),
    )
    hooked = _PyMemAllocatorEx(
        original.ctx, out_malloc, out_calloc, out_realloc, out_free)
    pyapi.PyMem_SetAllocator(domain_obj, ctypes.byref(hooked))
    try:
        fn()
    finally:
        pyapi.PyMem_SetAllocator(domain_obj, ctypes.byref(original))
    return int(lib.alloccount_read())


def once() -> None:
    # No running total: each ``hits +=`` would allocate an int and drown
    # the two temporary strings this function creates per call.
    for path, prefix in PAIRS:
        if not path_startswith(path, prefix):
            raise SystemExit(f"expected prefix hit for {path}")


def main() -> None:
    lib = _load_counter()
    # Import and compile the call before counting.
    once()
    samples = [_count(lib, once) for _ in range(RUNS)]
    median = statistics.median(samples)
    noise = (max(samples) - min(samples)) / median * 100.0
    print(json.dumps({
        "baseline_value": median,
        "noise_pct": noise,
        "samples": samples,
        "metric_kind": "allocations",
    }))


if __name__ == "__main__":
    sys.exit(main() or 0)
