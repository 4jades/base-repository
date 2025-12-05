from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import sys
from typing import Any

PERF_RESULTS_DIR = "tests/perf/results"

@dataclass(frozen=True)
class PerfMeta:
    run_id: str
    ts_utc: str
    git_sha: str | None
    python: str
    platform: str
    suite: str
    source: str
    iter: int
    seed_data_rows_cnt: int | None = None

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _results_dir() -> Path:
    p = os.getenv("PERF_RESULTS_DIR", PERF_RESULTS_DIR)
    return Path(p)


def _run_id() -> str:
    return os.getenv("PERF_RUN_ID") or _default_run_id()


def _git_sha() -> str | None:
    return os.getenv("PERF_GIT_SHA")


def _sanitize_filename(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return s[:180] if len(s) > 180 else s


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _jsonl_path(meta: PerfMeta) -> Path:
    base = _results_dir() / meta.suite
    _ensure_dir(base)
    return base / f"{_sanitize_filename(meta.run_id)}.jsonl"


def _build_meta(*, suite: str, source: str, iter: int, seed_data_rows_cnt: int | None) -> PerfMeta:
    return PerfMeta(
        run_id=_run_id(),
        ts_utc=_utc_now_iso(),
        git_sha=_git_sha(),
        python=sys.version.split()[0],
        platform=platform.platform(),
        suite=suite,
        source=source,
        iter=iter,
        seed_data_rows_cnt=seed_data_rows_cnt
    )


def _write_record(meta: PerfMeta, record: dict[str, Any]) -> None:
    payload = {
        "meta": asdict(meta),
        **record,
    }
    path = _jsonl_path(meta)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))
        f.write("\n")


def record_table(
    *,
    suite: str,
    source: str,
    scenario: str,
    key_label: str,
    metrics: dict[int, dict[str, float]],
    iter: int,
    seed_data_rows_cnt: int | None = None
) -> None:
    """
    < table 형태 결과를 JSONL로 누적 저장 >
    1. meta를 만든다.
    2. record를 만든다.
    3. run_id 파일에 append 한다.
    """
    meta = _build_meta(suite=suite, source=source, iter=iter, seed_data_rows_cnt=seed_data_rows_cnt)
    record = {
        "type": "table",
        "scenario": scenario,
        "key_label": key_label,
        "metrics": {str(k): v for k, v in metrics.items()},
    }
    _write_record(meta, record)


def record_one(
    *,
    suite: str,
    source: str,
    scenario: str,
    metrics: dict[str, float],
    iter: int,
    seed_data_rows_cnt: int | None = None
) -> None:
    """
    < 단일 결과(avg/p95/p99) 형태를 JSONL로 누적 저장 >
    1. meta를 만든다.
    2. record를 만든다.
    3. run_id 파일에 append 한다.
    """
    meta = _build_meta(suite=suite, source=source, iter=iter, seed_data_rows_cnt=seed_data_rows_cnt)
    record = {
        "type": "one",
        "scenario": scenario,
        "metrics": metrics,
    }
    _write_record(meta, record)
