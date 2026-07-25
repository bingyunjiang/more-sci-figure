from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import more_sci_figure as msf


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AxisMapTests(unittest.TestCase):
    def test_linear_map_supports_reversed_pixel_axis(self) -> None:
        mapping = msf.AxisMap(
            {
                "scale": "linear",
                "anchors": [{"pixel": 100, "value": 0}, {"pixel": 20, "value": 10}],
            }
        )
        self.assertAlmostEqual(5.0, mapping.value(60), places=6)
        self.assertAlmostEqual(60.0, mapping.pixel(5), places=6)
        self.assertFalse(mapping.report()["rmse_evaluable"])

    def test_log_map_fits_in_transformed_space(self) -> None:
        mapping = msf.AxisMap(
            {
                "scale": "log10",
                "anchors": [
                    {"pixel": 0, "value": 1},
                    {"pixel": 50, "value": 10},
                    {"pixel": 100, "value": 100},
                ],
            }
        )
        self.assertAlmostEqual(10.0, mapping.value(50), places=6)
        self.assertTrue(mapping.report()["rmse_evaluable"])

    def test_uncertainty_is_positive(self) -> None:
        mapping = msf.AxisMap(
            {
                "scale": "linear",
                "anchors": [{"pixel": 0, "value": 0}, {"pixel": 100, "value": 10}],
            }
        )
        self.assertGreater(mapping.uncertainty(50), 0)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_line_project(self, *, with_gap: bool = False) -> Path:
        source = self.root / "line.png"
        image = Image.new("RGB", (220, 140), "white")
        draw = ImageDraw.Draw(image)
        if with_gap:
            draw.line((20, 110, 90, 78), fill="#d62728", width=3)
            draw.line((130, 61, 200, 30), fill="#d62728", width=3)
        else:
            draw.line((20, 110, 200, 30), fill="#d62728", width=3)
        image.save(source)
        spec = {
            "schema": msf.SCHEMA,
            "project_id": "line-fixture",
            "source": {
                "path": str(source),
                "sha256": digest(source),
                "page": None,
                "measurement_raster": str(source),
                "measurement_sha256": digest(source),
            },
            "chart": {
                "type": "line",
                "plot_box": [20, 20, 200, 110],
                "x_axis": {
                    "scale": "linear",
                    "anchors": [{"pixel": 20, "value": 0}, {"pixel": 200, "value": 10}],
                },
                "y_axis": {
                    "scale": "linear",
                    "anchors": [{"pixel": 110, "value": 0}, {"pixel": 30, "value": 8}],
                },
                "series": [{"id": "trend", "color": "#d62728", "tolerance": 15}],
            },
            "quality_gates": {
                "line": {"min_coverage": 0.5, "max_gap_fraction": 0.3}
            },
            "render": {
                "plot_type": "line",
                "x": "x",
                "y": "y",
                "group": "series",
                "x_label": "时间",
                "y_label": "响应",
                "title": "合成夹具",
            },
        }
        spec_path = self.root / "project.json"
        msf.write_json(spec_path, spec)
        return spec_path

    def decisions_for(self, evidence: Path, accepted_ids: set[str] | None = None) -> Path:
        candidates = msf.read_tabular_rows(evidence / "candidates.csv")
        accepted_ids = accepted_ids if accepted_ids is not None else {
            str(row["candidate_id"]) for row in candidates
        }
        payload = {
            "schema": msf.REVIEW_SCHEMA,
            "candidate_sha256": digest(evidence / "candidates.csv"),
            "reviewed_by": "自动化测试中的人工复核夹具",
            "reviewed_at": "2026-07-25T00:00:00Z",
            "decisions": [
                {
                    "candidate_id": str(row["candidate_id"]),
                    "decision": (
                        "accepted" if str(row["candidate_id"]) in accepted_ids else "rejected"
                    ),
                    "reason": "" if str(row["candidate_id"]) in accepted_ids else "测试拒绝",
                }
                for row in candidates
            ],
        }
        path = self.root / "review-decisions-input.json"
        msf.write_json(path, payload)
        return path

    def test_pipeline_stops_for_review_then_completes(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        waiting = msf.pipeline_command(spec_path, output)
        self.assertEqual("awaiting_review", waiting["review"])
        self.assertEqual("not_run", waiting["render"])
        self.assertTrue((output / "candidates.csv").is_file())
        self.assertTrue((output / "review.html").is_file())
        self.assertFalse((output / "data.csv").exists())

        decisions = self.decisions_for(output)
        result = msf.pipeline_command(spec_path, output, decisions)
        self.assertEqual("pass", result["extraction"])
        self.assertEqual("accepted", result["review"])
        self.assertEqual("pass", result["render"])
        self.assertEqual("pass", result["delivery"])
        manifest = msf.read_json(output / "manifest.json")
        self.assertEqual("accepted", manifest["review_status"])
        for relative in (
            "candidates.csv",
            "data.csv",
            "overlay.png",
            "review-decisions.json",
            "render/render.png",
            "render/render.svg",
            "render/render.pdf",
            "validation-report.json",
        ):
            self.assertTrue((output / relative).is_file(), relative)

    def test_review_partial_only_promotes_accepted_rows(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        candidates = msf.read_tabular_rows(output / "candidates.csv")
        accepted_id = str(candidates[0]["candidate_id"])
        result = msf.review_apply_command(output, self.decisions_for(output, {accepted_id}))
        self.assertEqual("partial", result["review_status"])
        promoted = msf.read_tabular_rows(output / "data.csv")
        self.assertEqual(1, len(promoted))
        self.assertEqual(accepted_id, promoted[0]["candidate_id"])

    def test_review_hash_mismatch_is_rejected(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions = self.decisions_for(output)
        payload = msf.read_json(decisions)
        payload["candidate_sha256"] = "0" * 64
        msf.write_json(decisions, payload)
        with self.assertRaisesRegex(msf.FigureError, "哈希"):
            msf.review_apply_command(output, decisions)

    def test_source_hash_mismatch_fails_spec_validation(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["source"]["sha256"] = "0" * 64
        msf.write_json(spec_path, spec)
        errors = msf.validate_spec(spec, spec_path)
        self.assertIn("source.sha256 与当前来源文件不一致", errors)

    def test_equal_axis_values_are_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["chart"]["x_axis"]["anchors"][1]["value"] = 0
        errors = msf.validate_spec(spec, spec_path)
        self.assertTrue(any("至少包含两个不同值" in error for error in errors))

    def test_non_finite_anchor_pixel_is_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["chart"]["x_axis"]["anchors"][0]["pixel"] = float("nan")
        errors = msf.validate_spec(spec, spec_path)
        self.assertTrue(any("锚点像素必须是有限数值" in error for error in errors))

    def test_non_positive_log_anchor_is_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["chart"]["y_axis"]["scale"] = "log10"
        spec["chart"]["y_axis"]["anchors"][0]["value"] = 0
        errors = msf.validate_spec(spec, spec_path)
        self.assertTrue(any("log10 锚点必须为正数" in error for error in errors))

    def test_invalid_quality_gate_is_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["quality_gates"]["line"]["min_coverage"] = 1.1
        errors = msf.validate_spec(spec, spec_path)
        self.assertTrue(any("min_coverage" in error for error in errors))

    def test_measurement_hash_mismatch_is_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["source"]["measurement_sha256"] = "0" * 64
        msf.write_json(spec_path, spec)
        with self.assertRaisesRegex(msf.FigureError, "测量栅格哈希"):
            msf.extract_command(spec_path, self.root / "evidence")

    def test_review_must_cover_every_candidate(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions = self.decisions_for(output)
        payload = msf.read_json(decisions)
        payload["decisions"] = payload["decisions"][:-1]
        msf.write_json(decisions, payload)
        with self.assertRaisesRegex(msf.FigureError, "未覆盖全部候选值"):
            msf.review_apply_command(output, decisions)

    def test_gap_is_preserved_as_two_render_segments(self) -> None:
        spec_path = self.make_line_project(with_gap=True)
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions = self.decisions_for(output)
        msf.review_apply_command(output, decisions)
        report = msf.render_command(spec_path, output / "data.csv", output / "render")
        self.assertEqual(2, report["rendered_segments"]["trend"])

    def test_direct_data_render_is_not_applicable_to_extraction(self) -> None:
        spec_path = self.make_line_project()
        data = self.root / "supplied.csv"
        data.write_text("series,x,y\ntrend,1,2\ntrend,2,3\n", encoding="utf-8")
        output = self.root / "direct"
        msf.render_command(spec_path, data, output / "render")
        validation = msf.validate_command(output)
        manifest = msf.read_json(output / "manifest.json")
        self.assertEqual("not_applicable", manifest["extraction_status"])
        self.assertEqual("not_applicable", manifest["review_status"])
        self.assertEqual("pass", validation["delivery_status"])

    def test_validation_fails_if_review_artifact_is_missing(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions = self.decisions_for(output)
        msf.review_apply_command(output, decisions)
        msf.render_command(spec_path, output / "data.csv", output / "render")
        (output / "review-decisions.json").unlink()
        validation = msf.validate_command(output)
        self.assertEqual("failed", validation["delivery_status"])
        self.assertTrue(any("review_decisions" in error for error in validation["errors"]))

    def test_canvas_mismatch_is_reported_without_resizing(self) -> None:
        spec_path = self.make_line_project()
        data = self.root / "supplied.csv"
        data.write_text("series,x,y\ntrend,1,2\ntrend,2,3\n", encoding="utf-8")
        output = self.root / "direct"
        msf.render_command(spec_path, data, output / "render")
        reference = self.root / "reference.png"
        Image.new("RGB", (10, 10), "white").save(reference)
        validation = msf.validate_command(output, reference)
        self.assertEqual("canvas_mismatch", validation["visual_comparison"]["status"])

    def test_excel_rows_are_supported_for_rendering(self) -> None:
        from openpyxl import Workbook

        path = self.root / "data.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["series", "x", "y"])
        sheet.append(["a", 0, 1.5])
        sheet.append(["a", 1, 2.5])
        workbook.save(path)
        workbook.close()
        rows = msf.read_tabular_rows(path)
        self.assertEqual(2, len(rows))
        self.assertEqual(2.5, rows[1]["y"])

    def test_legacy_xls_is_not_claimed_as_supported(self) -> None:
        path = self.root / "legacy.xls"
        path.write_bytes(b"not-a-real-workbook")
        self.assertEqual("unknown", msf.source_metadata(path)["kind"])

    def test_scatter_component_centres_and_uncertainty_are_recovered(self) -> None:
        image = Image.new("RGB", (120, 100), "white")
        draw = ImageDraw.Draw(image)
        for x, y in ((20, 80), (60, 50), (100, 20)):
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#0072b2")
        x_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 10, "value": 0}, {"pixel": 110, "value": 10}]}
        )
        y_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 90, "value": 0}, {"pixel": 10, "value": 8}]}
        )
        rows, diagnostics = msf.extract_scatter(
            np.asarray(image),
            (10, 10, 110, 90),
            [{"id": "points", "color": "#0072b2", "tolerance": 10, "min_area": 10, "max_area": 100}],
            x_map,
            y_map,
        )
        self.assertEqual(3, len(rows))
        self.assertGreater(rows[0]["x_uncertainty"], 0)
        self.assertEqual(3, diagnostics["series"][0]["accepted_components"])

    def test_lab_color_mask_tolerates_small_color_shift(self) -> None:
        array = np.asarray([[[2, 113, 180], [255, 255, 255]]], dtype=np.uint8)
        mask = msf.series_mask(
            array,
            {"color": "#0072b2", "color_space": "lab", "tolerance": 3},
        )
        self.assertEqual([True, False], mask[0].tolist())

    def test_elongated_scatter_component_is_rejected(self) -> None:
        image = Image.new("RGB", (100, 80), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 38, 70, 41), fill="#0072b2")
        mapping = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 0, "value": 0}, {"pixel": 99, "value": 1}]}
        )
        rows, diagnostics = msf.extract_scatter(
            np.asarray(image),
            (0, 0, 99, 79),
            [
                {
                    "id": "points",
                    "color": "#0072b2",
                    "tolerance": 10,
                    "min_area": 10,
                    "max_area": 500,
                    "max_aspect_ratio": 4,
                }
            ],
            mapping,
            mapping,
        )
        self.assertEqual([], rows)
        self.assertGreater(diagnostics["series"][0]["rejected_components"], 0)

    def test_bar_rectangles_are_recovered(self) -> None:
        image = Image.new("RGB", (140, 110), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 70, 40, 100), fill="#009e73")
        draw.rectangle((60, 50, 80, 100), fill="#009e73")
        draw.rectangle((100, 30, 120, 100), fill="#009e73")
        x_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 10, "value": 0}, {"pixel": 130, "value": 3}]}
        )
        y_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 100, "value": 0}, {"pixel": 20, "value": 8}]}
        )
        rows, diagnostics = msf.extract_bars(
            np.asarray(image),
            (10, 20, 130, 100),
            [{"id": "bars", "color": "#009e73", "tolerance": 10, "min_area": 100}],
            x_map,
            y_map,
            {"baseline_pixel": 100},
        )
        self.assertEqual(3, len(rows))
        self.assertTrue(all(float(row["rectangularity"]) >= 0.8 for row in rows))
        self.assertEqual(3, diagnostics["series"][0]["accepted_components"])

    def test_bar_not_touching_baseline_is_rejected(self) -> None:
        image = Image.new("RGB", (100, 100), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 40, 50), fill="#009e73")
        x_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 0, "value": 0}, {"pixel": 99, "value": 1}]}
        )
        y_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 90, "value": 0}, {"pixel": 10, "value": 8}]}
        )
        rows, diagnostics = msf.extract_bars(
            np.asarray(image),
            (0, 0, 99, 99),
            [{"id": "bars", "color": "#009e73", "tolerance": 10, "min_area": 20}],
            x_map,
            y_map,
            {"baseline_pixel": 90},
        )
        self.assertEqual([], rows)
        self.assertGreater(diagnostics["series"][0]["rejected_components"], 0)


if __name__ == "__main__":
    unittest.main()
