#!/usr/bin/env python3
"""more-sci-figure 本地发布验收门。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "pass" if completed.returncode == 0 else "failed",
        "stderr_tail": completed.stderr[-1000:],
    }


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    required = [
        "README.md",
        "CHANGELOG.md",
        "SKILL.md",
        "VERSION",
        "agents/openai.yaml",
        "assets/project-template.json",
        "benchmarks/README.md",
        "references/artifact-contract.md",
        "references/extraction-protocol.md",
        "references/rendering-protocol.md",
        "schemas/project.schema.json",
        "schemas/review-assessment.schema.json",
        "schemas/review-decisions.schema.json",
        "scripts/more_sci_figure.py",
    ]
    structure = {
        "status": "pass" if all((ROOT / path).is_file() for path in required) else "failed",
        "missing": [path for path in required if not (ROOT / path).is_file()],
    }
    version_surfaces = {
        "VERSION": version,
        "SKILL.md": f"当前版本：`{version}`"
        in (ROOT / "SKILL.md").read_text(encoding="utf-8"),
        "README.md": f"版本：v{version}"
        in (ROOT / "README.md").read_text(encoding="utf-8"),
        "CHANGELOG.md": f"## {version} -"
        in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        "python": f'VERSION = "{version}"'
        in (ROOT / "scripts" / "more_sci_figure.py").read_text(encoding="utf-8"),
    }
    version_consistency = {
        "status": (
            "pass"
            if all(value is True for key, value in version_surfaces.items() if key != "VERSION")
            else "failed"
        ),
        "surfaces": version_surfaces,
    }
    expected_history = ["0.3.1", "0.3.0", "0.2.0", "0.1.0"]
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme_positions = [readme_text.find(f"**v{item} ·") for item in expected_history]
    changelog_positions = [changelog_text.find(f"## {item} -") for item in expected_history]
    history_continuity = {
        "status": (
            "pass"
            if all(position >= 0 for position in readme_positions + changelog_positions)
            and readme_positions == sorted(readme_positions)
            and changelog_positions == sorted(changelog_positions)
            else "failed"
        ),
        "expected_descending_versions": expected_history,
        "readme_positions": readme_positions,
        "changelog_positions": changelog_positions,
    }
    tests = run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(ROOT / "scripts" / "tests"),
            "-p",
            "test_*.py",
            "-q",
        ]
    )
    cli = run([sys.executable, str(ROOT / "scripts" / "more_sci_figure.py"), "--version"])
    with tempfile.TemporaryDirectory(prefix="more-sci-figure-acceptance-") as temp:
        output = Path(temp) / "inspect"
        fixture = Path(temp) / "fixture.png"
        from PIL import Image

        Image.new("RGB", (64, 48), "white").save(fixture)
        inspect = run(
            [
                sys.executable,
                str(ROOT / "scripts" / "more_sci_figure.py"),
                "inspect",
                "--input",
                str(fixture),
                "--chart-type",
                "line",
                "--out-dir",
                str(output),
            ]
        )
        inspect["artifacts_present"] = all(
            (output / name).is_file() for name in ("source-report.json", "project.json")
        )
        if not inspect["artifacts_present"]:
            inspect["status"] = "failed"
    help_check = run(
        [
            sys.executable,
            str(ROOT / "scripts" / "more_sci_figure.py"),
            "--help",
        ]
    )
    help_check["contains_chinese"] = "人工复核" in str(
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "more_sci_figure.py"), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        ).stdout
    )
    if not help_check["contains_chinese"]:
        help_check["status"] = "failed"
    checks = {
        "structure": structure,
        "version_consistency": version_consistency,
        "history_continuity": history_continuity,
        "tests": tests,
        "cli": cli,
        "chinese_help": help_check,
        "inspect": inspect,
    }
    status = "pass" if all(check["status"] == "pass" for check in checks.values()) else "failed"
    report = {
        "schema": "more-sci-figure.release-acceptance.v1",
        "version": version,
        "status": status,
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
