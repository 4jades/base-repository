from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = Path("tests/perf/results")

def main() -> None:
    runs = defaultdict(list)  # run_id -> [ts, suite, file]
    for p in RESULTS_DIR.rglob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            meta = obj["meta"]
            run_id = meta["run_id"]
            runs[run_id].append((meta["ts_utc"], meta["suite"], str(p)))

    for run_id in sorted(runs.keys()):
        ts = min(t for t, _, _ in runs[run_id])
        suites = sorted(set(s for _, s, _ in runs[run_id]))
        print(f"{run_id}  ts={ts}  suites={','.join(suites)}")

if __name__ == "__main__":
    main()
