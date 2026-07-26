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
        self.assertEqual("awaiting_confirmation", waiting["review"])
        self.assertIn("综合评分", waiting)
        self.assertIn("最低维度分", waiting)
        self.assertEqual("工程分析", waiting["用途等级"])
        self.assertEqual("eligible_for_user_confirmation", waiting["判定"])
        self.assertTrue(waiting["硬门通过"])
        self.assertEqual("batch_confirm", waiting["建议动作"])
        self.assertEqual("not_run", waiting["render"])
        self.assertTrue((output / "candidates.csv").is_file())
        self.assertTrue((output / "review.html").is_file())
        self.assertTrue((output / "review-assessment.json").is_file())
        self.assertTrue((output / "review-anomalies.csv").is_file())
        review_html = (output / "review.html").read_text(encoding="utf-8")
        self.assertIn("AI 综合评判", review_html)
        self.assertIn("用途等级", review_html)
        self.assertIn("合格线", review_html)
        self.assertIn("当前最低维度", review_html)
        self.assertIn("下一步指令", review_html)
        self.assertIn("坐标标定质量", review_html)
        self.assertIn("普通候选可批量确认", review_html)
        self.assertIn("异常候选独立复核", review_html)
        self.assertIn("普通候选批量区", review_html)
        self.assertIn("普通候选批量确认", review_html)
        self.assertIn("id='confirm-assessment-anomalies'", review_html)
        self.assertIn("id='confirm-assessment'", review_html)
        self.assertIn('fetch("/api/review-confirm"', review_html)
        self.assertIn("接受全部异常项", review_html)
        self.assertIn("拒绝全部异常项", review_html)
        self.assertIn("普通候选全部接受", review_html)
        self.assertIn("decision-summary", review_html)
        self.assertIn("decision-toast", review_html)
        self.assertIn("待决策", review_html)
        self.assertIn("decision-accepted", review_html)
        self.assertIn("decision-rejected", review_html)
        self.assertIn("export-result", review_html)
        self.assertIn("生成完整复核文件（下一步）", review_html)
        self.assertIn('id="reviewed-by" required aria-required="true"', review_html)
        self.assertIn('id="export" disabled', review_html)
        self.assertIn("export-readiness", review_html)
        self.assertIn("正在生成 ${index}/${decisionSelects.length}", review_html)
        self.assertIn("requestAnimationFrame", review_html)
        self.assertIn("confirm-uncertain", review_html)
        self.assertIn("confirm-export-scope", review_html)
        self.assertIn("必须填写复核人", review_html)
        self.assertNotIn("alert(", review_html)
        self.assertNotIn("confirm(", review_html)
        self.assertIn("只有 Agent 成功应用复核后才会生成正式", review_html)
        self.assertIn("保存到当前项目目录", review_html)
        self.assertIn("复制复核 JSON", review_html)
        self.assertIn('fetch("/api/review-decisions"', review_html)
        self.assertIn("X-Review-Token", review_html)
        self.assertIn("需由 Agent 启动本地复核会话", review_html)
        self.assertNotIn("showSaveFilePicker", review_html)
        self.assertIn("保存成功", review_html)
        self.assertNotIn("new Blob", review_html)
        self.assertNotIn("URL.createObjectURL", review_html)
        self.assertNotIn("showModal", review_html)
        self.assertIn("复制完整管线 Agent 任务语句", review_html)
        self.assertIn("复制仅应用复核 Agent 任务语句", review_html)
        self.assertIn("请使用 more-sci-figure skill", review_html)
        self.assertIn("Codex、Claude Code、Hermes", review_html)
        self.assertIn("不要假定固定文件名或固定路径", review_html)
        self.assertIn("不得为寻找文件而扫描整个用户磁盘", review_html)
        self.assertIn("如果复核 JSON、候选文件或项目规格没有唯一匹配", review_html)
        self.assertNotIn(str(output), review_html)
        self.assertNotIn("python3 ", review_html)
        self.assertIn("不会自动保存文件", review_html)
        self.assertLess(
            review_html.index('id="export"'),
            review_html.index("<table>"),
        )
        self.assertIn("校正坐标", review_html)
        self.assertIn("重新归属", review_html)
        self.assertGreater(review_html.index('id="reviewed-by"'), review_html.index("异常候选独立复核"))
        template = msf.read_json(output / "review-template.json")
        self.assertTrue(all(item["decision"] == "accepted" for item in template["decisions"]))
        self.assertEqual("line-fixture", template["project_id"])
        self.assertIn("source_sha256", template)
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

    def test_ai_assessment_supports_conversational_batch_confirmation(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)

        assessment = msf.review_assess_command(output)
        self.assertEqual("pass", assessment["status"])
        self.assertEqual("batch_confirm", assessment["recommended_action"])
        assessment_payload = msf.read_json(output / "review-assessment.json")
        self.assertEqual(7, len(assessment_payload["scorecard"]["dimensions"]))
        self.assertEqual("engineering", assessment_payload["acceptance"]["profile"])
        self.assertEqual(90.0, assessment_payload["acceptance"]["thresholds"]["overall_score"])
        self.assertEqual(
            85.0,
            assessment_payload["acceptance"]["thresholds"]["minimum_dimension_score"],
        )
        self.assertTrue(assessment_payload["acceptance"]["hard_gates_pass"])
        self.assertEqual(
            "eligible_for_user_confirmation",
            assessment_payload["acceptance"]["decision"],
        )
        self.assertGreaterEqual(assessment_payload["minimum_dimension_score"], 85.0)
        self.assertTrue(assessment_payload["acceptance"]["next_instruction"])
        self.assertTrue((output / "review-assessment.json").is_file())
        self.assertTrue((output / "review-anomalies.csv").is_file())
        manifest_before = msf.read_json(output / "manifest.json")
        self.assertEqual("not_run", manifest_before["review_status"])

        confirmation = msf.review_confirm_command(output, "Dr.Jiang", "下一步")
        self.assertEqual("ai_assisted_batch_confirmation", confirmation["review_method"])
        self.assertEqual("saved", confirmation["save_status"])
        self.assertFalse(confirmation["applied"])
        decisions = msf.read_json(output / "review-decisions.json")
        self.assertEqual(len(msf.read_tabular_rows(output / "candidates.csv")), len(decisions["decisions"]))
        self.assertTrue(all(item["decision"] == "accepted" for item in decisions["decisions"]))
        self.assertEqual("下一步", decisions["conversation_confirmation"])
        self.assertTrue(decisions["anomaly_acknowledgement"]["confirmed"])
        self.assertEqual(
            assessment["anomaly_count"],
            decisions["anomaly_acknowledgement"]["candidate_count"],
        )
        self.assertEqual("下一步", decisions["anomaly_acknowledgement"]["confirmation"])
        self.assertFalse((output / "data.csv").exists())

        ready = msf.review_assess_command(output)
        self.assertEqual("apply_review", ready["recommended_action"])
        self.assertEqual("review_record_ready", ready["acceptance_decision"])
        review_page = msf.review_command(output)
        self.assertIn("应用", review_page["下一步"])

        applied = msf.review_apply_command(output, output / "review-decisions.json")
        self.assertEqual("accepted", applied["review_status"])
        normalized = msf.read_json(output / "review-decisions.json")
        self.assertEqual("ai_assisted_batch_confirmation", normalized["review_method"])
        self.assertIn("assessment_sha256", normalized)
        self.assertTrue(normalized["anomaly_acknowledgement"]["confirmed"])

    def test_anomalies_are_reviewed_separately_from_normal_batch(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        candidates = msf.read_tabular_rows(output / "candidates.csv")
        anomaly_candidate = candidates[0]
        anomaly_id = str(anomaly_candidate["candidate_id"])
        msf.write_csv(
            output / "review-anomalies.csv",
            [
                {
                    "candidate_id": anomaly_id,
                    "series": anomaly_candidate["series"],
                    "severity": "medium",
                    "anomaly_type": "guide_residual_outlier",
                    "observed": "6.2",
                    "reason": "测试异常候选必须独立复核",
                    "recommended_action": "batch_review",
                }
            ],
        )
        assessment = msf.read_json(output / "review-assessment.json")
        assessment["recommended_action"] = "batch_confirm"
        assessment["anomaly_groups"]["guide_residual_outlier"] = 1
        msf.write_json(output / "review-assessment.json", assessment)

        msf.review_command(output)
        review_html = (output / "review.html").read_text(encoding="utf-8")
        self.assertIn('id="anomaly-decisions"', review_html)
        self.assertIn('id="normal-decisions"', review_html)
        self.assertIn("data-anomaly='true'", review_html)
        self.assertIn("data-anomaly='false'", review_html)
        self.assertIn("evidence-crop", review_html)
        self.assertIn("测试异常候选必须独立复核", review_html)
        self.assertIn("仍有 ${anomalyPending} 个异常候选待独立决策", review_html)
        template = msf.read_json(output / "review-template.json")
        decision_by_id = {item["candidate_id"]: item["decision"] for item in template["decisions"]}
        self.assertEqual("anomaly_first_split_review", template["review_method"])
        self.assertEqual(1, template["anomaly_review"]["candidate_count"])
        self.assertEqual([anomaly_id], template["anomaly_review"]["candidate_ids"])
        self.assertTrue(template["anomaly_review"]["separated_from_normal_batch"])
        self.assertEqual("pending", decision_by_id[anomaly_id])
        self.assertTrue(
            all(
                decision == "accepted"
                for candidate_id, decision in decision_by_id.items()
                if candidate_id != anomaly_id
            )
        )
        with self.assertRaisesRegex(msf.FigureError, "必须先在独立异常复核区逐项处理"):
            msf.review_confirm_command(output, "Dr.Jiang", "下一步")

    def test_ai_batch_confirmation_stops_on_critical_source_issue(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        project = msf.read_json(output / "project.json")
        project["source"]["path"] = "missing-source.png"
        msf.write_json(output / "project.json", project)
        original_project = msf.read_json(spec_path)
        original_project["source"]["path"] = "missing-source.png"
        msf.write_json(spec_path, original_project)

        assessment = msf.review_assess_command(output)
        self.assertEqual("attention_required", assessment["status"])
        self.assertEqual("critical", assessment["risk_level"])
        self.assertEqual("stop", assessment["recommended_action"])
        with self.assertRaisesRegex(msf.FigureError, "不得一键批量确认"):
            msf.review_confirm_command(output, "Dr.Jiang", "继续")
        self.assertFalse((output / "review-decisions.json").exists())

    def test_publication_profile_requires_a_higher_dimension_floor(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["assessment"] = {"acceptance_profile": "publication"}
        msf.write_json(spec_path, spec)
        output = self.root / "evidence"

        msf.extract_command(spec_path, output)
        assessment = msf.read_json(output / "review-assessment.json")

        self.assertEqual("publication", assessment["acceptance"]["profile"])
        self.assertEqual(95.0, assessment["acceptance"]["thresholds"]["overall_score"])
        self.assertEqual(
            90.0, assessment["acceptance"]["thresholds"]["minimum_dimension_score"]
        )
        self.assertFalse(assessment["acceptance"]["dimension_floor_pass"])
        self.assertEqual("not_qualified", assessment["acceptance"]["decision"])
        self.assertEqual("re_extract", assessment["recommended_action"])
        review_page = msf.review_command(output)
        self.assertIn("重新提取", review_page["下一步"])
        self.assertNotIn("批量确认", review_page["下一步"])

    def test_extract_rebases_relative_source_paths_in_project_copy(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["source"]["path"] = "line.png"
        spec["source"]["measurement_raster"] = "line.png"
        msf.write_json(spec_path, spec)
        output = self.root / "nested" / "evidence"

        msf.extract_command(spec_path, output)

        copied_path = output / "project.json"
        copied = msf.read_json(copied_path)
        self.assertEqual(
            (self.root / "line.png").resolve(),
            msf.resolve_from(copied_path, copied["source"]["path"]),
        )
        self.assertEqual(
            (self.root / "line.png").resolve(),
            msf.resolve_from(copied_path, copied["source"]["measurement_raster"]),
        )
        assessment = msf.read_json(output / "review-assessment.json")
        self.assertEqual("batch_confirm", assessment["recommended_action"])

    def test_validate_uses_the_actual_project_spec_recorded_by_render(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        msf.review_apply_command(output, self.decisions_for(output))
        stale_copy = msf.read_json(output / "project.json")
        stale_copy["source"]["path"] = "missing-source.png"
        msf.write_json(output / "project.json", stale_copy)

        msf.render_command(spec_path, output / "data.csv", output / "render")
        validation = msf.validate_command(output, self.root / "line.png")

        self.assertEqual("pass", validation["status"])
        self.assertEqual("pass", validation["delivery_status"])
        manifest = msf.read_json(output / "manifest.json")
        self.assertEqual(str(spec_path.resolve()), manifest["artifacts"]["project_spec"]["path"])
        self.assertIn("extraction_project_spec", manifest["artifacts"])

    def test_review_save_uses_fixed_project_path_without_advancing_status(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        payload = msf.read_json(self.decisions_for(output))
        manifest_before = msf.read_json(output / "manifest.json")

        result = msf.save_review_decisions_command(output, payload)

        fixed_path = output.resolve() / "review-decisions.json"
        self.assertEqual(str(fixed_path), result["saved_path"])
        self.assertEqual("saved", result["save_status"])
        self.assertEqual("not_run", result["review_status"])
        self.assertFalse(result["applied"])
        self.assertTrue(fixed_path.is_file())
        self.assertEqual(digest(fixed_path), result["sha256"])
        self.assertEqual(manifest_before, msf.read_json(output / "manifest.json"))
        self.assertFalse((output / "data.csv").exists())

    def test_review_save_rejects_tampered_candidate_hash(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        payload = msf.read_json(self.decisions_for(output))
        payload["candidate_sha256"] = "0" * 64

        with self.assertRaisesRegex(msf.FigureError, "哈希"):
            msf.save_review_decisions_command(output, payload)

        self.assertFalse((output / "review-decisions.json").exists())

    def test_review_save_does_not_overwrite_applied_evidence(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions_path = self.decisions_for(output)
        payload = msf.read_json(decisions_path)
        msf.review_apply_command(output, decisions_path)
        applied_hash = digest(output / "review-decisions.json")

        with self.assertRaisesRegex(msf.FigureError, "保护证据链"):
            msf.save_review_decisions_command(output, payload)

        self.assertEqual(applied_hash, digest(output / "review-decisions.json"))

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

    def test_review_can_correct_coordinates_and_reassign_series_with_provenance(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["chart"]["series"].append(
            {"id": "alternate", "color": "#0072b2", "tolerance": 15}
        )
        msf.write_json(spec_path, spec)
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        decisions_path = self.decisions_for(output, set())
        payload = msf.read_json(decisions_path)
        first, second = payload["decisions"][:2]
        original_rows = msf.read_tabular_rows(output / "candidates.csv")
        first["decision"] = "corrected"
        first["corrected_y"] = float(original_rows[0]["y"]) + 0.25
        first["reason"] = "人工按证据叠图校正"
        second["decision"] = "reassigned"
        second["target_series"] = "alternate"
        second["reason"] = "颜色分支归属修正"
        msf.write_json(decisions_path, payload)
        result = msf.review_apply_command(output, decisions_path)
        promoted = msf.read_tabular_rows(output / "data.csv")
        self.assertEqual(1, result["corrected"])
        self.assertEqual(1, result["reassigned"])
        self.assertEqual(2, len(promoted))
        corrected = next(row for row in promoted if row["review_decision"] == "corrected")
        reassigned = next(row for row in promoted if row["review_decision"] == "reassigned")
        self.assertIn("original_y", corrected)
        self.assertEqual("alternate", reassigned["series"])
        self.assertEqual("trend", reassigned["original_series"])
        render = msf.render_command(
            spec_path, output / "data.csv", output / "render"
        )
        self.assertEqual("pass", render["status"])

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

    def test_invalid_component_and_display_geometry_settings_are_rejected(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["quality_gates"]["scatter"] = {"min_accepted_components": 0}
        spec["render"]["display_geometry"] = {
            "mode": "invented",
            "max_bridge_gap_px": -1,
        }
        spec["render"]["canvas_px"] = [220, 140]
        spec["render"]["axes_box_px"] = [20, 15, 260, 115]
        errors = msf.validate_spec(spec, spec_path)
        self.assertTrue(any("min_accepted_components" in error for error in errors))
        self.assertTrue(any("display_geometry.mode" in error for error in errors))
        self.assertTrue(any("max_bridge_gap_px" in error for error in errors))
        self.assertTrue(any("canvas_px 内" in error for error in errors))

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

    def test_guided_path_separates_same_colour_curves_and_ignores_local_legend(self) -> None:
        image = Image.new("RGB", (220, 140), "white")
        draw = ImageDraw.Draw(image)
        draw.line((20, 112, 200, 62), fill="#d62728", width=3)
        for start in range(20, 198, 14):
            end = min(start + 8, 200)
            draw.line(
                (start, 108 - 0.42 * (start - 20), end, 108 - 0.42 * (end - 20)),
                fill="#d62728",
                width=3,
            )
        draw.line((132, 100, 178, 100), fill="#d62728", width=4)
        x_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 20, "value": 0}, {"pixel": 200, "value": 1}]}
        )
        y_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 120, "value": 0}, {"pixel": 20, "value": 1}]}
        )
        series = [
            {
                "id": "solid",
                "color": "#d62728",
                "tolerance": 12,
                "extraction_mode": "guided_path",
                "shared_color_group": "red",
                "guide_corridor_px": 5,
                "guide_points_px": [[20, 112], [200, 62]],
                "exclude_boxes_px": [[132, 96, 178, 104]],
            },
            {
                "id": "dash",
                "color": "#d62728",
                "tolerance": 12,
                "extraction_mode": "guided_path",
                "shared_color_group": "red",
                "guide_corridor_px": 5,
                "guide_points_px": [[20, 108], [200, 32.4]],
                "exclude_boxes_px": [[132, 96, 178, 104]],
            },
        ]
        rows, diagnostics = msf.extract_line(
            np.asarray(image), (10, 15, 210, 125), series, x_map, y_map
        )
        grouped = {
            series_id: [row for row in rows if row["series"] == series_id]
            for series_id in ("solid", "dash")
        }
        self.assertGreater(len(grouped["solid"]), 150)
        self.assertGreater(len(grouped["dash"]), 85)
        late_solid = [float(row["pixel_y"]) for row in grouped["solid"] if row["pixel_x"] > 170]
        late_dash = [float(row["pixel_y"]) for row in grouped["dash"] if row["pixel_x"] > 170]
        self.assertGreater(float(np.mean(late_solid)) - float(np.mean(late_dash)), 18)
        self.assertTrue(any(row["evidence_status"] == "ambiguous_shared_colour" for row in rows))
        self.assertEqual(
            [[132, 96, 178, 104]], diagnostics["series"][0]["applied_exclusions_px"]
        )

    def test_global_guided_group_assigns_each_colour_cluster_exclusively(self) -> None:
        image = Image.new("RGB", (220, 140), "white")
        draw = ImageDraw.Draw(image)
        draw.line((20, 112, 200, 62), fill="#d62728", width=3)
        for start in range(20, 198, 14):
            end = min(start + 8, 200)
            draw.line(
                (start, 108 - 0.42 * (start - 20), end, 108 - 0.42 * (end - 20)),
                fill="#d62728",
                width=3,
            )
        x_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 20, "value": 0}, {"pixel": 200, "value": 1}]}
        )
        y_map = msf.AxisMap(
            {"scale": "linear", "anchors": [{"pixel": 120, "value": 0}, {"pixel": 20, "value": 1}]}
        )
        common = {
            "color": "#d62728",
            "tolerance": 12,
            "extraction_mode": "guided_group_path",
            "shared_color_group": "red",
            "guide_corridor_px": 5,
            "guide_interpolation": "shape_preserving",
        }
        rows, diagnostics = msf.extract_line(
            np.asarray(image),
            (10, 15, 210, 125),
            [
                {
                    **common,
                    "id": "solid",
                    "line_semantics": "solid",
                    "guide_points_px": [[20, 112], [100, 90], [200, 62]],
                },
                {
                    **common,
                    "id": "dash",
                    "line_semantics": "dashed",
                    "guide_points_px": [[20, 108], [100, 74.4], [200, 32.4]],
                },
            ],
            x_map,
            y_map,
        )
        pairs = [(int(row["pixel_x"]), float(row["pixel_y"])) for row in rows]
        self.assertEqual(len(pairs), len(set(pairs)))
        grouped = {
            series_id: [row for row in rows if row["series"] == series_id]
            for series_id in ("solid", "dash")
        }
        self.assertGreater(len(grouped["solid"]), 160)
        self.assertGreater(len(grouped["dash"]), 70)
        self.assertLess(len(grouped["dash"]), len(grouped["solid"]))
        self.assertTrue(
            any(
                row["evidence_status"] == "model_assisted_exclusive_assignment"
                for row in rows
            )
        )
        by_id = {item["id"]: item for item in diagnostics["series"]}
        self.assertEqual("solid", by_id["solid"]["line_semantics"])
        self.assertGreater(by_id["dash"]["maximum_gap_columns"], 0)

    def test_display_geometry_only_bridges_an_explicitly_bounded_gap(self) -> None:
        rows = [
            {"x": 0, "y": 0, "pixel_x": 10, "segment_break": True},
            {"x": 1, "y": 1, "pixel_x": 11, "segment_break": False},
            {"x": 3, "y": 2, "pixel_x": 14, "segment_break": True},
            {"x": 4, "y": 3, "pixel_x": 15, "segment_break": False},
        ]
        preserved = msf.display_segments(
            rows,
            "x",
            "y",
            mode="none",
            smoothing_window=1,
            samples_per_interval=1,
            max_bridge_gap_px=0,
        )
        bridged = msf.display_segments(
            rows,
            "x",
            "y",
            mode="shape_preserving",
            smoothing_window=1,
            samples_per_interval=4,
            max_bridge_gap_px=3,
        )
        self.assertEqual(2, len(preserved))
        self.assertEqual(1, len(bridged))
        self.assertGreater(len(bridged[0][0]), len(rows))
        self.assertEqual(0, bridged[0][0][0])
        self.assertEqual(4, bridged[0][0][-1])

    def test_display_geometry_rejects_pixel_outlier_and_reports_retained_knots(self) -> None:
        rows = [
            {"x": index, "y": value, "pixel_x": 10 + index, "pixel_y": pixel_y, "segment_break": index == 0}
            for index, (value, pixel_y) in enumerate(
                [(0, 100), (1, 99), (50, 50), (3, 97), (4, 96)]
            )
        ]
        segments = msf.display_segments(
            rows,
            "x",
            "y",
            mode="shape_preserving",
            smoothing_window=1,
            samples_per_interval=2,
            max_bridge_gap_px=0,
            outlier_window=3,
            max_outlier_pixel_residual=5,
            knot_stride=1,
        )
        _, dense_y, source_count, retained_count, _ = segments[0]
        self.assertEqual(5, source_count)
        self.assertEqual(4, retained_count)
        self.assertLess(float(np.max(dense_y)), 10)

    def test_guide_constrained_geometry_is_dense_and_keeps_observation_count(self) -> None:
        chart = {
            "plot_box": [20, 20, 200, 110],
            "x_axis": {
                "scale": "linear",
                "anchors": [{"pixel": 20, "value": 0}, {"pixel": 200, "value": 10}],
            },
            "y_axis": {
                "scale": "linear",
                "anchors": [{"pixel": 110, "value": 0}, {"pixel": 30, "value": 8}],
            },
        }
        entry = {
            "id": "trend",
            "guide_interpolation": "shape_preserving",
            "guide_points_px": [[20, 110], [100, 72], [200, 30]],
        }
        rows = [
            {"pixel_x": 20, "pixel_y": 109, "x": 0, "y": 0.1},
            {"pixel_x": 100, "pixel_y": 73, "x": 4.4, "y": 3.7},
            {"pixel_x": 200, "pixel_y": 31, "x": 10, "y": 7.9},
        ]
        display_x, display_y, source_count, retained_count, derived_count = (
            msf.guide_constrained_display_geometry(
                entry,
                rows,
                chart,
                maximum_residual_px=5,
                residual_smoothing_window=5,
            )
        )
        self.assertEqual(3, source_count)
        self.assertEqual(3, retained_count)
        self.assertEqual(181, derived_count)
        self.assertEqual(181, len(display_x))
        self.assertTrue(np.all(np.isfinite(display_y)))

    def test_fixed_canvas_and_derived_display_geometry_are_auditable(self) -> None:
        spec_path = self.make_line_project()
        spec = msf.read_json(spec_path)
        spec["render"].update(
            {
                "canvas_px": [220, 140],
                "dpi": 100,
                "axes_box_px": [20, 15, 205, 115],
                "display_geometry": {
                    "mode": "shape_preserving",
                    "smoothing_window": 5,
                    "samples_per_interval": 3,
                    "max_bridge_gap_px": 0,
                },
            }
        )
        msf.write_json(spec_path, spec)
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        msf.review_apply_command(output, self.decisions_for(output))
        observed_rows = msf.read_tabular_rows(output / "data.csv")
        report = msf.render_command(spec_path, output / "data.csv", output / "render")
        with Image.open(output / "render" / "render.png") as rendered:
            self.assertEqual((220, 140), rendered.size)
        self.assertGreater(report["display_geometry"]["rows"], len(observed_rows))
        self.assertEqual(len(observed_rows), len(msf.read_tabular_rows(output / "data.csv")))
        display_rows = msf.read_tabular_rows(output / "render" / "display-geometry.csv")
        self.assertTrue(
            all(row["provenance"] == "derived_display_geometry" for row in display_rows)
        )

    def test_candidate_preview_never_promotes_or_updates_manifest(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        manifest_before = msf.read_json(output / "manifest.json")
        report = msf.preview_command(
            spec_path, output / "candidates.csv", output / "candidate-preview"
        )
        manifest_after = msf.read_json(output / "manifest.json")
        self.assertFalse(report["formal_render"])
        self.assertEqual("unreviewed_candidates", report["input_status"])
        self.assertEqual(manifest_before, manifest_after)
        self.assertFalse((output / "data.csv").exists())
        self.assertTrue(
            (output / "candidate-preview" / "candidate-preview.png").is_file()
        )

    def test_formal_render_rejects_unreviewed_candidates(self) -> None:
        spec_path = self.make_line_project()
        output = self.root / "evidence"
        msf.extract_command(spec_path, output)
        with self.assertRaisesRegex(msf.FigureError, "未复核候选"):
            msf.render_command(
                spec_path, output / "candidates.csv", output / "render"
            )

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
        delivery_assessment = validation["delivery_assessment"]
        self.assertEqual("accepted", delivery_assessment["decision"])
        self.assertEqual(4, len(delivery_assessment["dimensions"]))
        self.assertEqual(100.0, delivery_assessment["overall_score"])
        self.assertTrue(delivery_assessment["hard_gates_pass"])

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
        self.assertEqual("blocked", validation["delivery_assessment"]["decision"])
        self.assertFalse(validation["delivery_assessment"]["hard_gates_pass"])
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

    def test_inspect_can_lock_original_pdf_embedded_raster(self) -> None:
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF unavailable")
        raster = self.root / "embedded.png"
        Image.new("RGB", (73, 41), "#d62728").save(raster)
        pdf = self.root / "embedded.pdf"
        document = fitz.open()
        page = document.new_page(width=200, height=120)
        page.insert_image(fitz.Rect(20, 20, 166, 102), filename=str(raster))
        document.save(pdf)
        document.close()
        evidence = self.root / "pdf-evidence"

        msf.inspect_command(
            pdf,
            "line",
            evidence,
            1,
            pdf_image_index=0,
        )

        report = msf.read_json(evidence / "source-report.json")
        measurement = report["measurement_raster"]
        self.assertEqual("pdf_embedded_raster", measurement["measurement_kind"])
        self.assertEqual([73, 41], [measurement["width"], measurement["height"]])
        self.assertIsInstance(measurement["pdf_xref"], int)
        project = msf.read_json(evidence / "project.json")
        locked = (evidence / project["source"]["measurement_raster"]).resolve()
        self.assertTrue(locked.is_file())
        self.assertEqual(digest(locked), project["source"]["measurement_sha256"])

    def test_polar_line_extractor_produces_overlay_and_redraw(self) -> None:
        source = self.root / "polar.png"
        image = Image.new("RGB", (240, 240), "white")
        draw = ImageDraw.Draw(image)
        center = (120.0, 120.0)
        points: list[tuple[float, float]] = []
        for angle in range(361):
            radius = 60.0 + 10.0 * np.cos(np.deg2rad(3.0 * angle))
            radians = np.deg2rad(angle)
            points.append(
                (
                    center[0] + radius * np.cos(radians),
                    center[1] + radius * np.sin(radians),
                )
            )
        draw.line(points, fill="#d62728", width=3, joint="curve")
        image.save(source)
        spec = {
            "schema": msf.SCHEMA,
            "project_id": "polar-fixture",
            "source": {
                "path": str(source),
                "sha256": digest(source),
                "page": None,
                "measurement_raster": str(source),
                "measurement_sha256": digest(source),
            },
            "chart": {
                "type": "polar_line",
                "plot_box": [20, 20, 220, 220],
                "polar": {
                    "center_px": [120, 120],
                    "angle_axis": {
                        "unit": "degree",
                        "zero_bearing_deg": 0,
                        "direction": "clockwise",
                        "anchors": [
                            {"pixel": [200, 120], "value": 0},
                            {"pixel": [120, 200], "value": 90},
                            {"pixel": [40, 120], "value": 180},
                            {"pixel": [120, 40], "value": 270},
                        ],
                    },
                    "radius_axis": {
                        "scale": "linear",
                        "anchors": [
                            {"pixel": 30, "value": 30},
                            {"pixel": 60, "value": 60},
                            {"pixel": 90, "value": 90},
                        ],
                    },
                    "inner_radius_px": 25,
                    "outer_radius_px": 95,
                    "angle_start_deg": 0,
                    "angle_end_deg": 360,
                    "angle_step_deg": 1,
                },
                "series": [
                    {
                        "id": "directivity",
                        "color": "#d62728",
                        "color_space": "lab",
                        "tolerance": 8,
                        "extraction_mode": "polar_radial",
                        "angular_half_width_deg": 0.8,
                    }
                ],
            },
            "quality_gates": {
                "calibration": {"require_three_anchors": True, "max_normalized_rmse": 0.001},
                "polar_line": {"min_coverage": 0.95, "max_gap_fraction": 0.03},
            },
            "render": {
                "plot_type": "polar_line",
                "x": "x",
                "y": "y",
                "group": "series",
                "x_ticks": list(range(0, 360, 45)),
                "y_limits": [20, 80],
                "y_ticks": [30, 40, 50, 60, 70, 80],
                "series_styles": {"directivity": {"color": "#d62728"}},
            },
        }
        spec_path = self.root / "polar-project.json"
        msf.write_json(spec_path, spec)
        evidence = self.root / "polar-evidence"

        report = msf.extract_command(spec_path, evidence)

        self.assertEqual("pass", report["status"])
        self.assertGreater(report["rows"], 340)
        self.assertTrue((evidence / "overlay.png").is_file())
        candidates = msf.read_tabular_rows(evidence / "candidates.csv")
        angle_zero = min(candidates, key=lambda row: abs(float(row["x"])))
        self.assertAlmostEqual(70.0, float(angle_zero["y"]), delta=2.0)
        preview = msf.preview_command(
            evidence / "project.json",
            evidence / "candidates.csv",
            evidence / "candidate-preview",
        )
        self.assertEqual("polar_line", preview["plot_type"])
        self.assertTrue((evidence / "candidate-preview" / "candidate-preview.svg").is_file())

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
