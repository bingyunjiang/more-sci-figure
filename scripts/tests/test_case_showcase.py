from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import build_case_showcase as showcase


class CaseShowcaseTests(unittest.TestCase):
    def test_builds_symmetric_no_crop_showcase_from_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.png"
            redraw = root / "redraw.png"
            Image.new("RGB", (800, 400), "white").save(original)
            Image.new("RGB", (400, 800), "white").save(redraw)
            validation = root / "validation.json"
            validation.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "delivery_status": "pass",
                        "stage_statuses": {
                            "extraction_status": "pass",
                            "review_status": "accepted",
                            "render_status": "pass",
                        },
                        "delivery_assessment": {
                            "decision": "accepted",
                            "overall_score": 100,
                            "minimum_dimension_score": 100,
                            "profile": "publication",
                            "qualification_note": "delivery only",
                        },
                    }
                ),
                encoding="utf-8",
            )
            extraction = root / "extraction.json"
            extraction.write_text(
                json.dumps(
                    {
                        "overall_score": 99.4,
                        "minimum_dimension_score": 96,
                        "acceptance": {"profile": "publication"},
                    }
                ),
                encoding="utf-8",
            )
            formal = root / "formal.json"
            formal.write_text(json.dumps({"formal_rows": 1429}), encoding="utf-8")
            args = argparse.Namespace(
                original=original,
                redraw=redraw,
                validation_report=validation,
                extraction_report=extraction,
                formal_data_report=formal,
                out_dir=root / "out",
                stem="case",
                title="Test Fig. 9",
                subtitle="locked versus formal",
                no_png=True,
            )

            report = showcase.build_showcase(args)

            self.assertEqual("symmetric_side_by_side", report["layout"]["mode"])
            self.assertEqual("contain_no_crop", report["layout"]["image_fit"])
            self.assertEqual(100.0, report["scores"]["delivery_score"])
            self.assertEqual(99.4, report["scores"]["extraction_score"])
            self.assertEqual(1429, report["formal_rows"])
            self.assertEqual(
                report["layout"]["embedded_geometry"]["original"]["width"],
                1008,
            )
            self.assertEqual(
                report["layout"]["embedded_geometry"]["redraw"]["height"],
                670,
            )
            svg = (root / "out" / "case.svg").read_text(encoding="utf-8")
            self.assertIn("重绘交付评分  100 / 100", svg)
            self.assertIn("提取评估 99.4 / 100", svg)

    def test_rejects_unreviewed_redraw_as_formal_case(self) -> None:
        with self.assertRaisesRegex(ValueError, "review_status='not_reviewed'"):
            showcase.require_formal_case(
                {
                    "status": "pass",
                    "delivery_status": "pass",
                    "stage_statuses": {
                        "extraction_status": "pass",
                        "review_status": "not_reviewed",
                        "render_status": "pass",
                    },
                    "delivery_assessment": {"decision": "accepted"},
                }
            )


if __name__ == "__main__":
    unittest.main()
