from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

import matplotlib.pyplot as plt


@dataclass(frozen=True)
class Record:
    run_id: str
    ts_utc: str
    suite: str
    source: str
    type: str
    scenario: str
    key_label: str | None
    metrics: Any
    seed_data_rows: int | None
    

def _parse_ts(ts_utc: str) -> datetime:
    # 1) Parse timestamps like "2025-11-26T..." (UTC offset may be included)
    return datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))


def _scenario_family_and_variant(scenario: str) -> tuple[str, str]:
    # 1) Treat the leading "[..][..]" chunks as the family
    # 2) Treat the remaining text as the variant
    m = re.match(r"^(\[[^\]]+\](?:\[[^\]]+\])*)\s*(.*)$", scenario)
    if m:
        fam = m.group(1).strip()
        var = m.group(2).strip()
        if not var:
            return fam, "(default)"
        return fam, var

    # Handle CPU cases where something like "_sa" is appended right after "[...]"
    m2 = re.match(r"^(\[[^\]]+\])(.*)$", scenario)
    if m2:
        fam = m2.group(1).strip()
        var = m2.group(2).strip()
        var = var.lstrip("_- ").strip()
        return fam, (var or "(default)")

    return scenario, "(default)"


def _safe(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    s = s.lstrip("_.")
    if not s:
        s = "scenario"
    return s[:180] if len(s) > 180 else s


def _load_all(results_dir: Path) -> list[Record]:
    records: list[Record] = []
    for path in results_dir.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                meta = obj["meta"]
                records.append(
                    Record(
                        run_id=meta["run_id"],
                        ts_utc=meta["ts_utc"],
                        suite=meta["suite"],
                        source=meta["source"],
                        type=obj["type"],
                        scenario=obj["scenario"],
                        key_label=obj.get("key_label"),
                        metrics=obj["metrics"],
                        seed_data_rows=meta.get("seed_data_rows_cnt"),
                    )
                )
    return records


def _pick_latest_run(records: list[Record]) -> str:
    # 1) Pick the most recent run_id based on timestamp
    records_sorted = sorted(records, key=lambda r: _parse_ts(r.ts_utc))
    return records_sorted[-1].run_id


def _plot_table_group(
    *,
    report_root: Path,
    out_dir: Path,
    title: str,
    key_label: str,
    series: dict[str, dict[int, dict[str, float]]],
) -> list[str]:
    paths: list[str] = []

    xs_all: set[int] = set()
    for _, points in series.items():
        xs_all.update(points.keys())
    xs = sorted(xs_all)

    for metric in ["avg", "p95", "p99"]:
        plt.figure()
        for variant, points in series.items():
            ys = []
            for x in xs:
                ys.append(points[x][metric] if x in points else float("nan"))
            plt.plot(xs, ys, marker="o", label=variant)

        plt.title(f"{title} ({metric})")
        plt.xlabel(key_label)
        plt.ylabel("ms")
        plt.legend()

        out_dir.mkdir(parents=True, exist_ok=True)
        png = out_dir / f"{_safe(metric)}.png"
        plt.savefig(png, dpi=160, bbox_inches="tight")
        plt.close()

        paths.append(png.relative_to(report_root).as_posix())

    return paths


def _plot_one_group(
    *,
    report_root: Path,
    out_dir: Path,
    title: str,
    series: dict[str, dict[str, float]],
) -> list[str]:
    paths: list[str] = []
    variants = list(series.keys())

    for metric in ["avg", "p95", "p99"]:
        plt.figure()
        ys = [series[v][metric] for v in variants]
        xs = list(range(len(variants)))
        plt.bar(xs, ys)
        plt.xticks(xs, variants, rotation=30, ha="right")
        plt.title(f"{title} ({metric})")
        plt.ylabel("ms")

        out_dir.mkdir(parents=True, exist_ok=True)
        png = out_dir / f"{_safe(metric)}.png"
        plt.savefig(png, dpi=160, bbox_inches="tight")
        plt.close()

        paths.append(png.relative_to(report_root).as_posix())

    return paths



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=str, default="tests/perf/results")
    parser.add_argument("--out-dir", type=str, default="tests/perf/report")
    parser.add_argument("--run-id", type=str, default="")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.out_dir)

    records = _load_all(results_dir)
    if not records:
        raise SystemExit(f"no records under: {results_dir}")

    run_id = args.run_id or _pick_latest_run(records)
    picked = [r for r in records if r.run_id == run_id]

    # 1) Group by (suite, family, type, key_label)
    table_groups: dict[tuple[str, str, str, str], dict[str, dict[int, dict[str, float]]]] = defaultdict(dict)
    one_groups: dict[tuple[str, str, str], dict[str, dict[str, float]]] = defaultdict(dict)

    for r in picked:
        family, variant = _scenario_family_and_variant(r.scenario)

        if r.type == "table":
            key_label = r.key_label or "X"
            metrics_raw: dict[str, dict[str, float]] = r.metrics
            metrics: dict[int, dict[str, float]] = {int(k): v for k, v in metrics_raw.items()}
            table_groups[(r.suite, family, r.type, key_label)][variant] = metrics

        elif r.type == "one":
            one_groups[(r.suite, family, r.type)][variant] = r.metrics

    # 2) Generate images + write index.html
    out_dir.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []
    sections.append(f"<h1>Performance Report</h1>")
    sections.append(f"<h2>run_id: {run_id}</h2>")

    seed_data_rows = None
    for r in picked:
        if r.seed_data_rows is not None:
            seed_data_rows = r.seed_data_rows
            break
    if seed_data_rows is not None:
        sections.append(f"<h2>seed_data_rows: {seed_data_rows}</h2>")

    # Table groups
    for (suite, family, _type, key_label), series in sorted(table_groups.items()):
        base = out_dir / suite / _safe(family) / "table"
        rels = _plot_table_group(
            report_root=out_dir,
            out_dir=base,
            title=f"{suite} {family}",
            key_label=key_label,
            series=series,
        )
        sections.append(f"<h2>{family}</h2>")
        img_html = []
        for rel in rels:
            img_html.append(f"<div class='card'><img src='{rel}'></div>")
        sections.append("<div class='grid2'>" + "\n".join(img_html) + "</div>")


    # One groups
    for (suite, family, _type, key_label), table_series in sorted(table_groups.items()):
        base = out_dir / suite / _safe(family) / "table"
        rels = _plot_table_group(
            report_root=out_dir,
            out_dir=base,
            title=f"{suite} {family}",
            key_label=key_label,
            series=table_series,
        )
        sections.append(f"<h2>{family}</h2>")
        img_html = []
        for rel in rels:
            img_html.append(f"<div class='card'><img src='{rel}'></div>")
        sections.append("<div class='grid2'>" + "\n".join(img_html) + "</div>")


    index = out_dir / "index.html"
    index.write_text(
        "<html><head><meta charset='utf-8'><title>Perf Report</title>"
        "<style>"
        "body{margin:0 auto;padding:16px;font-family:system-ui,-apple-system,sans-serif;}"
        ".grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;align-items:start;}"
        ".card{border:1px solid #e5e7eb;border-radius:10px;padding:10px;background:#fff;}"
        ".card img{width:100%;height:auto;display:block;}"
        "</style>"
        "</head><body>"
        + "\n".join(sections)
        + "</body></html>",
        encoding="utf-8",   
    )


    print(f"[perf-view] wrote: {index}")


if __name__ == "__main__":
    main()
