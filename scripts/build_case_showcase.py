#!/usr/bin/env python3
"""Build an auditable, symmetric original-versus-redraw showcase asset."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CANVAS_WIDTH = 2400
CANVAS_HEIGHT = 1350
PANEL_WIDTH = 1080
PANEL_HEIGHT = 870
IMAGE_BOX_WIDTH = 1008
IMAGE_BOX_HEIGHT = 670


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def data_uri(path: Path) -> str:
    mime = {
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"不支持的图片格式：{path.suffix}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def contain_geometry(
    image_path: Path,
    box_x: int,
    box_y: int,
    box_width: int = IMAGE_BOX_WIDTH,
    box_height: int = IMAGE_BOX_HEIGHT,
) -> dict[str, int]:
    with Image.open(image_path) as image:
        source_width, source_height = image.size
    scale = min(box_width / source_width, box_height / source_height)
    width = round(source_width * scale)
    height = round(source_height * scale)
    return {
        "x": box_x + (box_width - width) // 2,
        "y": box_y + (box_height - height) // 2,
        "width": width,
        "height": height,
        "source_width": source_width,
        "source_height": source_height,
    }


def score_payload(
    validation_report: dict[str, Any],
    extraction_report: dict[str, Any],
) -> dict[str, Any]:
    delivery = validation_report.get("delivery_assessment", {})
    delivery_score = float(delivery["overall_score"])
    extraction_score = float(extraction_report["overall_score"])
    return {
        "delivery_score": delivery_score,
        "delivery_minimum_dimension_score": float(
            delivery["minimum_dimension_score"]
        ),
        "delivery_profile": delivery.get("profile"),
        "delivery_status": validation_report.get("delivery_status"),
        "extraction_score": extraction_score,
        "extraction_minimum_dimension_score": float(
            extraction_report["minimum_dimension_score"]
        ),
        "extraction_profile": extraction_report.get("acceptance", {}).get("profile"),
        "extraction_status": validation_report.get("stage_statuses", {}).get(
            "extraction_status"
        ),
        "review_status": validation_report.get("stage_statuses", {}).get(
            "review_status"
        ),
        "render_status": validation_report.get("stage_statuses", {}).get(
            "render_status"
        ),
        "qualification_note": delivery.get("qualification_note"),
    }


def require_formal_case(validation_report: dict[str, Any]) -> None:
    stages = validation_report.get("stage_statuses", {})
    actual = {
        "validation_status": validation_report.get("status"),
        "extraction_status": stages.get("extraction_status"),
        "review_status": stages.get("review_status"),
        "render_status": stages.get("render_status"),
        "delivery_status": validation_report.get("delivery_status"),
        "delivery_decision": validation_report.get("delivery_assessment", {}).get(
            "decision"
        ),
    }
    required = {
        "validation_status": "pass",
        "extraction_status": "pass",
        "review_status": "accepted",
        "render_status": "pass",
        "delivery_status": "pass",
        "delivery_decision": "accepted",
    }
    failures = [
        f"{key}={actual[key]!r}（要求 {expected!r}）"
        for key, expected in required.items()
        if actual[key] != expected
    ]
    if failures:
        raise ValueError("不能生成正式案例：" + "；".join(failures))


def format_score(value: float) -> str:
    return f"{value:.0f}" if value.is_integer() else f"{value:.1f}"


def panel(
    *,
    x: int,
    label: str,
    badge: str,
    badge_color: str,
    image_uri: str,
    geometry: dict[str, int],
    score_markup: str = "",
) -> str:
    return f'''
  <g filter="url(#shadow)">
    <rect x="{x}" y="300" width="{PANEL_WIDTH}" height="{PANEL_HEIGHT}" rx="42" fill="#ffffff"/>
  </g>
  <text x="{x + 40}" y="365" class="panel-title">{escape(label)}</text>
  <rect x="{x + PANEL_WIDTH - 270}" y="326" width="230" height="48" rx="24" fill="{badge_color}"/>
  <text x="{x + PANEL_WIDTH - 155}" y="358" text-anchor="middle" class="badge">{escape(badge)}</text>
  <rect x="{x + 36}" y="405" width="{IMAGE_BOX_WIDTH}" height="{IMAGE_BOX_HEIGHT}" rx="24" fill="#f4f7fb" stroke="#d7e1ef" stroke-width="2"/>
  <image href="{image_uri}" x="{geometry['x']}" y="{geometry['y']}" width="{geometry['width']}" height="{geometry['height']}" preserveAspectRatio="xMidYMid meet"/>
  {score_markup}'''


def build_svg(
    *,
    title: str,
    subtitle: str,
    original_path: Path,
    redraw_path: Path,
    scores: dict[str, Any],
    formal_rows: int,
) -> tuple[str, dict[str, dict[str, int]]]:
    left_x = 96
    right_x = 1224
    image_y = 405
    left_geometry = contain_geometry(original_path, left_x + 36, image_y)
    right_geometry = contain_geometry(redraw_path, right_x + 36, image_y)
    delivery = format_score(scores["delivery_score"])
    extraction = format_score(scores["extraction_score"])
    original_panel = panel(
        x=left_x,
        label="(a) 论文原图",
        badge="SOURCE LOCKED",
        badge_color="#e9f1ff",
        image_uri=data_uri(original_path),
        geometry=left_geometry,
    )
    score_markup = f'''
  <rect x="{right_x + 40}" y="1100" width="460" height="56" rx="28" fill="#075f54"/>
  <text x="{right_x + 270}" y="1138" text-anchor="middle" class="score-primary">重绘交付评分  {delivery} / 100</text>
  <text x="{right_x + 530}" y="1138" class="score-secondary">提取评估 {extraction} / 100 · 复核 {escape(str(scores['review_status']))}</text>'''
    redraw_panel = panel(
        x=right_x,
        label="(b) 正式数据重绘",
        badge="FORMAL · ACCEPTED",
        badge_color="#dcf8ef",
        image_uri=data_uri(redraw_path),
        geometry=right_geometry,
        score_markup=score_markup,
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}：论文原图与正式数据重绘对照</title>
<desc id="desc">左右等宽并列；左侧为锁定来源的论文原图，右侧为经过人工复核的正式数据重绘。</desc>
<defs>
  <linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f7faff"/><stop offset="1" stop-color="#eef8f5"/></linearGradient>
  <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="16" stdDeviation="18" flood-color="#51627a" flood-opacity=".16"/></filter>
  <style>
    text {{ font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", sans-serif; fill: #14213d; }}
    .eyebrow {{ font-size: 24px; font-weight: 760; letter-spacing: 2px; fill: #155eef; }}
    .title {{ font-size: 62px; font-weight: 820; letter-spacing: -1px; }}
    .subtitle {{ font-size: 27px; font-weight: 520; fill: #5b687c; }}
    .panel-title {{ font-size: 35px; font-weight: 780; }}
    .badge {{ font-size: 19px; font-weight: 760; fill: #155eef; }}
    .score-primary {{ font-size: 24px; font-weight: 780; fill: #ffffff; }}
    .score-secondary {{ font-size: 23px; font-weight: 650; fill: #40516a; }}
    .footer {{ font-size: 22px; font-weight: 560; fill: #607087; }}
  </style>
</defs>
<rect width="2400" height="1350" fill="url(#background)"/>
<circle cx="220" cy="80" r="310" fill="#8fb4ff" opacity=".16"/>
<circle cx="2260" cy="1280" r="380" fill="#6bd1b9" opacity=".14"/>
<text x="96" y="76" class="eyebrow">MORE SCI FIGURE · 正式案例展示</text>
<text x="96" y="158" class="title">{escape(title)}</text>
<text x="96" y="210" class="subtitle">{escape(subtitle)}</text>
<rect x="96" y="246" width="2208" height="2" fill="#cbd8e8"/>
{original_panel}
{redraw_panel}
<path d="M1185 694h30" stroke="#155eef" stroke-width="6" stroke-linecap="round"/><path d="M1204 683l12 11-12 11" fill="none" stroke="#155eef" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
<text x="96" y="1243" class="footer">正式数据 {formal_rows} 行 · extraction {escape(str(scores['extraction_status']))} · review {escape(str(scores['review_status']))} · render {escape(str(scores['render_status']))} · delivery {escape(str(scores['delivery_status']))}</text>
<text x="2304" y="1243" text-anchor="end" class="footer">评分评价证据链、数据映射与交付规格，不等同于科研真值准确率</text>
<text x="96" y="1298" class="footer">Dr. Jiang Bingyun · github.com/bingyunjiang/more-sci-figure</text>
</svg>'''
    return svg, {"original": left_geometry, "redraw": right_geometry}


def render_png(svg_path: Path, png_path: Path) -> None:
    executable = shutil.which("rsvg-convert")
    if executable is None:
        raise RuntimeError("未找到 rsvg-convert，无法生成 README 用 PNG")
    subprocess.run(
        [
            executable,
            "--width",
            str(CANVAS_WIDTH),
            "--height",
            str(CANVAS_HEIGHT),
            "--output",
            str(png_path),
            str(svg_path),
        ],
        check=True,
    )


def build_showcase(args: argparse.Namespace) -> dict[str, Any]:
    original = args.original.resolve()
    redraw = args.redraw.resolve()
    validation_path = args.validation_report.resolve()
    extraction_path = args.extraction_report.resolve()
    formal_data_path = args.formal_data_report.resolve()
    for path in (original, redraw, validation_path, extraction_path, formal_data_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    validation_report = read_json(validation_path)
    require_formal_case(validation_report)
    scores = score_payload(validation_report, read_json(extraction_path))
    formal_data = read_json(formal_data_path)
    formal_rows = int(formal_data["formal_rows"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = args.out_dir / f"{args.stem}.svg"
    png_path = args.out_dir / f"{args.stem}.png"
    report_path = args.out_dir / f"{args.stem}.json"
    svg, geometry = build_svg(
        title=args.title,
        subtitle=args.subtitle,
        original_path=original,
        redraw_path=redraw,
        scores=scores,
        formal_rows=formal_rows,
    )
    svg_path.write_text(svg, encoding="utf-8")
    if not args.no_png:
        render_png(svg_path, png_path)
    report: dict[str, Any] = {
        "schema": "more-sci-figure.case-showcase.v1",
        "layout": {
            "canvas": [CANVAS_WIDTH, CANVAS_HEIGHT],
            "mode": "symmetric_side_by_side",
            "panel_width": PANEL_WIDTH,
            "image_fit": "contain_no_crop",
            "embedded_geometry": geometry,
        },
        "scores": scores,
        "formal_rows": formal_rows,
        "sources": {
            "original": {"path": display_path(original), "sha256": sha256(original)},
            "redraw": {"path": display_path(redraw), "sha256": sha256(redraw)},
            "validation_report": {
                "path": display_path(validation_path),
                "sha256": sha256(validation_path),
            },
            "extraction_report": {
                "path": display_path(extraction_path),
                "sha256": sha256(extraction_path),
            },
            "formal_data_report": {
                "path": display_path(formal_data_path),
                "sha256": sha256(formal_data_path),
            },
        },
        "outputs": {
            "svg": {"path": display_path(svg_path), "sha256": sha256(svg_path)},
        },
        "score_scope": "交付评分评价文件、哈希、格式、数据映射和规格执行；不等同于科研数据准确率或视觉审美评分。",
    }
    if png_path.is_file():
        report["outputs"]["png"] = {
            "path": display_path(png_path),
            "sha256": sha256(png_path),
        }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="生成左右等宽、来源与评分可追溯的论文原图/正式重绘案例图。"
    )
    result.add_argument("--original", type=Path, required=True, help="论文原图")
    result.add_argument("--redraw", type=Path, required=True, help="正式重绘 PNG")
    result.add_argument("--validation-report", type=Path, required=True)
    result.add_argument("--extraction-report", type=Path, required=True)
    result.add_argument("--formal-data-report", type=Path, required=True)
    result.add_argument("--out-dir", type=Path, required=True)
    result.add_argument("--stem", default="case-original-vs-redraw")
    result.add_argument("--title", required=True)
    result.add_argument(
        "--subtitle",
        default="左：锁定来源的论文原图 ｜ 右：经人工复核的正式 data.csv 重绘",
    )
    result.add_argument("--no-png", action="store_true", help="仅生成 SVG 与审计报告")
    return result


def main() -> int:
    args = parser().parse_args()
    report = build_showcase(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
