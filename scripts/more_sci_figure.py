#!/usr/bin/env python3
"""more-sci-figure v0.2 统一中文本地命令行。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from collections import deque
from html import escape
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw


SCHEMA = "more-sci-figure.project.v1"
MANIFEST_SCHEMA = "more-sci-figure.manifest.v1"
REVIEW_SCHEMA = "more-sci-figure.review-decisions.v1"
SUPPORTED_CHARTS = {"line", "scatter", "bar", "histogram"}
VERSION = "0.2.0"


class FigureError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_from(base_file: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_file.parent / path).resolve()


def parse_hex_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise FigureError(f"颜色必须采用 #RRGGBB 格式：{value}")
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise FigureError(f"颜色值无效：{value}") from exc


def source_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FigureError(f"找不到来源文件：{path}")
    suffix = path.suffix.lower()
    result: dict[str, Any] = {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "suffix": suffix,
    }
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        with Image.open(path) as image:
            result.update(
                {
                    "kind": "raster",
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                }
            )
    elif suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise FigureError("检查 PDF 需要安装 PyMuPDF") from exc
        with fitz.open(path) as document:
            result.update(
                {
                    "kind": "pdf",
                    "pages": document.page_count,
                    "page_sizes_points": [
                        [float(page.rect.width), float(page.rect.height)] for page in document
                    ],
                }
            )
    elif suffix in {".csv", ".tsv", ".json", ".xlsx", ".xlsm"}:
        result["kind"] = "data"
    else:
        result["kind"] = "unknown"
    return result


def render_pdf_page(path: Path, page_number: int, output: Path, dpi: int = 144) -> dict[str, Any]:
    try:
        import fitz
    except ImportError as exc:
        raise FigureError("渲染 PDF 页面需要安装 PyMuPDF") from exc
    with fitz.open(path) as document:
        if page_number < 1 or page_number > document.page_count:
            raise FigureError(f"PDF 页码必须位于 1 到 {document.page_count} 之间")
        page = document[page_number - 1]
        scale = dpi / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(output)
    with Image.open(output) as image:
        return {
            "path": str(output),
            "sha256": sha256_file(output),
            "width": image.width,
            "height": image.height,
            "dpi": dpi,
            "page": page_number,
        }


def inspect_command(input_path: Path, chart_type: str | None, out_dir: Path, page: int) -> None:
    input_path = input_path.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = source_metadata(input_path)
    report: dict[str, Any] = {
        "schema": "more-sci-figure.source-report.v1",
        "tool_version": VERSION,
        "source": metadata,
        "chart_type_proposal": chart_type,
        "numeric_extraction_authorized": False,
        "required_next": ["确认图表类型", "确认绘图区", "确认坐标轴锚点"],
        "说明": "检查阶段不会授权数值提取；请先完成人工确认。",
    }
    measurement: dict[str, Any] | None = None
    if metadata["kind"] == "pdf":
        measurement = render_pdf_page(input_path, page, out_dir / "source-page.png")
        report["measurement_raster"] = measurement
    elif metadata["kind"] == "raster":
        measurement = {
            "path": str(input_path),
            "sha256": metadata["sha256"],
            "width": metadata["width"],
            "height": metadata["height"],
        }
        report["measurement_raster"] = measurement
    write_json(out_dir / "source-report.json", report)

    relative_source = os.path.relpath(input_path, out_dir.resolve())
    project = {
        "schema": SCHEMA,
        "project_id": input_path.stem,
        "source": {
            "path": relative_source,
            "sha256": metadata["sha256"],
            "page": page if metadata["kind"] == "pdf" else None,
            "measurement_raster": (
                os.path.relpath(out_dir / "source-page.png", out_dir)
                if metadata["kind"] == "pdf"
                else relative_source
            ),
            "measurement_sha256": measurement["sha256"] if measurement else None,
        },
        "chart": {
            "type": chart_type or "unknown",
            "plot_box": [0, 0, 0, 0],
            "x_axis": {
                "scale": "linear",
                "anchors": [{"pixel": 0, "value": 0}, {"pixel": 0, "value": 1}],
            },
            "y_axis": {
                "scale": "linear",
                "anchors": [{"pixel": 0, "value": 0}, {"pixel": 0, "value": 1}],
            },
            "series": [
                {
                    "id": "series-a",
                    "color": "#d62728",
                    "color_space": "lab",
                    "tolerance": 12,
                    "min_area": 4,
                    "max_area": 500,
                    "min_fill_ratio": 0.25,
                    "max_aspect_ratio": 4.0,
                    "min_rectangularity": 0.8,
                    "baseline_tolerance": 3.0,
                }
            ],
        },
        "quality_gates": {
            "calibration": {
                "max_normalized_rmse": None,
                "require_three_anchors": False
            },
            "line": {
                "min_coverage": 0.5,
                "max_gap_fraction": None
            },
            "scatter": {
                "min_accepted_components": 1,
                "max_rejected_ratio": None
            },
            "bar": {
                "min_accepted_components": 1,
                "max_rejected_ratio": None
            }
        },
        "render": {
            "plot_type": chart_type or "line",
            "x": "x",
            "y": "y",
            "group": "series",
            "x_label": "",
            "y_label": "",
            "title": "",
        },
    }
    write_json(out_dir / "project.json", project)
    print(
        json.dumps(
            {
                "status": "pass",
                "说明": "已锁定来源并生成项目模板，尚未授权数值提取。",
                "report": str(out_dir / "source-report.json"),
                "spec": str(out_dir / "project.json"),
            },
            ensure_ascii=False,
        )
    )


def validate_spec(spec: dict[str, Any], spec_path: Path, *, extraction: bool = True) -> list[str]:
    errors: list[str] = []
    if spec.get("schema") != SCHEMA:
        errors.append(f"schema 必须是 {SCHEMA}")
    source = spec.get("source")
    if not isinstance(source, dict) or not source.get("path"):
        errors.append("必须填写 source.path")
    else:
        path = resolve_from(spec_path, str(source["path"]))
        if not path.is_file():
            errors.append(f"找不到来源文件：{path}")
        elif source.get("sha256") != sha256_file(path):
            errors.append("source.sha256 与当前来源文件不一致")
    chart = spec.get("chart")
    if not isinstance(chart, dict):
        errors.append("必须提供 chart 对象")
        return errors
    chart_type = chart.get("type")
    if extraction and chart_type not in SUPPORTED_CHARTS:
        errors.append(f"不支持的 chart.type：{chart_type}")
    box = chart.get("plot_box")
    if extraction and (
        not isinstance(box, list)
        or len(box) != 4
        or not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in box
        )
        or box[2] <= box[0]
        or box[3] <= box[1]
    ):
        errors.append("chart.plot_box 必须是具有正面积的 [left, top, right, bottom]")
    if extraction:
        for axis_name in ("x_axis", "y_axis"):
            axis = chart.get(axis_name)
            anchors = axis.get("anchors") if isinstance(axis, dict) else None
            if not isinstance(anchors, list) or len(anchors) < 2:
                errors.append(f"chart.{axis_name} 至少需要两个锚点")
                continue
            pixels = [anchor.get("pixel") for anchor in anchors if isinstance(anchor, dict)]
            values = [anchor.get("value") for anchor in anchors if isinstance(anchor, dict)]
            numeric_pixels = [
                float(pixel)
                for pixel in pixels
                if isinstance(pixel, (int, float)) and math.isfinite(float(pixel))
            ]
            if len(numeric_pixels) != len(pixels):
                errors.append(f"chart.{axis_name} 的锚点像素必须是有限数值")
            elif len(set(numeric_pixels)) < 2:
                errors.append(f"chart.{axis_name} 的锚点像素位置必须不同")
            if any(not isinstance(value, (int, float)) for value in values):
                errors.append(f"chart.{axis_name} 的锚点值必须是有限数值")
            numeric_values = [
                float(value)
                for value in values
                if isinstance(value, (int, float)) and math.isfinite(float(value))
            ]
            if len(numeric_values) != len(values):
                errors.append(f"chart.{axis_name} 的锚点值不能包含 NaN 或无穷值")
            elif len(set(numeric_values)) < 2:
                errors.append(f"chart.{axis_name} 的锚点数值必须至少包含两个不同值")
            if axis.get("scale", "linear") == "log10" and any(value <= 0 for value in values if isinstance(value, (int, float))):
                errors.append(f"chart.{axis_name} 的 log10 锚点必须为正数")
            if isinstance(axis, dict) and axis.get("scale", "linear") not in {"linear", "log10"}:
                errors.append(f"chart.{axis_name} 只支持 linear 或 log10")
        series = chart.get("series")
        if not isinstance(series, list) or not series:
            errors.append("chart.series 至少需要一个系列")
        else:
            for entry in series:
                if not isinstance(entry, dict):
                    errors.append("chart.series 中每个系列都必须是对象")
                    continue
                try:
                    parse_hex_color(str(entry.get("color", "")))
                except FigureError as exc:
                    errors.append(str(exc))
                if str(entry.get("color_space", "rgb")).lower() not in {"rgb", "lab"}:
                    errors.append(f"系列 {entry.get('id', '')} 的 color_space 只支持 rgb 或 lab")
                tolerance = entry.get("tolerance", 45)
                if not isinstance(tolerance, (int, float)) or float(tolerance) <= 0:
                    errors.append(f"系列 {entry.get('id', '')} 的 tolerance 必须为正数")

        quality = spec.get("quality_gates", {})
        if quality and not isinstance(quality, dict):
            errors.append("quality_gates 必须是对象")
        elif isinstance(quality, dict):
            calibration = quality.get("calibration", {})
            maximum_rmse = calibration.get("max_normalized_rmse") if isinstance(calibration, dict) else None
            if maximum_rmse is not None and (
                not isinstance(maximum_rmse, (int, float)) or float(maximum_rmse) < 0
            ):
                errors.append("quality_gates.calibration.max_normalized_rmse 必须为非负数或 null")
            line_gates = quality.get("line", {})
            if isinstance(line_gates, dict):
                for key in ("min_coverage", "max_gap_fraction"):
                    value = line_gates.get(key)
                    if value is not None and (
                        not isinstance(value, (int, float)) or not 0 <= float(value) <= 1
                    ):
                        errors.append(f"quality_gates.line.{key} 必须位于 0 到 1 之间或为 null")
            for section in ("scatter", "bar"):
                gates = quality.get(section, {})
                if not isinstance(gates, dict):
                    continue
                ratio = gates.get("max_rejected_ratio")
                if ratio is not None and (
                    not isinstance(ratio, (int, float)) or not 0 <= float(ratio) <= 1
                ):
                    errors.append(
                        f"quality_gates.{section}.max_rejected_ratio 必须位于 0 到 1 之间或为 null"
                    )
                minimum = gates.get("min_accepted_components")
                if minimum is not None and (
                    not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1
                ):
                    errors.append(
                        f"quality_gates.{section}.min_accepted_components 必须是正整数"
                    )
    return errors


class AxisMap:
    def __init__(self, axis: dict[str, Any]):
        self.scale = axis.get("scale", "linear")
        if self.scale not in {"linear", "log10"}:
            raise FigureError(f"不支持的坐标轴尺度：{self.scale}")
        anchors = axis["anchors"]
        self.pixels = np.asarray([float(item["pixel"]) for item in anchors], dtype=float)
        self.values = np.asarray([float(item["value"]) for item in anchors], dtype=float)
        transformed = np.log10(self.values) if self.scale == "log10" else self.values
        self.slope, self.intercept = np.polyfit(self.pixels, transformed, 1)
        if not math.isfinite(float(self.slope)) or abs(float(self.slope)) < 1e-15:
            raise FigureError("坐标轴标定斜率无效，请检查锚点")
        predicted = self.slope * self.pixels + self.intercept
        self.residuals = predicted - transformed
        self.rmse = float(np.sqrt(np.mean((predicted - transformed) ** 2)))
        transformed_span = float(np.ptp(transformed))
        self.normalized_rmse = self.rmse / transformed_span if transformed_span > 0 else math.inf
        self.rmse_evaluable = len(anchors) >= 3

    def value(self, pixel: float) -> float:
        transformed = self.slope * float(pixel) + self.intercept
        return float(10**transformed if self.scale == "log10" else transformed)

    def pixel(self, value: float) -> float:
        if self.scale == "log10" and value <= 0:
            raise FigureError("log10 坐标轴无法映射非正值")
        transformed = math.log10(value) if self.scale == "log10" else value
        return float((transformed - self.intercept) / self.slope)

    def uncertainty(self, pixel: float, pixel_half_width: float = 0.5) -> float:
        """给出像素量化与可评估标定残差共同形成的保守局部半宽。"""
        center = self.value(pixel)
        candidates = [
            abs(self.value(pixel - pixel_half_width) - center),
            abs(self.value(pixel + pixel_half_width) - center),
        ]
        if self.rmse_evaluable:
            transformed = self.slope * float(pixel) + self.intercept
            if self.scale == "log10":
                candidates.extend(
                    [
                        abs(10 ** (transformed - self.rmse) - center),
                        abs(10 ** (transformed + self.rmse) - center),
                    ]
                )
            else:
                candidates.append(self.rmse)
        return float(max(candidates, default=0.0))

    def report(self) -> dict[str, Any]:
        return {
            "scale": self.scale,
            "slope": float(self.slope),
            "intercept": float(self.intercept),
            "rmse_transformed_units": self.rmse,
            "normalized_rmse": self.normalized_rmse,
            "rmse_evaluable": self.rmse_evaluable,
            "anchor_count": int(len(self.pixels)),
            "anchor_residuals_transformed_units": [float(value) for value in self.residuals],
            "说明": (
                "至少三个锚点，可用残差辅助评估标定质量。"
                if self.rmse_evaluable
                else "仅有两个锚点，拟合残差必然接近零，不能独立证明标定准确。"
            ),
        }


def color_mask(array: np.ndarray, color: tuple[int, int, int], tolerance: float) -> np.ndarray:
    delta = array.astype(np.int32) - np.asarray(color, dtype=np.int32)
    return np.sqrt(np.sum(delta * delta, axis=2)) <= tolerance


def rgb_to_lab(array: np.ndarray) -> np.ndarray:
    """把 sRGB 数组转换为 CIE Lab，供抗压缩颜色距离使用。"""
    rgb = array.astype(np.float64) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    matrix = np.asarray(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = linear @ matrix.T
    xyz /= np.asarray([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    transformed = np.where(
        xyz > delta**3,
        np.cbrt(xyz),
        xyz / (3 * delta**2) + 4 / 29,
    )
    return np.stack(
        [
            116 * transformed[..., 1] - 16,
            500 * (transformed[..., 0] - transformed[..., 1]),
            200 * (transformed[..., 1] - transformed[..., 2]),
        ],
        axis=-1,
    )


def series_mask(array: np.ndarray, entry: dict[str, Any]) -> np.ndarray:
    color = parse_hex_color(entry["color"])
    tolerance = float(entry.get("tolerance", 45))
    if str(entry.get("color_space", "rgb")).lower() == "lab":
        target = rgb_to_lab(np.asarray(color, dtype=np.uint8).reshape(1, 1, 3))[0, 0]
        delta = rgb_to_lab(array) - target
        return np.sqrt(np.sum(delta * delta, axis=2)) <= tolerance
    return color_mask(array, color, tolerance)


def components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    found: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            queue = deque([(x, y)])
            visited[y, x] = True
            pixels: list[tuple[int, int]] = []
            while queue:
                px, py = queue.popleft()
                pixels.append((px, py))
                for ny in range(max(0, py - 1), min(height, py + 2)):
                    for nx in range(max(0, px - 1), min(width, px + 2)):
                        if mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
            found.append(pixels)
    return found


def prepare_measurement_raster(spec: dict[str, Any], spec_path: Path, out_dir: Path) -> tuple[Image.Image, Path]:
    source = spec["source"]
    source_path = resolve_from(spec_path, source["path"])
    measurement_value = source.get("measurement_raster")
    if measurement_value:
        measurement_path = resolve_from(spec_path, str(measurement_value))
    elif source_path.suffix.lower() == ".pdf":
        measurement_path = out_dir / "source-page.png"
        render_pdf_page(source_path, int(source.get("page") or 1), measurement_path)
    else:
        measurement_path = source_path
    if not measurement_path.is_file():
        raise FigureError(f"找不到测量栅格：{measurement_path}")
    expected = source.get("measurement_sha256")
    if expected and sha256_file(measurement_path) != expected:
        raise FigureError("测量栅格哈希与项目声明不一致")
    return Image.open(measurement_path).convert("RGB"), measurement_path


def extract_line(
    array: np.ndarray,
    box: tuple[int, int, int, int],
    series: list[dict[str, Any]],
    x_map: AxisMap,
    y_map: AxisMap,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    left, top, right, bottom = box
    crop = array[top : bottom + 1, left : right + 1]
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"series": []}
    for entry in series:
        mask = series_mask(crop, entry)
        supported = 0
        previous_x: int | None = None
        current_gap = 0
        maximum_gap = 0
        for local_x in range(mask.shape[1]):
            local_ys = np.flatnonzero(mask[:, local_x])
            if local_ys.size == 0:
                previous_x = None
                current_gap += 1
                maximum_gap = max(maximum_gap, current_gap)
                continue
            current_gap = 0
            pixel_x = left + local_x
            pixel_y = top + float(np.median(local_ys))
            pixel_half_height = max(0.5, float(np.ptp(local_ys)) / 2.0)
            rows.append(
                {
                    "series": entry["id"],
                    "x": x_map.value(pixel_x),
                    "y": y_map.value(pixel_y),
                    "x_uncertainty": x_map.uncertainty(pixel_x),
                    "y_uncertainty": y_map.uncertainty(pixel_y, pixel_half_height),
                    "pixel_x": pixel_x,
                    "pixel_y": pixel_y,
                    "pixel_half_height": pixel_half_height,
                    "segment_break": previous_x is None,
                    "status": "visible",
                }
            )
            supported += 1
            previous_x = pixel_x
        coverage = supported / max(1, mask.shape[1])
        diagnostics["series"].append(
            {
                "id": entry["id"],
                "supported_columns": supported,
                "coverage": coverage,
                "maximum_gap_columns": maximum_gap,
                "maximum_gap_fraction": maximum_gap / max(1, mask.shape[1]),
            }
        )
    return rows, diagnostics


def extract_scatter(
    array: np.ndarray,
    box: tuple[int, int, int, int],
    series: list[dict[str, Any]],
    x_map: AxisMap,
    y_map: AxisMap,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    left, top, right, bottom = box
    crop = array[top : bottom + 1, left : right + 1]
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"series": []}
    for entry in series:
        mask = series_mask(crop, entry)
        min_area = int(entry.get("min_area", 4))
        max_area = int(entry.get("max_area", 500))
        minimum_fill_ratio = float(entry.get("min_fill_ratio", 0.25))
        maximum_aspect_ratio = float(entry.get("max_aspect_ratio", 4.0))
        accepted = 0
        rejected = 0
        for component in components(mask):
            area = len(component)
            if area < min_area or area > max_area:
                rejected += 1
                continue
            xs = np.asarray([point[0] for point in component], dtype=float)
            ys = np.asarray([point[1] for point in component], dtype=float)
            width = float(np.ptp(xs) + 1)
            height = float(np.ptp(ys) + 1)
            fill_ratio = area / max(1.0, width * height)
            aspect_ratio = max(width, height) / max(1.0, min(width, height))
            if fill_ratio < minimum_fill_ratio or aspect_ratio > maximum_aspect_ratio:
                rejected += 1
                continue
            pixel_x = left + float(xs.mean())
            pixel_y = top + float(ys.mean())
            rows.append(
                {
                    "series": entry["id"],
                    "x": x_map.value(pixel_x),
                    "y": y_map.value(pixel_y),
                    "x_uncertainty": x_map.uncertainty(
                        pixel_x, max(0.5, float(np.ptp(xs)) / 2.0)
                    ),
                    "y_uncertainty": y_map.uncertainty(
                        pixel_y, max(0.5, float(np.ptp(ys)) / 2.0)
                    ),
                    "pixel_x": pixel_x,
                    "pixel_y": pixel_y,
                    "component_area": area,
                    "component_width": width,
                    "component_height": height,
                    "component_fill_ratio": fill_ratio,
                    "component_aspect_ratio": aspect_ratio,
                    "status": "visible_component",
                }
            )
            accepted += 1
        diagnostics["series"].append(
            {"id": entry["id"], "accepted_components": accepted, "rejected_components": rejected}
        )
    rows.sort(key=lambda row: (str(row["series"]), float(row["x"])))
    return rows, diagnostics


def extract_bars(
    array: np.ndarray,
    box: tuple[int, int, int, int],
    series: list[dict[str, Any]],
    x_map: AxisMap,
    y_map: AxisMap,
    chart: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    left, top, right, bottom = box
    crop = array[top : bottom + 1, left : right + 1]
    if "baseline_pixel" in chart:
        baseline = float(chart["baseline_pixel"])
    elif y_map.scale == "log10":
        raise FigureError("对数纵轴的柱图必须显式提供正值基线对应的 baseline_pixel")
    else:
        baseline = float(y_map.pixel(0.0))
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {"baseline_pixel": baseline, "series": []}
    candidates: list[dict[str, Any]] = []
    for entry in series:
        mask = series_mask(crop, entry)
        min_area = int(entry.get("min_area", 20))
        max_area = int(entry.get("max_area", 1000000))
        minimum_rectangularity = float(entry.get("min_rectangularity", 0.8))
        baseline_tolerance = float(entry.get("baseline_tolerance", 3.0))
        accepted = 0
        rejected = 0
        for component in components(mask):
            if len(component) < min_area or len(component) > max_area:
                rejected += 1
                continue
            xs = [point[0] for point in component]
            ys = [point[1] for point in component]
            x0, x1 = left + min(xs), left + max(xs)
            y0, y1 = top + min(ys), top + max(ys)
            if x1 - x0 < 2 or y1 - y0 < 2:
                rejected += 1
                continue
            bounding_area = (x1 - x0 + 1) * (y1 - y0 + 1)
            rectangularity = len(component) / max(1, bounding_area)
            baseline_distance = min(abs(y0 - baseline), abs(y1 - baseline))
            if rectangularity < minimum_rectangularity or baseline_distance > baseline_tolerance:
                rejected += 1
                continue
            endpoint = y0 if abs(y0 - baseline) >= abs(y1 - baseline) else y1
            candidates.append(
                {
                    "series": entry["id"],
                    "pixel_left": x0,
                    "pixel_top": y0,
                    "pixel_right": x1,
                    "pixel_bottom": y1,
                    "pixel_center": (x0 + x1) / 2.0,
                    "value": y_map.value(endpoint),
                    "value_uncertainty": y_map.uncertainty(endpoint),
                    "baseline_value": y_map.value(baseline),
                    "x_uncertainty": x_map.uncertainty(center := (x0 + x1) / 2.0, (x1 - x0 + 1) / 2.0),
                    "rectangularity": rectangularity,
                    "baseline_distance_pixels": baseline_distance,
                    "status": "visible_rectangle",
                }
            )
            accepted += 1
        diagnostics["series"].append(
            {"id": entry["id"], "accepted_components": accepted, "rejected_components": rejected}
        )
    candidates.sort(key=lambda row: float(row["pixel_center"]))
    centers: list[float] = []
    for candidate in candidates:
        center = float(candidate["pixel_center"])
        category = next((index for index, known in enumerate(centers) if abs(known - center) <= 3), None)
        if category is None:
            centers.append(center)
            category = len(centers) - 1
        candidate["category_index"] = category
        candidate["x_value"] = x_map.value(center)
        rows.append(candidate)
    return rows, diagnostics


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def draw_overlay(image: Image.Image, chart_type: str, rows: list[dict[str, Any]], output: Path) -> None:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    if chart_type == "line":
        grouped: dict[str, list[tuple[float, float]]] = {}
        for row in rows:
            grouped.setdefault(str(row["series"]), []).append((float(row["pixel_x"]), float(row["pixel_y"])))
        for points in grouped.values():
            for point in points:
                draw.ellipse((point[0] - 1.5, point[1] - 1.5, point[0] + 1.5, point[1] + 1.5), outline="#ff00ff")
    elif chart_type == "scatter":
        for row in rows:
            x, y = float(row["pixel_x"]), float(row["pixel_y"])
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), outline="#ff00ff", width=2)
    else:
        for row in rows:
            draw.rectangle(
                (
                    float(row["pixel_left"]),
                    float(row["pixel_top"]),
                    float(row["pixel_right"]),
                    float(row["pixel_bottom"]),
                ),
                outline="#ff00ff",
                width=2,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output)


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if path.exists():
        return read_json(path)
    return {
        "schema": MANIFEST_SCHEMA,
        "tool_version": VERSION,
        "extraction_status": "not_run",
        "review_status": "not_run",
        "render_status": "not_run",
        "delivery_status": "not_run",
        "artifacts": {},
    }


def artifact_entry(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def assign_candidate_ids(chart_type: str, rows: list[dict[str, Any]]) -> None:
    counters: dict[str, int] = {}
    for row in rows:
        series = str(row.get("series", "series"))
        counters[series] = counters.get(series, 0) + 1
        safe_series = "".join(character if character.isalnum() else "-" for character in series)
        row["candidate_id"] = f"{chart_type}-{safe_series}-{counters[series]:06d}"


def evaluate_quality_gates(
    spec: dict[str, Any],
    chart_type: str,
    rows: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    x_map: AxisMap,
    y_map: AxisMap,
) -> dict[str, Any]:
    configured = spec.get("quality_gates", {})
    checks: list[dict[str, Any]] = []

    calibration = configured.get("calibration", {})
    require_three = bool(calibration.get("require_three_anchors", False))
    maximum_rmse = calibration.get("max_normalized_rmse")
    for axis_name, mapping in (("x_axis", x_map), ("y_axis", y_map)):
        if require_three:
            checks.append(
                {
                    "name": f"{axis_name}.anchor_count",
                    "status": "pass" if mapping.rmse_evaluable else "failed",
                    "observed": len(mapping.pixels),
                    "threshold": ">=3",
                }
            )
        if maximum_rmse is not None:
            checks.append(
                {
                    "name": f"{axis_name}.normalized_rmse",
                    "status": (
                        "pass"
                        if mapping.rmse_evaluable
                        and mapping.normalized_rmse <= float(maximum_rmse)
                        else "failed"
                    ),
                    "observed": mapping.normalized_rmse,
                    "threshold": f"<={float(maximum_rmse)}",
                    "evaluable": mapping.rmse_evaluable,
                }
            )

    chart_gates = configured.get("bar" if chart_type == "histogram" else chart_type, {})
    if chart_type == "line":
        minimum_coverage = float(chart_gates.get("min_coverage", 0.5))
        maximum_gap = chart_gates.get("max_gap_fraction")
        for series in diagnostics["series"]:
            checks.append(
                {
                    "name": f"{series['id']}.coverage",
                    "status": "pass" if float(series["coverage"]) >= minimum_coverage else "failed",
                    "observed": float(series["coverage"]),
                    "threshold": f">={minimum_coverage}",
                }
            )
            if maximum_gap is not None:
                checks.append(
                    {
                        "name": f"{series['id']}.maximum_gap_fraction",
                        "status": (
                            "pass"
                            if float(series["maximum_gap_fraction"]) <= float(maximum_gap)
                            else "failed"
                        ),
                        "observed": float(series["maximum_gap_fraction"]),
                        "threshold": f"<={float(maximum_gap)}",
                    }
                )
    else:
        minimum_components = int(chart_gates.get("min_accepted_components", 1))
        maximum_rejected_ratio = chart_gates.get("max_rejected_ratio")
        for series in diagnostics["series"]:
            accepted = int(series["accepted_components"])
            rejected = int(series["rejected_components"])
            checks.append(
                {
                    "name": f"{series['id']}.accepted_components",
                    "status": "pass" if accepted >= minimum_components else "failed",
                    "observed": accepted,
                    "threshold": f">={minimum_components}",
                }
            )
            if maximum_rejected_ratio is not None:
                ratio = rejected / max(1, accepted + rejected)
                checks.append(
                    {
                        "name": f"{series['id']}.rejected_ratio",
                        "status": "pass" if ratio <= float(maximum_rejected_ratio) else "failed",
                        "observed": ratio,
                        "threshold": f"<={float(maximum_rejected_ratio)}",
                    }
                )

    failed = [check for check in checks if check["status"] == "failed"]
    if not rows:
        status = "failed"
    elif failed:
        status = "partial"
    else:
        status = "pass"
    return {
        "status": status,
        "checks": checks,
        "说明": "质量门槛只用于筛查风险，不能替代人工语义复核。",
    }


def extract_command(spec_path: Path, out_dir: Path) -> dict[str, Any]:
    spec_path = spec_path.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = read_json(spec_path)
    errors = validate_spec(spec, spec_path, extraction=True)
    if errors:
        report = {
            "schema": "more-sci-figure.extraction-report.v1",
            "status": "failed",
            "numeric_output_authorized": False,
            "errors": errors,
        }
        write_json(out_dir / "extraction-report.json", report)
        raise FigureError("；".join(errors))

    image, measurement_path = prepare_measurement_raster(spec, spec_path, out_dir)
    array = np.asarray(image, dtype=np.uint8)
    box = tuple(int(round(value)) for value in spec["chart"]["plot_box"])
    left, top, right, bottom = box
    if left < 0 or top < 0 or right >= image.width or bottom >= image.height:
        raise FigureError("chart.plot_box 超出测量栅格范围")
    x_map = AxisMap(spec["chart"]["x_axis"])
    y_map = AxisMap(spec["chart"]["y_axis"])
    chart_type = spec["chart"]["type"]
    extractors: dict[str, Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]]] = {
        "line": extract_line,
        "scatter": extract_scatter,
    }
    if chart_type in extractors:
        rows, diagnostics = extractors[chart_type](
            array, box, spec["chart"]["series"], x_map, y_map
        )
    else:
        rows, diagnostics = extract_bars(
            array, box, spec["chart"]["series"], x_map, y_map, spec["chart"]
        )
    assign_candidate_ids(chart_type, rows)
    quality = evaluate_quality_gates(spec, chart_type, rows, diagnostics, x_map, y_map)
    status = quality["status"]
    candidates_path = out_dir / "candidates.csv"
    overlay_path = out_dir / "overlay.png"
    write_csv(candidates_path, rows)
    draw_overlay(image, chart_type, rows, overlay_path)
    report = {
        "schema": "more-sci-figure.extraction-report.v1",
        "status": status,
        "numeric_output_authorized": False,
        "source": {
            "path": str(resolve_from(spec_path, spec["source"]["path"])),
            "sha256": spec["source"]["sha256"],
            "measurement_raster": str(measurement_path),
            "measurement_sha256": sha256_file(measurement_path),
            "width": image.width,
            "height": image.height,
        },
        "chart_type": chart_type,
        "plot_box": list(box),
        "calibration": {"x_axis": x_map.report(), "y_axis": y_map.report()},
        "rows": len(rows),
        "diagnostics": diagnostics,
        "quality_gates": quality,
        "review_status": "not_run",
        "limitations": "仅包含有颜色像素证据的可见标记；不会推断隐藏、粘连或遮挡数据。",
        "required_next": "生成并完成人工复核后，才能创建正式 data.csv。",
    }
    report_path = out_dir / "extraction-report.json"
    write_json(report_path, report)
    project_copy = out_dir / "project.json"
    if project_copy.resolve() != spec_path:
        write_json(project_copy, spec)
    manifest = load_manifest(out_dir)
    manifest.update(
        {
            "project_id": spec.get("project_id"),
            "project_spec": artifact_entry(project_copy if project_copy.exists() else spec_path),
            "source_sha256": spec["source"]["sha256"],
            "extraction_status": status,
            "review_status": "not_run",
            "tool_version": VERSION,
        }
    )
    manifest["artifacts"].update(
        {
            "project_spec": artifact_entry(project_copy if project_copy.exists() else spec_path),
            "candidates": artifact_entry(candidates_path),
            "overlay": artifact_entry(overlay_path),
            "extraction_report": artifact_entry(report_path),
        }
    )
    source_report = out_dir / "source-report.json"
    if source_report.is_file():
        manifest["artifacts"]["source_report"] = artifact_entry(source_report)
    write_json(out_dir / "manifest.json", manifest)
    if rows:
        review_command(out_dir)
    return report


def review_command(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.expanduser().resolve()
    candidates_path = project_dir / "candidates.csv"
    overlay_path = project_dir / "overlay.png"
    if not candidates_path.is_file() or not overlay_path.is_file():
        raise FigureError("缺少 candidates.csv 或 overlay.png，请先运行 extract")
    rows = read_tabular_rows(candidates_path)
    if not rows:
        raise FigureError("没有可供复核的候选值")
    candidate_hash = sha256_file(candidates_path)
    template = {
        "schema": REVIEW_SCHEMA,
        "candidate_sha256": candidate_hash,
        "reviewed_by": "",
        "reviewed_at": "",
        "decisions": [
            {
                "candidate_id": str(row["candidate_id"]),
                "decision": "accepted",
                "reason": "",
            }
            for row in rows
        ],
    }
    template_path = project_dir / "review-template.json"
    write_json(template_path, template)

    table_rows: list[str] = []
    for row in rows:
        candidate_id = escape(str(row["candidate_id"]))
        series = escape(str(row.get("series", "")))
        x_value = escape(str(row.get("x", row.get("x_value", row.get("category_index", "")))))
        y_value = escape(str(row.get("y", row.get("value", ""))))
        table_rows.append(
            "<tr>"
            f"<td><code>{candidate_id}</code></td>"
            f"<td>{series}</td><td>{x_value}</td><td>{y_value}</td>"
            f"<td><select data-decision='{candidate_id}'>"
            "<option value='accepted'>接受</option>"
            "<option value='rejected'>拒绝</option>"
            "</select></td>"
            f"<td><input data-reason='{candidate_id}' placeholder='必要时填写理由'></td>"
            "</tr>"
        )
    payload = json.dumps(
        {"schema": REVIEW_SCHEMA, "candidate_sha256": candidate_hash},
        ensure_ascii=False,
    )
    html = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>more-sci-figure 候选数据复核</title>
<style>
:root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
body { margin: 0 auto; max-width: 1440px; padding: 24px; color: #17202a; background: #f6f8fa; }
h1 { margin-bottom: 8px; } .note { padding: 12px 16px; background: #fff8c5; border-left: 4px solid #d4a72c; }
.layout { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(560px, 1.2fr); gap: 20px; margin-top: 20px; }
.panel { background: white; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; overflow: auto; }
img { max-width: none; image-rendering: auto; } table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { border-bottom: 1px solid #d8dee4; padding: 8px; text-align: left; }
th { position: sticky; top: 0; background: #f6f8fa; } input, select { width: 100%; box-sizing: border-box; padding: 6px; }
button { margin-top: 12px; padding: 9px 16px; border: 0; border-radius: 6px; background: #0969da; color: white; cursor: pointer; }
@media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>候选数据人工复核</h1>
<p class="note">请按原始尺寸查看叠图。接受表示该候选确实对应可见图形标记；不要根据期望值或期望数量调节判断。</p>
<label>复核人或复核记录：<input id="reviewed-by" placeholder="必填，例如：张三 / 项目组联合复核"></label>
<div class="layout">
  <section class="panel"><h2>原尺寸证据叠图</h2><img src="overlay.png" alt="候选值证据叠图"></section>
  <section class="panel">
    <h2>逐项决策</h2>
    <table><thead><tr><th>候选编号</th><th>系列</th><th>X</th><th>Y/值</th><th>决策</th><th>理由</th></tr></thead>
    <tbody>__TABLE_ROWS__</tbody></table>
    <button id="export">导出 review-decisions.json</button>
  </section>
</div>
<script>
const base = __PAYLOAD__;
document.getElementById("export").addEventListener("click", () => {
  const reviewedBy = document.getElementById("reviewed-by").value.trim();
  if (!reviewedBy) { alert("请先填写复核人或复核记录。"); return; }
  const decisions = [...document.querySelectorAll("[data-decision]")].map(select => {
    const candidateId = select.dataset.decision;
    const reason = document.querySelector(`[data-reason="${candidateId}"]`).value.trim();
    return { candidate_id: candidateId, decision: select.value, reason };
  });
  const output = {...base, reviewed_by: reviewedBy, reviewed_at: new Date().toISOString(), decisions};
  const blob = new Blob([JSON.stringify(output, null, 2) + "\\n"], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "review-decisions.json";
  link.click();
  URL.revokeObjectURL(link.href);
});
</script>
</body>
</html>
"""
    html = html.replace("__TABLE_ROWS__", "\n".join(table_rows)).replace("__PAYLOAD__", payload)
    html_path = project_dir / "review.html"
    html_path.write_text(html, encoding="utf-8")
    manifest = load_manifest(project_dir)
    manifest["artifacts"]["review_html"] = artifact_entry(html_path)
    manifest["artifacts"]["review_template"] = artifact_entry(template_path)
    write_json(project_dir / "manifest.json", manifest)
    return {
        "status": "pass",
        "review_status": manifest.get("review_status", "not_run"),
        "候选数量": len(rows),
        "复核页面": str(html_path),
        "复核模板": str(template_path),
        "下一步": "在浏览器中打开 review.html，导出决策文件后运行 review-apply。",
    }


def review_apply_command(project_dir: Path, decisions_path: Path) -> dict[str, Any]:
    project_dir = project_dir.expanduser().resolve()
    decisions_path = decisions_path.expanduser().resolve()
    candidates_path = project_dir / "candidates.csv"
    if not candidates_path.is_file():
        raise FigureError("缺少 candidates.csv，请先运行 extract")
    payload = read_json(decisions_path)
    if payload.get("schema") != REVIEW_SCHEMA:
        raise FigureError(f"复核文件 schema 必须是 {REVIEW_SCHEMA}")
    if payload.get("candidate_sha256") != sha256_file(candidates_path):
        raise FigureError("复核文件绑定的候选数据哈希与当前 candidates.csv 不一致")
    reviewed_by = str(payload.get("reviewed_by", "")).strip()
    if not reviewed_by:
        raise FigureError("复核文件必须填写 reviewed_by")
    rows = read_tabular_rows(candidates_path)
    row_by_id = {str(row["candidate_id"]): row for row in rows}
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise FigureError("复核文件的 decisions 必须是数组")
    decision_by_id: dict[str, dict[str, Any]] = {}
    for item in decisions:
        if not isinstance(item, dict):
            raise FigureError("每条复核决定必须是对象")
        candidate_id = str(item.get("candidate_id", ""))
        decision = item.get("decision")
        if candidate_id not in row_by_id:
            raise FigureError(f"复核文件包含未知候选编号：{candidate_id}")
        if candidate_id in decision_by_id:
            raise FigureError(f"复核文件重复包含候选编号：{candidate_id}")
        if decision not in {"accepted", "rejected"}:
            raise FigureError(f"{candidate_id} 的 decision 必须是 accepted 或 rejected")
        decision_by_id[candidate_id] = item
    missing = sorted(set(row_by_id) - set(decision_by_id))
    if missing:
        raise FigureError(f"复核文件未覆盖全部候选值，缺少 {len(missing)} 项")

    accepted_rows: list[dict[str, Any]] = []
    for candidate_id, row in row_by_id.items():
        decision = decision_by_id[candidate_id]
        if decision["decision"] == "accepted":
            accepted = dict(row)
            accepted["reviewed_by"] = reviewed_by
            accepted["review_decision"] = "accepted"
            accepted_rows.append(accepted)
    accepted_count = len(accepted_rows)
    rejected_count = len(rows) - accepted_count
    if accepted_count == 0:
        review_status = "rejected"
    elif rejected_count == 0:
        review_status = "accepted"
    else:
        review_status = "partial"

    normalized = {
        "schema": REVIEW_SCHEMA,
        "candidate_sha256": sha256_file(candidates_path),
        "reviewed_by": reviewed_by,
        "reviewed_at": payload.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
        "summary": {
            "total": len(rows),
            "accepted": accepted_count,
            "rejected": rejected_count,
            "review_status": review_status,
        },
    }
    applied_path = project_dir / "review-decisions.json"
    write_json(applied_path, normalized)
    data_path = project_dir / "data.csv"
    write_csv(data_path, accepted_rows)

    report_path = project_dir / "extraction-report.json"
    report = read_json(report_path)
    report["review_status"] = review_status
    report["numeric_output_authorized"] = accepted_count > 0
    report["review_summary"] = normalized["summary"]
    write_json(report_path, report)

    manifest = load_manifest(project_dir)
    manifest["review_status"] = review_status
    manifest["artifacts"]["review_decisions"] = artifact_entry(applied_path)
    manifest["artifacts"]["data"] = artifact_entry(data_path)
    manifest["artifacts"]["extraction_report"] = artifact_entry(report_path)
    write_json(project_dir / "manifest.json", manifest)
    return {
        "status": "pass" if accepted_count else "failed",
        "review_status": review_status,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "data": str(data_path),
    }


def read_tabular_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ","))
    if suffix == ".json":
        payload = read_json(path)
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise FigureError("JSON 数据必须是对象列表，或包含 rows 列表的对象")
        return rows
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise FigureError("读取 Excel 需要安装 openpyxl") from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
        workbook.close()
        if not values:
            return []
        headers = [str(value) for value in values[0]]
        return [dict(zip(headers, row, strict=False)) for row in values[1:]]
    raise FigureError(f"不支持的数据格式：{suffix}")


def numeric(row: dict[str, Any], key: str) -> float:
    try:
        value = float(row[key])
        if not math.isfinite(value):
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError) as exc:
        raise FigureError(f"列 {key!r} 必须包含有限数值") from exc


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def series_colors(spec: dict[str, Any]) -> dict[str, str]:
    return {str(item["id"]): str(item["color"]) for item in spec.get("chart", {}).get("series", [])}


def render_command(spec_path: Path, data_path: Path, out_dir: Path) -> dict[str, Any]:
    cache_root = Path(os.environ.get("TMPDIR", "/tmp")) / "more-sci-figure-mpl"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root))
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Hiragino Sans GB",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt

    spec_path = spec_path.expanduser().resolve()
    data_path = data_path.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = read_json(spec_path)
    errors = validate_spec(spec, spec_path, extraction=False)
    if errors:
        raise FigureError("；".join(errors))
    rows = read_tabular_rows(data_path)
    if not rows:
        raise FigureError("没有可用于重绘的数据行")
    render = spec.get("render", {})
    plot_type = render.get("plot_type") or spec.get("chart", {}).get("type")
    if plot_type not in SUPPORTED_CHARTS:
        raise FigureError(f"不支持的重绘类型：{plot_type}")
    x_key = str(render.get("x", "x" if plot_type in {"line", "scatter"} else "category_index"))
    y_key = str(render.get("y", "y" if plot_type in {"line", "scatter"} else "value"))
    group_key = render.get("group")
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = str(row.get(str(group_key), "series")) if group_key else "series"
        groups.setdefault(group, []).append(row)
    colors = series_colors(spec)
    fig, axis = plt.subplots(figsize=(7.2, 4.8), dpi=160, constrained_layout=True)
    fallback = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    rendered_segments: dict[str, int] = {}
    if plot_type in {"line", "scatter"}:
        for index, (group, group_rows) in enumerate(groups.items()):
            color = colors.get(group, fallback[index % len(fallback)])
            if plot_type == "line":
                segments: list[list[dict[str, Any]]] = []
                current: list[dict[str, Any]] = []
                for row in group_rows:
                    if current and truthy(row.get("segment_break", False)):
                        segments.append(current)
                        current = []
                    current.append(row)
                if current:
                    segments.append(current)
                rendered_segments[group] = len(segments)
                for segment_index, segment in enumerate(segments):
                    axis.plot(
                        [numeric(row, x_key) for row in segment],
                        [numeric(row, y_key) for row in segment],
                        color=color,
                        linewidth=1.8,
                        label=group if segment_index == 0 else None,
                    )
            else:
                xs = [numeric(row, x_key) for row in group_rows]
                ys = [numeric(row, y_key) for row in group_rows]
                axis.scatter(xs, ys, color=color, s=24, label=group)
    else:
        category_values = sorted({numeric(row, x_key) for row in rows})
        group_count = len(groups)
        width = 0.8 / max(1, group_count)
        for index, (group, group_rows) in enumerate(groups.items()):
            mapping = {numeric(row, x_key): numeric(row, y_key) for row in group_rows}
            positions = np.asarray(category_values) - 0.4 + width / 2 + index * width
            heights = [mapping.get(category, np.nan) for category in category_values]
            axis.bar(
                positions,
                heights,
                width=width,
                color=colors.get(group, fallback[index % len(fallback)]),
                label=group,
            )
        axis.set_xticks(category_values)
    chart = spec.get("chart", {})
    x_scale = str(render.get("x_scale") or chart.get("x_axis", {}).get("scale", "linear"))
    y_scale = str(render.get("y_scale") or chart.get("y_axis", {}).get("scale", "linear"))
    axis.set_xscale("log" if x_scale == "log10" else "linear")
    axis.set_yscale("log" if y_scale == "log10" else "linear")
    axis.set_xlabel(str(render.get("x_label", "")))
    axis.set_ylabel(str(render.get("y_label", "")))
    axis.set_title(str(render.get("title", "")))
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.6, alpha=0.6)
    if len(groups) > 1 or (group_key and next(iter(groups)) != "series"):
        axis.legend(frameon=False)
    outputs: dict[str, dict[str, Any]] = {}
    for suffix in ("png", "svg", "pdf"):
        path = out_dir / f"render.{suffix}"
        fig.savefig(path, facecolor="white")
        outputs[suffix] = artifact_entry(path)
    plt.close(fig)
    report = {
        "schema": "more-sci-figure.render-report.v1",
        "status": "pass",
        "plot_type": plot_type,
        "rows": len(rows),
        "mapping": {"x": x_key, "y": y_key, "group": group_key},
        "axis_scales": {"x": x_scale, "y": y_scale},
        "rendered_segments": rendered_segments,
        "outputs": outputs,
    }
    write_json(out_dir / "render-report.json", report)
    root = out_dir.parent if out_dir.name == "render" else out_dir
    manifest = load_manifest(root)
    if manifest.get("extraction_status") == "not_run":
        canonical_data = root / "data.csv"
        write_csv(canonical_data, rows)
        project_copy = root / "project.json"
        if project_copy.resolve() != spec_path:
            write_json(project_copy, spec)
        manifest["extraction_status"] = "not_applicable"
        manifest["review_status"] = "not_applicable"
        manifest["data_origin"] = "supplied"
        manifest["artifacts"]["supplied_data"] = artifact_entry(data_path)
        manifest["artifacts"]["data"] = artifact_entry(canonical_data)
        manifest["project_spec"] = artifact_entry(project_copy if project_copy.exists() else spec_path)
        manifest["artifacts"]["project_spec"] = artifact_entry(
            project_copy if project_copy.exists() else spec_path
        )
    manifest["render_status"] = "pass"
    manifest["tool_version"] = VERSION
    manifest["artifacts"]["render_report"] = artifact_entry(out_dir / "render-report.json")
    for suffix, entry in outputs.items():
        manifest["artifacts"][f"render_{suffix}"] = entry
    write_json(root / "manifest.json", manifest)
    return report


def validate_command(project_dir: Path, reference: Path | None = None) -> dict[str, Any]:
    project_dir = project_dir.expanduser().resolve()
    manifest_path = project_dir / "manifest.json"
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest_path.exists():
        raise FigureError(f"找不到 manifest.json：{manifest_path}")
    manifest = read_json(manifest_path)
    required = {
        "project_spec": project_dir / "project.json",
        "data": project_dir / "data.csv",
        "render_png": project_dir / "render" / "render.png",
        "render_svg": project_dir / "render" / "render.svg",
        "render_pdf": project_dir / "render" / "render.pdf",
    }
    if manifest.get("extraction_status") != "not_applicable":
        required.update(
            {
                "candidates": project_dir / "candidates.csv",
                "overlay": project_dir / "overlay.png",
                "extraction_report": project_dir / "extraction-report.json",
                "review_decisions": project_dir / "review-decisions.json",
            }
        )
    project_path = required["project_spec"]
    if project_path.is_file():
        project_errors = validate_spec(read_json(project_path), project_path, extraction=False)
        errors.extend(f"项目规格验证失败：{error}" for error in project_errors)
    artifact_checks: dict[str, Any] = {}
    for name, path in required.items():
        exists = path.is_file()
        artifact_checks[name] = {"path": str(path), "exists": exists}
        if not exists:
            errors.append(f"缺少交付物：{name}")
            continue
        recorded = manifest.get("artifacts", {}).get(name, {}).get("sha256")
        current = sha256_file(path)
        artifact_checks[name]["sha256"] = current
        if not recorded:
            errors.append(f"清单未记录交付物哈希：{name}")
        elif recorded != current:
            errors.append(f"交付物哈希不一致：{name}")
    visual: dict[str, Any] = {"status": "not_run"}
    if reference is not None:
        reference = reference.expanduser().resolve()
        render_path = required["render_png"]
        if reference.is_file() and render_path.is_file():
            with Image.open(reference).convert("RGB") as ref_image, Image.open(render_path).convert("RGB") as rendered:
                if ref_image.size != rendered.size:
                    visual = {
                        "status": "canvas_mismatch",
                        "reference_size": list(ref_image.size),
                        "render_size": list(rendered.size),
                    }
                    warnings.append("参考图与重绘图画布不同；未通过缩放进行比较")
                else:
                    ref_array = np.asarray(ref_image, dtype=np.float32)
                    render_array = np.asarray(rendered, dtype=np.float32)
                    absolute = np.abs(ref_array - render_array)
                    mae = float(np.mean(absolute) / 255.0)
                    plot_mae: float | None = None
                    project_path = project_dir / "project.json"
                    if project_path.is_file():
                        project = read_json(project_path)
                        box = project.get("chart", {}).get("plot_box")
                        if (
                            isinstance(box, list)
                            and len(box) == 4
                            and all(isinstance(value, (int, float)) for value in box)
                        ):
                            left, top, right, bottom = [int(round(value)) for value in box]
                            if 0 <= left < right < ref_image.width and 0 <= top < bottom < ref_image.height:
                                plot_mae = float(
                                    np.mean(absolute[top : bottom + 1, left : right + 1]) / 255.0
                                )
                    heatmap = np.mean(absolute, axis=2)
                    maximum = float(np.max(heatmap))
                    normalized = (
                        np.clip(heatmap / maximum * 255.0, 0, 255).astype(np.uint8)
                        if maximum > 0
                        else np.zeros_like(heatmap, dtype=np.uint8)
                    )
                    heatmap_path = project_dir / "residual-heatmap.png"
                    Image.fromarray(normalized, mode="L").save(heatmap_path)
                    visual = {
                        "status": "measured",
                        "normalized_mae": mae,
                        "plot_box_normalized_mae": plot_mae,
                        "canvas": list(ref_image.size),
                        "residual_heatmap": str(heatmap_path),
                        "说明": "残差指标用于定位差异，不单独决定科学验收结论。",
                    }
        else:
            warnings.append("参考图或重绘 PNG 缺失")
    extraction = manifest.get("extraction_status", "not_run")
    review_status = manifest.get("review_status", "not_run")
    render_status = manifest.get("render_status", "not_run")
    if errors:
        delivery = "failed"
    elif extraction == "not_applicable" and render_status == "pass":
        delivery = "pass"
    elif extraction == "pass" and review_status == "accepted" and render_status == "pass":
        delivery = "pass"
    elif (
        extraction in {"pass", "partial"}
        and review_status in {"accepted", "partial"}
        and render_status == "pass"
    ):
        delivery = "partial"
    else:
        delivery = "failed"
    report = {
        "schema": "more-sci-figure.validation-report.v1",
        "status": "pass" if not errors else "failed",
        "delivery_status": delivery,
        "stage_statuses": {
            "extraction_status": extraction,
            "review_status": review_status,
            "render_status": render_status,
        },
        "artifact_checks": artifact_checks,
        "visual_comparison": visual,
        "errors": errors,
        "warnings": warnings,
    }
    report_path = project_dir / "validation-report.json"
    write_json(report_path, report)
    manifest["delivery_status"] = delivery
    if visual.get("residual_heatmap"):
        manifest["artifacts"]["residual_heatmap"] = artifact_entry(
            Path(str(visual["residual_heatmap"]))
        )
    manifest["artifacts"]["validation_report"] = artifact_entry(report_path)
    write_json(manifest_path, manifest)
    return report


def pipeline_command(
    spec_path: Path,
    out_dir: Path,
    review_decisions: Path | None = None,
) -> dict[str, Any]:
    extraction = extract_command(spec_path, out_dir)
    if review_decisions is None:
        return {
            "extraction": extraction["status"],
            "review": "awaiting_review",
            "render": "not_run",
            "delivery": "not_run",
            "复核页面": str(out_dir / "review.html"),
            "下一步": "完成人工复核并使用 --review-decisions 再次运行 pipeline，或分别运行 review-apply、render、validate。",
        }
    review = review_apply_command(out_dir, review_decisions)
    if review["review_status"] == "rejected":
        return {
            "extraction": extraction["status"],
            "review": "rejected",
            "render": "not_run",
            "delivery": "failed",
        }
    rendering = render_command(out_dir / "project.json", out_dir / "data.csv", out_dir / "render")
    validation = validate_command(out_dir)
    return {
        "extraction": extraction["status"],
        "review": review["review_status"],
        "render": rendering["status"],
        "delivery": validation["delivery_status"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可审计的科研图表数据提取、人工复核、重绘与验证。")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="显示版本并退出",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="检查来源并生成项目模板")
    inspect_parser.add_argument("--input", required=True, type=Path, help="图片、PDF 或数据文件")
    inspect_parser.add_argument("--chart-type", choices=sorted(SUPPORTED_CHARTS), help="图表类型")
    inspect_parser.add_argument("--page", type=int, default=1, help="PDF 页码，从 1 开始")
    inspect_parser.add_argument("--out-dir", required=True, type=Path, help="输出目录")

    extract_parser = subparsers.add_parser("extract", help="提取可见候选值并生成复核页面")
    extract_parser.add_argument("--spec", required=True, type=Path, help="项目规格 project.json")
    extract_parser.add_argument("--out-dir", required=True, type=Path, help="证据目录")

    review_parser = subparsers.add_parser("review", help="重新生成本地人工复核页面")
    review_parser.add_argument("--project-dir", required=True, type=Path, help="证据目录")

    apply_parser = subparsers.add_parser("review-apply", help="应用人工复核决定并生成正式 data.csv")
    apply_parser.add_argument("--project-dir", required=True, type=Path, help="证据目录")
    apply_parser.add_argument("--decisions", required=True, type=Path, help="复核决定 JSON")

    render_parser = subparsers.add_parser("render", help="把声明数据重绘为 PNG、SVG 和 PDF")
    render_parser.add_argument("--spec", required=True, type=Path, help="项目规格")
    render_parser.add_argument("--data", required=True, type=Path, help="正式数据或外部数据")
    render_parser.add_argument("--out-dir", required=True, type=Path, help="重绘输出目录")

    validate_parser = subparsers.add_parser("validate", help="验证交付物、哈希、状态和可选图像残差")
    validate_parser.add_argument("--project-dir", required=True, type=Path, help="证据目录")
    validate_parser.add_argument("--reference", type=Path, help="可选参考图片")

    pipeline_parser = subparsers.add_parser("pipeline", help="按门控顺序执行提取、复核、重绘和验证")
    pipeline_parser.add_argument("--spec", required=True, type=Path, help="项目规格")
    pipeline_parser.add_argument("--out-dir", required=True, type=Path, help="证据目录")
    pipeline_parser.add_argument(
        "--review-decisions",
        type=Path,
        help="人工复核决定；缺省时管线停在 awaiting_review",
    )
    for current in (
        parser,
        inspect_parser,
        extract_parser,
        review_parser,
        apply_parser,
        render_parser,
        validate_parser,
        pipeline_parser,
    ):
        current._positionals.title = "位置参数"
        current._optionals.title = "选项"
        for action in current._actions:
            if isinstance(action, argparse._HelpAction):
                action.help = "显示帮助并退出"
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            inspect_command(args.input, args.chart_type, args.out_dir, args.page)
            return 0
        if args.command == "extract":
            result = extract_command(args.spec, args.out_dir)
        elif args.command == "review":
            result = review_command(args.project_dir)
        elif args.command == "review-apply":
            result = review_apply_command(args.project_dir, args.decisions)
        elif args.command == "render":
            result = render_command(args.spec, args.data, args.out_dir)
        elif args.command == "validate":
            result = validate_command(args.project_dir, args.reference)
        else:
            result = pipeline_command(args.spec, args.out_dir, args.review_decisions)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except FigureError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
