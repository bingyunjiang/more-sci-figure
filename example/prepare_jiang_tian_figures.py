#!/usr/bin/env python3
"""生成 Jiang & Tian (2021) Fig. 7/9 的可审计来源与诊断产物。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
PDF = ROOT / (
    "Jiang和Tian - 2021 - Integrated Prediction of Mechanical Behavior for the "
    "Non-Aligned Fiber Composites With Experimental.pdf"
)
CONFIG = {
    "fig7": {
        "pdf_page": 6,
        "image_xref": 186,
        "image_placement_points": [309.0329895, 37.0199890, 537.1669922, 210.7839966],
        "page_figure_box_exclusive": [600, 60, 1090, 480],
        "page_plot_box_inclusive": [687, 81, 1061, 369],
        "page_blocker_boxes_inclusive": [[735, 286, 1055, 360]],
        "blockers": [
            "红、蓝、黑三种颜色分别被试验曲线和 MFH 曲线复用",
            "图例位于绘图区内部并使用与数据系列相同的颜色与线型",
            "试验曲线与 MFH 曲线局部重叠",
        ],
    },
    "fig9": {
        "pdf_page": 8,
        "image_xref": 219,
        "image_placement_points": [309.0329895, 560.5789795, 537.1669922, 708.3209839],
        "page_figure_box_exclusive": [600, 1100, 1095, 1485],
        "page_plot_box_inclusive": [686, 1130, 1063, 1358],
        "page_blocker_boxes_inclusive": [[895, 1180, 1055, 1335]],
        "blockers": [
            "仿真与 µCT 系列复用蓝色和黑色",
            "图例位于绘图区内部并覆盖部分横坐标范围",
            "多个系列在中心层及皮层区域局部交叉或重叠",
        ],
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def translate_box(box: list[int], origin: tuple[int, int]) -> list[int]:
    left, top, right, bottom = box
    ox, oy = origin
    return [left - ox, top - oy, right - ox, bottom - oy]


def main() -> None:
    with fitz.open(PDF) as document:
        for figure_id, config in CONFIG.items():
            directory = ROOT / figure_id
            page_raster = directory / "source-page.png"
            project_path = directory / "project.json"
            source_report_path = directory / "source-report.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))

            embedded = document.extract_image(config["image_xref"])
            if embedded["ext"] not in {"jpeg", "jpg"}:
                raise RuntimeError(
                    f"{figure_id} 的嵌入图像格式异常：{embedded['ext']}"
                )
            original_path = directory / "figure-original.jpeg"
            original_path.write_bytes(embedded["image"])

            figure_box = config["page_figure_box_exclusive"]
            left, top, right, bottom = figure_box
            with Image.open(page_raster).convert("RGB") as page:
                figure = page.crop((left, top, right, bottom))
                figure_path = directory / "figure.png"
                figure.save(figure_path)

                plot_left, plot_top, plot_right, plot_bottom = config[
                    "page_plot_box_inclusive"
                ]
                plot = page.crop(
                    (plot_left, plot_top, plot_right + 1, plot_bottom + 1)
                )
                plot_path = directory / "plot.png"
                plot.save(plot_path)

                diagnostic = figure.copy()
                draw = ImageDraw.Draw(diagnostic, "RGBA")
                plot_relative = translate_box(
                    config["page_plot_box_inclusive"], (left, top)
                )
                draw.rectangle(
                    plot_relative, outline=(22, 132, 75, 255), width=4
                )
                draw.rectangle(
                    [
                        plot_relative[0],
                        plot_relative[1],
                        plot_relative[0] + 122,
                        plot_relative[1] + 22,
                    ],
                    fill=(22, 132, 75, 220),
                )
                draw.text(
                    (plot_relative[0] + 7, plot_relative[1] + 5),
                    "confirmed plot box",
                    fill=(255, 255, 255, 255),
                )
                for blocker in config["page_blocker_boxes_inclusive"]:
                    blocker_relative = translate_box(blocker, (left, top))
                    draw.rectangle(
                        blocker_relative,
                        fill=(216, 58, 58, 45),
                        outline=(216, 58, 58, 255),
                        width=4,
                    )
                    draw.text(
                        (blocker_relative[0] + 6, blocker_relative[1] + 5),
                        "legend / same-color blocker",
                        fill=(166, 27, 27, 255),
                    )
                diagnostic_path = directory / "diagnostic-overlay.png"
                diagnostic.save(diagnostic_path)

            crop_report = {
                "schema": "more-sci-figure.example-crop.v1",
                "figure": figure_id,
                "pdf_page": config["pdf_page"],
                "embedded_image": {
                    "xref": config["image_xref"],
                    "placement_points": config["image_placement_points"],
                    "path": "figure-original.jpeg",
                    "sha256": sha256(original_path),
                    "width": embedded["width"],
                    "height": embedded["height"],
                },
                "page_raster": {
                    "path": "source-page.png",
                    "sha256": sha256(page_raster),
                },
                "page_figure_box_exclusive": figure_box,
                "page_plot_box_inclusive": config["page_plot_box_inclusive"],
                "page_blocker_boxes_inclusive": config[
                    "page_blocker_boxes_inclusive"
                ],
                "blockers": config["blockers"],
                "artifacts": {
                    "figure": {
                        "path": "figure.png",
                        "sha256": sha256(figure_path),
                    },
                    "plot": {
                        "path": "plot.png",
                        "sha256": sha256(plot_path),
                    },
                    "diagnostic_overlay": {
                        "path": "diagnostic-overlay.png",
                        "sha256": sha256(diagnostic_path),
                    },
                },
                "status": "prepared",
                "numeric_extraction_authorized": False,
            }
            crop_report_path = directory / "crop-report.json"
            crop_report_path.write_text(
                json.dumps(crop_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with Image.open(original_path) as original:
                original_width, original_height = original.size
            extraction_report = {
                "schema": "more-sci-figure.extraction-report.v1",
                "status": "failed",
                "numeric_output_authorized": False,
                "source": {
                    "path": project["source"]["path"],
                    "sha256": project["source"]["sha256"],
                    "page": project["source"]["page"],
                    "measurement_raster": "figure-original.jpeg",
                    "measurement_sha256": sha256(original_path),
                    "embedded_image_xref": config["image_xref"],
                    "width": original_width,
                    "height": original_height,
                },
                "chart_type": "line",
                "plot_box": project["chart"]["plot_box"],
                "calibration": {
                    "status": "confirmed",
                    "x_axis": project["chart"]["x_axis"],
                    "y_axis": project["chart"]["y_axis"],
                    "note": "每个线性坐标轴使用四个或更多可见刻度锚点。",
                },
                "rows": 0,
                "diagnostics": {
                    "status": "prepared_for_project_extractor",
                    "blockers": config["blockers"],
                },
                "review_status": "not_run",
                "errors": config["blockers"],
                "limitations": (
                    "通用颜色逐列提取器不能区分同色系列；"
                    "等待 example 专用线型与目标颜色分离提取器。"
                ),
                "required_next": (
                    "运行 python3 example/extract_jiang_tian_curves.py，"
                    "再人工复核候选叠图。"
                ),
            }
            extraction_report_path = directory / "extraction-report.json"
            extraction_report_path.write_text(
                json.dumps(extraction_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            manifest = {
                "schema": "more-sci-figure.manifest.v1",
                "tool_version": "0.2.0",
                "project_id": project["project_id"],
                "source_sha256": project["source"]["sha256"],
                "extraction_status": "failed",
                "review_status": "not_run",
                "render_status": "not_run",
                "delivery_status": "not_run",
                "artifacts": {
                    "project_spec": artifact(project_path),
                    "source_report": artifact(source_report_path),
                    "page_raster": artifact(page_raster),
                    "measurement_raster": artifact(original_path),
                    "figure_crop": artifact(figure_path),
                    "plot_crop": artifact(plot_path),
                    "diagnostic_overlay": artifact(diagnostic_path),
                    "crop_report": artifact(crop_report_path),
                    "extraction_report": artifact(extraction_report_path),
                },
                "note": (
                    "已锁定原 PDF、页面与嵌入原始栅格；"
                    "等待项目专用提取器生成候选值。"
                ),
            }
            (directory / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
