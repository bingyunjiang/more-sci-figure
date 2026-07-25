#!/usr/bin/env python3
"""为朋友圈案例版式生成高质量、但仍受复核门控的科研重绘图。

只读取 candidates.csv；严格保留 segment_break，不生成 data.csv 或 render/。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "more-sci-figure-matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "social" / "showcase-redraws"
FIXED_TIME = dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)

PALETTE = {
    "red": "#E5483F",
    "blue": "#126EAA",
    "blue_dark": "#245A84",
    "blue_light": "#527FB8",
    "ink": "#242628",
    "grid": "#DCE3E6",
    "muted": "#667078",
}

FIGURES: dict[str, dict[str, Any]] = {
    "fig7": {
        "xlabel": "True strain",
        "ylabel": "True stress (MPa)",
        "xlim": (0.0, 0.10),
        "ylim": (0.0, 145.0),
        "xticks": [0.00, 0.02, 0.04, 0.06, 0.08, 0.10],
        "yticks": [0, 25, 50, 75, 100, 125],
        "legend_ncol": 3,
        "series": [
            ("test_0deg", "Test — 0°", PALETTE["red"], "-", "s"),
            ("mfh_0deg", "MFH — 0°", PALETTE["red"], "--", None),
            ("test_45deg", "Test — 45°", PALETTE["blue"], "-", "^"),
            ("mfh_45deg", "MFH — 45°", PALETTE["blue"], "-.", None),
            ("test_90deg", "Test — 90°", PALETTE["ink"], "-", "D"),
            ("mfh_90deg", "MFH — 90°", PALETTE["ink"], "--", None),
        ],
        "dash_components": {"mfh_0deg", "mfh_45deg", "mfh_90deg"},
    },
    "fig9": {
        "xlabel": "Z-position through thickness (mm)",
        "ylabel": "Fiber orientation tensor",
        "xlim": (0.0, 1.65),
        "ylim": (0.0, 0.95),
        "xticks": [0.0, 0.4, 0.8, 1.2, 1.6],
        "yticks": [0.0, 0.2, 0.4, 0.6, 0.8],
        "legend_ncol": 3,
        "series": [
            ("simulation_a11", "Simulation — a11", PALETTE["blue_dark"], "-", "^"),
            ("uct_test_a11", "µCT test — a11", PALETTE["red"], "-", None),
            ("simulation_a22", "Simulation — a22", PALETTE["blue"], "-", "o"),
            ("uct_test_a22", "µCT test — a22", PALETTE["blue_light"], "-", None),
            ("simulation_a33", "Simulation — a33", PALETTE["ink"], "-", "x"),
            ("uct_test_a33", "µCT test — a33", PALETTE["ink"], "--", None),
        ],
        "dash_components": {"uct_test_a33"},
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row["x"] = float(row["x"])
        row["y"] = float(row["y"])
        row["pixel_x"] = float(row["pixel_x"])
        row["segment_break"] = row["segment_break"].strip().lower() == "true"
    return rows


def split_segments(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["pixel_x"]):
        if row["segment_break"] and current:
            result.append(current)
            current = []
        current.append(row)
    if current:
        result.append(current)
    return result


def render(name: str) -> dict[str, Any]:
    spec = FIGURES[name]
    rows = read_rows(ROOT / name / "candidates.csv")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["series"]].append(row)

    with plt.rc_context(
        {
            "font.family": "Avenir Next",
            "font.size": 11,
            "axes.labelcolor": PALETTE["ink"],
            "axes.edgecolor": "#1F2529",
            "xtick.color": "#454D52",
            "ytick.color": "#454D52",
            "svg.hashsalt": f"jiang-tian-{name}-social-redraw",
        }
    ):
        figure, axis = plt.subplots(figsize=(10.8, 7.2), dpi=180)
        figure.patch.set_facecolor("#FFFFFF")
        axis.set_facecolor("#FFFFFF")

        proxies: list[Line2D] = []
        for series, label, color, linestyle, marker in spec["series"]:
            segments = split_segments(grouped[series])
            for segment in segments:
                axis.plot(
                    [row["x"] for row in segment],
                    [row["y"] for row in segment],
                    color=color,
                    linestyle=linestyle,
                    linewidth=2.35,
                    solid_capstyle="round",
                    marker=marker,
                    markersize=5.0 if marker else 0,
                    markerfacecolor=color if marker else None,
                    markeredgecolor="#FFFFFF" if marker in {"s", "^", "o", "D"} else color,
                    markeredgewidth=0.75,
                    markevery=max(1, len(segment) // 9),
                    zorder=4 if marker else 3,
                )
            proxies.append(
                Line2D(
                    [0],
                    [0],
                    color=color,
                    linestyle=linestyle,
                    linewidth=2.35,
                    marker=marker,
                    markersize=5.2 if marker else 0,
                    markerfacecolor=color if marker else None,
                    markeredgecolor="#FFFFFF" if marker in {"s", "^", "o", "D"} else color,
                    markeredgewidth=0.75,
                    label=label,
                )
            )

        axis.set_xlim(*spec["xlim"])
        axis.set_ylim(*spec["ylim"])
        axis.set_xticks(spec["xticks"])
        axis.set_yticks(spec["yticks"])
        axis.set_xlabel(spec["xlabel"], fontsize=14, fontweight=600, labelpad=13)
        axis.set_ylabel(spec["ylabel"], fontsize=14, fontweight=600, labelpad=13)
        axis.tick_params(axis="both", labelsize=11, length=5, width=1.0)
        axis.grid(axis="y", color=PALETTE["grid"], linewidth=0.8, alpha=0.75)
        axis.grid(axis="x", visible=False)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["left"].set_linewidth(1.15)
        axis.spines["bottom"].set_linewidth(1.15)
        axis.legend(
            handles=proxies,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.13),
            ncol=spec["legend_ncol"],
            frameon=False,
            columnspacing=1.7,
            handlelength=2.6,
            handletextpad=0.65,
            fontsize=10.2,
        )
        figure.text(
            0.93,
            0.018,
            "Digitized candidate · pending human review",
            ha="right",
            va="bottom",
            color=PALETTE["muted"],
            fontsize=8.7,
        )
        figure.subplots_adjust(left=0.115, right=0.975, top=0.81, bottom=0.13)

        OUT.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, Any] = {}
        for suffix in ("png", "svg", "pdf"):
            path = OUT / f"{name}-redraw.{suffix}"
            if suffix == "pdf":
                metadata = {
                    "Creator": "more-sci-figure 0.2.0",
                    "CreationDate": FIXED_TIME,
                    "ModDate": FIXED_TIME,
                }
            elif suffix == "svg":
                metadata = {
                    "Creator": "more-sci-figure 0.2.0",
                    "Date": "2021-01-01T00:00:00+00:00",
                }
            else:
                metadata = {"Software": "more-sci-figure 0.2.0"}
            figure.savefig(path, facecolor="#FFFFFF", metadata=metadata)
            outputs[suffix] = {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        plt.close(figure)

    return {
        "figure": name,
        "status": "candidate_preview",
        "review_status": "not_run",
        "source": str((ROOT / name / "candidates.csv").relative_to(ROOT)),
        "source_sha256": sha256(ROOT / name / "candidates.csv"),
        "rows": len(rows),
        "segment_breaks_preserved": True,
        "outputs": outputs,
    }


def main() -> None:
    reports = [render("fig7"), render("fig9")]
    report_path = OUT / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema": "more-sci-figure.social-redraw.v1",
                "formal_render": False,
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
