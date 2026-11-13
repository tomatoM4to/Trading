import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests import support


def peak_rss():
    if os.name != "nt":
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    read_info = ctypes.windll.psapi.GetProcessMemoryInfo
    read_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not read_info(process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=range(1, 6), action="append")
    parser.add_argument("--match")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    results = []
    for stage in args.stage or range(1, 6):
        loader = unittest.TestLoader()
        if args.match:
            loader.testNamePatterns = [f"*{args.match}*"]
        suite = loader.loadTestsFromName(f"tests.test_stage{stage}")
        start = time.perf_counter()
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        failed_methods = {
            getattr(t, "test_case", t).id()
            for t, _ in [*result.failures, *result.errors]
        }
        error_methods = {getattr(t, "test_case", t).id() for t, _ in result.errors}
        results.append(
            {
                "stage": stage,
                "tests": result.testsRun,
                "passed": result.testsRun - len(failed_methods) - len(result.skipped),
                "failed": len(failed_methods - error_methods),
                "errored": len(error_methods),
                "failures": [t.id() for t, _ in result.failures],
                "errors": [t.id() for t, _ in result.errors],
                "skipped": [t.id() for t, _ in result.skipped],
                "seconds": round(time.perf_counter() - start, 4),
                "peak_rss_bytes": peak_rss(),
            }
        )
    report = {
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=support.ROOT, text=True
        ).strip(),
        "python": sys.version.split()[0],
        "sqlite": support.sqlite3.sqlite_version,
        "platform": sys.platform,
        "stages": results,
    }
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int(any(r["failures"] or r["errors"] or r["tests"] == 0 for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
