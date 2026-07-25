#!/usr/bin/env python3
"""Jiang & Tian (2021) Fig. 7/9 项目专用候选提取与预览重绘。

该脚本不会生成正式 data.csv，也不会把预览写入 render/。候选值必须
在 review.html 中完成人工复核后，才能进入 more-sci-figure 的正式流程。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "more-sci-figure-matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

matplotlib.rcParams["svg.hashsalt"] = "jiang-tian-2021-more-sci-figure"

ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parent

FIG7 = {
    "directory": ROOT / "fig7",
    "plot_box": [128, 14, 818, 547],
    "legend_box": [210, 390, 815, 535],
    "ranges": {
        "red": [128, 425],
        "blue": [128, 680],
        "black": [128, 625],
    },
}

FIG9 = {
    "directory": ROOT / "fig9",
    "plot_box": [125, 17, 821, 438],
    "legend_box": [520, 120, 815, 390],
    "data_x_range": [132, 705],
}

TABLE3 = [
    (1, 0.041, 0.772, 0.164, 0.064),
    (2, 0.124, 0.728, 0.202, 0.070),
    (3, 0.206, 0.816, 0.125, 0.059),
    (4, 0.289, 0.807, 0.130, 0.063),
    (5, 0.371, 0.820, 0.117, 0.063),
    (6, 0.454, 0.816, 0.118, 0.066),
    (7, 0.536, 0.800, 0.131, 0.069),
    (8, 0.619, 0.768, 0.157, 0.075),
    (9, 0.701, 0.705, 0.215, 0.080),
    (10, 0.784, 0.305, 0.611, 0.084),
    (11, 0.866, 0.322, 0.599, 0.079),
    (12, 0.949, 0.694, 0.226, 0.080),
    (13, 1.031, 0.779, 0.146, 0.075),
    (14, 1.114, 0.800, 0.128, 0.072),
    (15, 1.196, 0.816, 0.115, 0.070),
    (16, 1.279, 0.821, 0.111, 0.069),
    (17, 1.361, 0.827, 0.106, 0.067),
    (18, 1.444, 0.812, 0.120, 0.068),
    (19, 1.526, 0.726, 0.186, 0.088),
    (20, 1.609, 0.769, 0.153, 0.078),
]

SERIES_STYLES = {
    "test_0deg": {"color": "#ef3b2c", "linestyle": "-", "marker": "s"},
    "test_45deg": {"color": "#0570b0", "linestyle": "-", "marker": "^"},
    "test_90deg": {"color": "#222222", "linestyle": "-", "marker": "D"},
    "mfh_0deg": {"color": "#ef3b2c", "linestyle": "--", "marker": None},
    "mfh_45deg": {"color": "#0570b0", "linestyle": "-.", "marker": None},
    "mfh_90deg": {"color": "#222222", "linestyle": "--", "marker": None},
    "simulation_a11": {"color": "#2b618e", "linestyle": "-", "marker": "^"},
    "simulation_a22": {"color": "#0070c0", "linestyle": "-", "marker": "o"},
    "simulation_a33": {"color": "#222222", "linestyle": "-", "marker": "x"},
    "uct_test_a11": {"color": "#ef0000", "linestyle": "-", "marker": None},
    "uct_test_a22": {"color": "#4f81bd", "linestyle": "-", "marker": None},
    "uct_test_a33": {"color": "#222222", "linestyle": "--", "marker": None},
}


def load_skill_module() -> Any:
    path = SKILL_ROOT / "scripts" / "more_sci_figure.py"
    spec = importlib.util.spec_from_file_location("more_sci_figure", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 more-sci-figure 模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MSF = load_skill_module()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(path.parent.parent)),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def restrict_mask(
    mask: np.ndarray,
    plot_box: list[int],
    legend_box: list[int] | None = None,
) -> np.ndarray:
    result = np.zeros_like(mask, dtype=bool)
    left, top, right, bottom = plot_box
    result[top + 4 : bottom - 3, left + 4 : right - 3] = mask[
        top + 4 : bottom - 3, left + 4 : right - 3
    ]
    if legend_box is not None:
        ll, lt, lr, lb = legend_box
        result[lt : lb + 1, ll : lr + 1] = False
    return result


def generic_color_masks(image: np.ndarray) -> dict[str, np.ndarray]:
    red = image[:, :, 0].astype(int)
    green = image[:, :, 1].astype(int)
    blue = image[:, :, 2].astype(int)
    maximum = np.maximum.reduce([red, green, blue])
    minimum = np.minimum.reduce([red, green, blue])
    return {
        "red": (red > 140) & (red - green > 55) & (red - blue > 50),
        "blue": (blue > 80) & (blue - red > 25) & (blue - green > -30),
        "black": (maximum < 100) & (maximum - minimum < 22),
    }


def nearest_target_masks(
    image: np.ndarray,
    targets: dict[str, tuple[int, int, int]],
    tolerance: float,
) -> dict[str, np.ndarray]:
    array = image.astype(float)
    distances = np.stack(
        [
            np.linalg.norm(array - np.asarray(color, dtype=float), axis=2)
            for color in targets.values()
        ]
    )
    nearest = distances.argmin(axis=0)
    minimum = distances.min(axis=0)
    return {
        name: (nearest == index) & (minimum <= tolerance)
        for index, name in enumerate(targets)
    }


def column_groups(
    mask: np.ndarray,
    x: int,
    *,
    maximum_gap: int = 2,
    y_range: tuple[float, float] | None = None,
) -> list[tuple[float, int]]:
    ys = np.flatnonzero(mask[:, x])
    if y_range is not None:
        ys = ys[(ys >= y_range[0]) & (ys <= y_range[1])]
    if not ys.size:
        return []
    groups: list[np.ndarray] = []
    start = 0
    for index in range(1, len(ys)):
        if int(ys[index] - ys[index - 1]) > maximum_gap:
            groups.append(ys[start:index])
            start = index
    groups.append(ys[start:])
    return [(float(np.median(group)), int(len(group))) for group in groups]


def smooth_track(track: dict[int, float], radius: int = 3) -> dict[int, float]:
    if not track:
        return {}
    result: dict[int, float] = {}
    for x in sorted(track):
        values = [
            y
            for px, y in track.items()
            if abs(px - x) <= radius and math.isfinite(y)
        ]
        result[x] = float(np.median(values))
    return result


def ordered_branch_track(
    mask: np.ndarray,
    x_range: tuple[int, int],
    selector: str,
    *,
    y_range: tuple[float, float] | None = None,
) -> dict[int, float]:
    track: dict[int, float] = {}
    for x in range(x_range[0], x_range[1] + 1):
        groups = column_groups(mask, x, y_range=y_range)
        if not groups:
            continue
        centers = [center for center, _ in groups]
        track[x] = min(centers) if selector == "min" else max(centers)
    return smooth_track(track)


def continuity_track(
    mask: np.ndarray,
    x_range: tuple[int, int],
    *,
    y_range: tuple[float, float] | None = None,
    initial_selector: str = "largest",
    maximum_jump: float = 22.0,
) -> dict[int, float]:
    track: dict[int, float] = {}
    previous: float | None = None
    previous_x: int | None = None
    for x in range(x_range[0], x_range[1] + 1):
        groups = column_groups(mask, x, y_range=y_range)
        if not groups:
            continue
        if previous is None or previous_x is None or x - previous_x > 14:
            if initial_selector == "min":
                selected = min(groups, key=lambda item: item[0])
            elif initial_selector == "max":
                selected = max(groups, key=lambda item: item[0])
            else:
                selected = max(groups, key=lambda item: item[1])
        else:
            selected = min(
                groups,
                key=lambda item: abs(item[0] - previous) - min(item[1], 6) * 0.35,
            )
            if abs(selected[0] - previous) > maximum_jump:
                continue
        track[x] = selected[0]
        previous = selected[0]
        previous_x = x
    return smooth_track(track)


def reference_guided_track(
    mask: np.ndarray,
    x_range: tuple[int, int],
    x_map: Any,
    y_map: Any,
    reference_points: list[tuple[float, float]],
    *,
    maximum_pixel_distance: float = 16.0,
    y_range: tuple[float, float] | None = None,
) -> dict[int, float]:
    """用官方表格值帮助在多个真实像素分支中选轨，不创建无像素证据的点。"""
    reference_x = np.asarray([point[0] for point in reference_points], dtype=float)
    reference_y = np.asarray([point[1] for point in reference_points], dtype=float)
    track: dict[int, float] = {}
    for x in range(x_range[0], x_range[1] + 1):
        data_x = x_map.value(x)
        if data_x < reference_x.min() or data_x > reference_x.max():
            continue
        expected_y = float(np.interp(data_x, reference_x, reference_y))
        expected_pixel_y = y_map.pixel(expected_y)
        groups = column_groups(mask, x, y_range=y_range)
        if not groups:
            continue
        selected = min(groups, key=lambda item: abs(item[0] - expected_pixel_y))
        if abs(selected[0] - expected_pixel_y) <= maximum_pixel_distance:
            track[x] = selected[0]
    return smooth_track(track)


def fill_short_track_gaps_from_pixels(
    track: dict[int, float],
    support_mask: np.ndarray,
    *,
    maximum_gap_pixels: int = 26,
    corridor_half_height: float = 9.0,
    y_range: tuple[float, float] | None = None,
) -> dict[int, float]:
    """只用缺口内实际存在的支持像素补全颜色阈值造成的短缺列。"""
    if len(track) < 2:
        return track
    result = dict(track)
    xs = sorted(track)
    for left_x, right_x in zip(xs, xs[1:]):
        gap = right_x - left_x
        if gap <= 1 or gap > maximum_gap_pixels:
            continue
        left_y = track[left_x]
        right_y = track[right_x]
        for x in range(left_x + 1, right_x):
            expected_y = left_y + (right_y - left_y) * (
                (x - left_x) / gap
            )
            groups = column_groups(support_mask, x, y_range=y_range)
            if not groups:
                continue
            selected = min(groups, key=lambda item: abs(item[0] - expected_y))
            if abs(selected[0] - expected_y) <= corridor_half_height:
                result[x] = selected[0]
    return smooth_track(result)


def residual_dash_tracks(
    mask: np.ndarray,
    solid_track: dict[int, float],
    x_range: tuple[int, int],
    relation: str,
    *,
    removal_radius: int = 7,
) -> list[dict[int, float]]:
    residual = mask.copy()
    for x, y in solid_track.items():
        top = max(0, int(math.floor(y - removal_radius)))
        bottom = min(residual.shape[0], int(math.ceil(y + removal_radius + 1)))
        residual[top:bottom, x] = False
    keep = np.zeros_like(residual, dtype=bool)
    keep[:, x_range[0] : x_range[1] + 1] = True
    residual &= keep
    labels, count = ndimage.label(residual, structure=np.ones((3, 3), dtype=int))
    tracks: list[dict[int, float]] = []
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        if len(xs) < 6:
            continue
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        if width < 5 or max(width, height) / max(1, min(width, height)) < 1.35:
            continue
        component_track: dict[int, float] = {}
        relation_checks: list[float] = []
        for x in range(int(xs.min()), int(xs.max()) + 1):
            local = ys[xs == x]
            if not local.size:
                continue
            center = float(np.median(local))
            if x in solid_track:
                relation_checks.append(center - solid_track[x])
            component_track[x] = center
        if not relation_checks:
            continue
        median_relation = float(np.median(relation_checks))
        if relation == "above" and median_relation >= -3:
            continue
        if relation == "below" and median_relation <= 3:
            continue
        tracks.append(smooth_track(component_track, radius=2))
    tracks.sort(key=lambda item: min(item) if item else math.inf)
    return tracks


def rows_from_track(
    track: dict[int, float],
    series: str,
    x_map: Any,
    y_map: Any,
    *,
    sample_step: int = 10,
    force_segment_break: bool = False,
    evidence_note: str,
) -> list[dict[str, Any]]:
    if not track:
        return []
    rows: list[dict[str, Any]] = []
    xs = sorted(track)
    last_pixel_x: float | None = None
    for target in range(xs[0], xs[-1] + 1, sample_step):
        nearby = [x for x in xs if abs(x - target) <= max(2, sample_step // 3)]
        if not nearby:
            continue
        pixel_x = float(np.median(nearby))
        pixel_y = float(np.median([track[x] for x in nearby]))
        segment_break = (
            force_segment_break
            or last_pixel_x is None
            or pixel_x - last_pixel_x > sample_step * 1.8
        )
        rows.append(
            {
                "series": series,
                "x": x_map.value(pixel_x),
                "y": y_map.value(pixel_y),
                "x_uncertainty": x_map.uncertainty(
                    pixel_x, pixel_half_width=sample_step / 2
                ),
                "y_uncertainty": y_map.uncertainty(
                    pixel_y, pixel_half_width=2.0
                ),
                "pixel_x": pixel_x,
                "pixel_y": pixel_y,
                "pixel_half_height": 2.0,
                "segment_break": segment_break,
                "status": "visible_candidate",
                "provenance": "image_candidate",
                "evidence_note": evidence_note,
            }
        )
        force_segment_break = False
        last_pixel_x = pixel_x
    return rows


def merge_dash_style_breaks(
    rows: list[dict[str, Any]],
    *,
    maximum_gap_pixels: float = 28.0,
) -> None:
    """把规律性的虚线短划间隔视为线型空白，而不是数据缺失区。"""
    previous_pixel_x: float | None = None
    for row in sorted(rows, key=lambda item: float(item["pixel_x"])):
        pixel_x = float(row["pixel_x"])
        row["segment_break"] = (
            previous_pixel_x is None
            or pixel_x - previous_pixel_x > maximum_gap_pixels
        )
        previous_pixel_x = pixel_x
        row["evidence_note"] += (
            f" 相邻短划像素间隔不超过 {maximum_gap_pixels:g}px 时，"
            "按虚线样式空白归入同一数据段；更大空白仍保留为缺失区。"
        )


def extract_fig7(image: np.ndarray, project: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    x_map = MSF.AxisMap(project["chart"]["x_axis"])
    y_map = MSF.AxisMap(project["chart"]["y_axis"])
    masks = {
        name: restrict_mask(mask, FIG7["plot_box"], FIG7["legend_box"])
        for name, mask in generic_color_masks(image).items()
    }
    configs = [
        ("red", "test_0deg", "mfh_0deg", "max", "above"),
        ("blue", "test_45deg", "mfh_45deg", "min", "below"),
        ("black", "test_90deg", "mfh_90deg", "max", "above"),
    ]
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"series": {}}
    for color_name, solid_id, dash_id, selector, dash_relation in configs:
        x_range = tuple(FIG7["ranges"][color_name])
        solid = ordered_branch_track(masks[color_name], x_range, selector)
        solid_rows = rows_from_track(
            solid,
            solid_id,
            x_map,
            y_map,
            sample_step=10,
            evidence_note=(
                f"{color_name} 连续标记线；按同色分支位置与连续性提取，"
                "图例区域已排除。"
            ),
        )
        rows.extend(solid_rows)

        dash_tracks = residual_dash_tracks(
            masks[color_name],
            solid,
            x_range,
            dash_relation,
            removal_radius=7,
        )
        dash_rows: list[dict[str, Any]] = []
        for track in dash_tracks:
            dash_rows.extend(
                rows_from_track(
                    track,
                    dash_id,
                    x_map,
                    y_map,
                    sample_step=6,
                    force_segment_break=True,
                    evidence_note=(
                        f"{color_name} 可见虚线段；从连续标记线邻域移除后，"
                        "仅保留满足相对位置与形状约束的连通段。"
                    ),
                )
            )
        merge_dash_style_breaks(dash_rows)
        rows.extend(dash_rows)
        diagnostics["series"][solid_id] = {
            "candidate_rows": len(solid_rows),
            "method": "ordered continuous branch",
        }
        diagnostics["series"][dash_id] = {
            "candidate_rows": len(dash_rows),
            "visible_dash_components": len(dash_tracks),
            "method": "residual visible dash components",
        }
    diagnostics["limitations"] = [
        "同色曲线完全重合处不为虚线系列生成独立候选",
        "虚线候选只覆盖可见线段，预览保留段间空缺",
        "图例矩形被排除，不从被图例遮挡的像素推断数值",
    ]
    before_filter = len(rows)
    rows = [
        row
        for row in rows
        if not (float(row["x"]) < 0.003 and float(row["y"]) > 25.0)
    ]
    diagnostics["axis_artifacts_removed"] = before_filter - len(rows)
    return rows, diagnostics


def extract_fig9(image: np.ndarray, project: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    x_map = MSF.AxisMap(project["chart"]["x_axis"])
    y_map = MSF.AxisMap(project["chart"]["y_axis"])
    generic = {
        name: restrict_mask(mask, FIG9["plot_box"], FIG9["legend_box"])
        for name, mask in generic_color_masks(image).items()
    }
    rgb = image.astype(int)
    relaxed_blue_support = (
        (rgb[:, :, 2] > 55)
        & (rgb[:, :, 2] - rgb[:, :, 0] > 8)
        & (rgb[:, :, 2] - rgb[:, :, 1] > -55)
    )
    relaxed_blue_support = restrict_mask(
        relaxed_blue_support,
        FIG9["plot_box"],
        FIG9["legend_box"],
    )
    target_masks = nearest_target_masks(
        image,
        {
            "simulation_a11": (43, 97, 142),
            "simulation_a22": (0, 112, 192),
            "uct_test_a22": (79, 129, 189),
        },
        tolerance=46,
    )
    target_masks = {
        name: restrict_mask(mask, FIG9["plot_box"], FIG9["legend_box"])
        for name, mask in target_masks.items()
    }
    x_range = tuple(FIG9["data_x_range"])
    tracks = {
        "simulation_a11": continuity_track(
            target_masks["simulation_a11"],
            x_range,
            y_range=(35, 250),
            initial_selector="min",
        ),
        "simulation_a22": continuity_track(
            target_masks["simulation_a22"],
            x_range,
            y_range=(245, 430),
            initial_selector="largest",
        ),
        "uct_test_a22": reference_guided_track(
            target_masks["uct_test_a22"],
            x_range,
            x_map,
            y_map,
            [(row[1], row[3]) for row in TABLE3],
            maximum_pixel_distance=40.0,
            y_range=(120, 430),
        ),
        "uct_test_a11": continuity_track(
            generic["red"],
            x_range,
            y_range=(35, 380),
            initial_selector="largest",
        ),
    }
    tracks["simulation_a11"] = fill_short_track_gaps_from_pixels(
        tracks["simulation_a11"],
        relaxed_blue_support,
        maximum_gap_pixels=28,
        corridor_half_height=12.0,
        y_range=(35, 250),
    )
    tracks["simulation_a22"] = fill_short_track_gaps_from_pixels(
        tracks["simulation_a22"],
        relaxed_blue_support,
        maximum_gap_pixels=28,
        corridor_half_height=12.0,
        y_range=(245, 430),
    )
    black_solid = ordered_branch_track(
        generic["black"], x_range, "max", y_range=(365, 432)
    )
    tracks["simulation_a33"] = black_solid
    black_dashes = residual_dash_tracks(
        generic["black"],
        black_solid,
        x_range,
        "above",
        removal_radius=6,
    )

    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"series": {}}
    for series, track in tracks.items():
        series_rows = rows_from_track(
            track,
            series,
            x_map,
            y_map,
            sample_step=10,
            evidence_note=(
                "按原始 JPEG 描边目标颜色、坐标范围与局部连续性提取；"
                "图例区域已排除。"
            ),
        )
        rows.extend(series_rows)
        diagnostics["series"][series] = {
            "candidate_rows": len(series_rows),
            "method": "target-color continuity track",
        }

    dash_rows: list[dict[str, Any]] = []
    for track in black_dashes:
        dash_rows.extend(
            rows_from_track(
                track,
                "uct_test_a33",
                x_map,
                y_map,
                sample_step=6,
                force_segment_break=True,
                evidence_note=(
                    "黑色可见虚线段；移除 simulation_a33 连续标记线邻域后提取。"
                ),
            )
        )
    merge_dash_style_breaks(dash_rows)
    rows.extend(dash_rows)
    diagnostics["series"]["uct_test_a33"] = {
        "candidate_rows": len(dash_rows),
        "visible_dash_components": len(black_dashes),
        "method": "residual visible dash components",
    }
    diagnostics["limitations"] = [
        "图例区域被排除，不从被覆盖的像素推断数值",
        "颜色目标来自原始嵌入 JPEG，JPEG 压缩造成的局部缺口保留为分段",
        "µCT a22 使用 Table 3 仅辅助在真实蓝色像素分支中选轨，不创建无像素证据的点",
        "µCT 图像候选另与论文 Table 3 的官方表格值交叉核对",
    ]
    return rows, diagnostics


def assign_candidate_ids(rows: list[dict[str, Any]]) -> None:
    counters: dict[str, int] = defaultdict(int)
    for row in sorted(rows, key=lambda item: (item["series"], item["pixel_x"])):
        counters[row["series"]] += 1
        row["candidate_id"] = (
            f"line-{row['series']}-{counters[row['series']]:04d}"
        )


def write_candidates(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "candidate_id",
        "series",
        "x",
        "y",
        "x_uncertainty",
        "y_uncertainty",
        "pixel_x",
        "pixel_y",
        "pixel_half_height",
        "segment_break",
        "status",
        "provenance",
        "evidence_note",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def draw_overlay(
    source: Image.Image,
    rows: list[dict[str, Any]],
    output: Path,
) -> None:
    overlay = source.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.rectangle([0, 0, overlay.width, 28], fill=(237, 139, 35, 225))
    draw.text(
        (8, 8),
        "CANDIDATES - HUMAN REVIEW REQUIRED",
        fill=(255, 255, 255, 255),
    )
    for row in rows:
        x = float(row["pixel_x"])
        y = float(row["pixel_y"])
        color = SERIES_STYLES[row["series"]]["color"]
        draw.ellipse(
            [x - 3.5, y - 3.5, x + 3.5, y + 3.5],
            outline=color,
            width=2,
        )
    overlay.save(output)


def segment_rows(rows: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: float(item["pixel_x"])):
        if row["segment_break"] and current:
            segments.append(current)
            current = []
        current.append(row)
    if current:
        segments.append(current)
    return segments


def render_candidate_preview(
    directory: Path,
    project: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    preview = directory / "preview"
    preview.mkdir(exist_ok=True)
    fig, axis = plt.subplots(figsize=(8.4, 5.8), dpi=180)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["series"]].append(row)
    for series, series_rows in grouped.items():
        style = SERIES_STYLES[series]
        label_used = False
        for segment in segment_rows(series_rows):
            axis.plot(
                [float(row["x"]) for row in segment],
                [float(row["y"]) for row in segment],
                color=style["color"],
                linestyle=style["linestyle"],
                marker=style["marker"],
                markersize=3.2,
                linewidth=1.6,
                markevery=max(1, len(segment) // 12),
                label=series if not label_used else None,
            )
            label_used = True
    axis.set_xlabel(project["render"]["x_label"])
    axis.set_ylabel(project["render"]["y_label"])
    axis.set_title(
        f"{project['render']['title']}\nCANDIDATE PREVIEW — NOT HUMAN-REVIEWED"
    )
    axis.grid(True, color="#d8e3ea", linewidth=0.7, alpha=0.8)
    axis.legend(fontsize=7.5, frameon=False, ncol=2)
    axis.text(
        0.5,
        0.5,
        "CANDIDATE PREVIEW",
        transform=axis.transAxes,
        ha="center",
        va="center",
        fontsize=27,
        color="#d97706",
        alpha=0.12,
        rotation=24,
        weight="bold",
    )
    fig.tight_layout()
    artifacts: dict[str, Any] = {}
    fixed_time = dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)
    for suffix in ("png", "svg", "pdf"):
        path = preview / f"candidate-preview.{suffix}"
        metadata: dict[str, Any]
        if suffix == "pdf":
            metadata = {
                "Creator": "more-sci-figure 0.2.0",
                "CreationDate": fixed_time,
                "ModDate": fixed_time,
            }
        elif suffix == "svg":
            metadata = {
                "Creator": "more-sci-figure 0.2.0",
                "Date": "2021-01-01T00:00:00+00:00",
            }
        else:
            metadata = {"Software": "more-sci-figure 0.2.0"}
        fig.savefig(path, bbox_inches="tight", metadata=metadata)
        artifacts[suffix] = {
            "path": str(path.relative_to(directory)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    plt.close(fig)
    report = {
        "schema": "more-sci-figure.candidate-preview.v1",
        "status": "pass",
        "formal_render": False,
        "review_status": "not_run",
        "rows": len(rows),
        "artifacts": artifacts,
        "warning": (
            "这些文件仅用于人工复核候选轨迹；不是正式 render/ 交付物，"
            "不得视为已接受数据。"
        ),
    }
    report_path = preview / "candidate-preview-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def write_table3_reference(directory: Path) -> Path:
    path = directory / "reference-table3.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["layer", "z_position_mm", "uct_test_a11", "uct_test_a22", "uct_test_a33"]
        )
        writer.writerows(TABLE3)
    return path


def table3_crosscheck(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["series"]].append(row)
    result: dict[str, Any] = {}
    column = {"uct_test_a11": 2, "uct_test_a22": 3, "uct_test_a33": 4}
    for series, value_index in column.items():
        comparisons = []
        candidates = grouped.get(series, [])
        for table_row in TABLE3:
            z = table_row[1]
            if not candidates:
                continue
            nearest = min(candidates, key=lambda row: abs(float(row["x"]) - z))
            if abs(float(nearest["x"]) - z) > 0.04:
                continue
            reference = table_row[value_index]
            comparisons.append(
                {
                    "z_position_mm": z,
                    "candidate_y": float(nearest["y"]),
                    "reference_y": reference,
                    "absolute_error": abs(float(nearest["y"]) - reference),
                }
            )
        result[series] = {
            "matched_points": len(comparisons),
            "mean_absolute_error": (
                float(np.mean([item["absolute_error"] for item in comparisons]))
                if comparisons
                else None
            ),
            "comparisons": comparisons,
        }
    return result


def process_figure(
    figure_id: str,
    extractor: Any,
) -> None:
    directory = ROOT / figure_id
    project_path = directory / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    source_path = directory / project["source"]["measurement_raster"]
    if sha256(source_path) != project["source"]["measurement_sha256"]:
        raise RuntimeError(f"{figure_id} 测量栅格哈希不匹配")
    with Image.open(source_path).convert("RGB") as source:
        image = np.asarray(source, dtype=np.uint8)
        rows, diagnostics = extractor(image, project)
        assign_candidate_ids(rows)
        rows.sort(key=lambda item: (item["series"], float(item["pixel_x"])))
        candidates_path = directory / "candidates.csv"
        write_candidates(candidates_path, rows)
        overlay_path = directory / "overlay.png"
        draw_overlay(source, rows, overlay_path)

    crosscheck: dict[str, Any] | None = None
    reference_path: Path | None = None
    if figure_id == "fig9":
        reference_path = write_table3_reference(directory)
        crosscheck = table3_crosscheck(rows)

    report = {
        "schema": "more-sci-figure.extraction-report.v1",
        "status": "partial",
        "numeric_output_authorized": False,
        "source": {
            "path": project["source"]["path"],
            "sha256": project["source"]["sha256"],
            "page": project["source"]["page"],
            "measurement_raster": project["source"]["measurement_raster"],
            "measurement_sha256": project["source"]["measurement_sha256"],
            "embedded_image_xref": project["source"]["embedded_image_xref"],
            "width": image.shape[1],
            "height": image.shape[0],
        },
        "chart_type": "line",
        "plot_box": project["chart"]["plot_box"],
        "calibration": {
            "x_axis": MSF.AxisMap(project["chart"]["x_axis"]).report(),
            "y_axis": MSF.AxisMap(project["chart"]["y_axis"]).report(),
        },
        "rows": len(rows),
        "diagnostics": diagnostics,
        "quality_gates": {
            "status": "partial",
            "checks": [
                {
                    "name": "candidate_rows",
                    "status": "pass" if rows else "failed",
                    "observed": len(rows),
                    "threshold": ">0",
                },
                {
                    "name": "series_coverage",
                    "status": "partial",
                    "observed": "仅恢复可分离的可见轨迹段",
                    "threshold": "人工逐系列复核",
                },
            ],
        },
        "review_status": "not_run",
        "reference_crosscheck": crosscheck,
        "limitations": diagnostics["limitations"],
        "required_next": (
            "打开 review.html，在原尺寸 overlay.png 上逐项复核；"
            "只有绑定 candidates.csv 哈希的接受项才能生成正式 data.csv。"
        ),
    }
    extraction_report_path = directory / "extraction-report.json"
    extraction_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    preview_report = render_candidate_preview(directory, project, rows)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "extraction_status": "partial",
            "review_status": "not_run",
            "render_status": "not_run",
            "delivery_status": "not_run",
            "note": (
                "已生成图像候选与未复核预览；正式数据和正式重绘仍受人工复核门控。"
            ),
        }
    )
    manifest["artifacts"].update(
        {
            "project_spec": artifact(project_path),
            "candidates": artifact(candidates_path),
            "overlay": artifact(overlay_path),
            "extraction_report": artifact(extraction_report_path),
        }
    )
    if reference_path is not None:
        manifest["artifacts"]["reference_table3"] = artifact(reference_path)
    for suffix, entry in preview_report["artifacts"].items():
        path = directory / entry["path"]
        manifest["artifacts"][f"candidate_preview_{suffix}"] = artifact(path)
    preview_report_path = directory / "preview" / "candidate-preview-report.json"
    manifest["artifacts"]["candidate_preview_report"] = artifact(
        preview_report_path
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MSF.review_command(directory)


def main() -> None:
    process_figure("fig7", extract_fig7)
    process_figure("fig9", extract_fig9)


if __name__ == "__main__":
    main()
