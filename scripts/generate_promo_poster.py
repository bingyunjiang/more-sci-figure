#!/usr/bin/env python3
"""Generate deterministic, evidence-labelled promotional posters."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
EXAMPLES = ROOT / "examples"

CASES = (
    {
        "name": "案例 01 · Figure 10(a)",
        "kind": "多曲线直角坐标图",
        "score": "94.4",
        "source": EXAMPLES / "jiang-2026-figure10a" / "source-image.jpeg",
        "preview": EXAMPLES
        / "jiang-2026-figure10a"
        / "candidate-preview"
        / "candidate-preview.png",
    },
    {
        "name": "案例 02 · Figure 10(b)",
        "kind": "单曲线极坐标图",
        "score": "96.1",
        "source": EXAMPLES / "jiang-2026-figure10b" / "source-image.png",
        "preview": EXAMPLES
        / "jiang-2026-figure10b"
        / "candidate-preview"
        / "candidate-preview.png",
    },
)


def data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def case_card(case: dict[str, object], index: int, x: int, y: int, height: int) -> str:
    source_uri = data_uri(case["source"])  # type: ignore[arg-type]
    preview_uri = data_uri(case["preview"])  # type: ignore[arg-type]
    image_y = y + 150
    image_h = height - 260
    left_x = x + 38
    right_x = x + 566
    image_w = 486
    bottom_y = y + height - 52
    return f'''
  <g filter="url(#cardShadow)">
    <rect x="{x}" y="{y}" width="1090" height="{height}" rx="44" fill="#dfe7f4"/>
    <rect x="{x + 8}" y="{y + 8}" width="1074" height="{height - 16}" rx="37" fill="#ffffff"/>
  </g>
  <circle cx="{x + 58}" cy="{y + 58}" r="25" fill="#155eef"/>
  <text x="{x + 58}" y="{y + 68}" text-anchor="middle" font-size="26" font-weight="760" fill="#ffffff">{index}</text>
  <text x="{x + 102}" y="{y + 58}" font-size="34" font-weight="760" fill="#14213d">{case['name']}</text>
  <text x="{x + 102}" y="{y + 95}" font-size="26" fill="#53627a">{case['kind']}</text>
  <rect x="{x + 824}" y="{y + 34}" width="220" height="70" rx="35" fill="#e9fff8"/>
  <text x="{x + 850}" y="{y + 72}" font-size="21" font-weight="680" fill="#047d6f">AI 评估</text>
  <text x="{x + 1016}" y="{y + 82}" text-anchor="end" font-size="38" font-weight="800" fill="#047d6f">{case['score']}</text>

  <rect x="{left_x}" y="{image_y}" width="{image_w}" height="{image_h}" rx="30" fill="#f4f7fb"/>
  <rect x="{left_x + 8}" y="{image_y + 8}" width="{image_w - 16}" height="{image_h - 16}" rx="24" fill="#ffffff"/>
  <text x="{left_x + 24}" y="{image_y + 42}" font-size="27" font-weight="720" fill="#14213d">论文原图</text>
  <rect x="{left_x + 286}" y="{image_y + 16}" width="176" height="42" rx="21" fill="#eaf1ff"/>
  <text x="{left_x + 374}" y="{image_y + 44}" text-anchor="middle" font-size="20" font-weight="700" fill="#155eef">SOURCE-LOCKED</text>
  <image href="{source_uri}" x="{left_x + 18}" y="{image_y + 70}" width="450" height="{image_h - 92}" preserveAspectRatio="xMidYMid meet"/>

  <path d="M{x + 535} {image_y + image_h / 2 - 10}h28" stroke="#155eef" stroke-width="5" stroke-linecap="round"/>
  <path d="M{x + 554} {image_y + image_h / 2 - 21}l12 11-12 11" fill="none" stroke="#155eef" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>

  <rect x="{right_x}" y="{image_y}" width="{image_w}" height="{image_h}" rx="30" fill="#eefbf7"/>
  <rect x="{right_x + 8}" y="{image_y + 8}" width="{image_w - 16}" height="{image_h - 16}" rx="24" fill="#ffffff"/>
  <text x="{right_x + 24}" y="{image_y + 42}" font-size="27" font-weight="720" fill="#14213d">数据提取并重绘</text>
  <rect x="{right_x + 294}" y="{image_y + 16}" width="168" height="42" rx="21" fill="#fff2e8"/>
  <text x="{right_x + 378}" y="{image_y + 44}" text-anchor="middle" font-size="20" font-weight="700" fill="#b84d20">NOT REVIEWED</text>
  <image href="{preview_uri}" x="{right_x + 18}" y="{image_y + 70}" width="450" height="{image_h - 92}" preserveAspectRatio="xMidYMid meet"/>

  <circle cx="{x + 48}" cy="{bottom_y - 7}" r="7" fill="#ef7b45"/>
  <text x="{x + 68}" y="{bottom_y}" font-size="25" font-weight="650" fill="#763b21">候选预览 · 等待关键异常复核</text>
  <text x="{x + 1046}" y="{bottom_y}" text-anchor="end" font-size="24" fill="#68758b">不宣称恢复原始真值</text>'''


def poster_svg(width: int, height: int) -> str:
    compact = height <= 1200
    header_y = 34 if compact else 42
    title_y = 170 if compact else 190
    cards_y = 286 if compact else 314
    cards_h = 780 if compact else 850
    footer_y = height - 46
    case_a = case_card(CASES[0], 1, 100, cards_y, cards_h)
    case_b = case_card(CASES[1], 2, 1210, cards_y, cards_h)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 2400 {height}" role="img" aria-labelledby="title desc">
<title id="title">More Sci Figure 明亮双案例横版宣传海报</title>
<desc id="desc">AI 先做全量检查，人只看关键处。展示两组论文原图与候选重绘对照。</desc>
<defs>
  <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#fbfdff"/><stop offset="0.55" stop-color="#f7f4ff"/><stop offset="1" stop-color="#effbf8"/>
  </linearGradient>
  <radialGradient id="blueWash"><stop stop-color="#91b8ff" stop-opacity=".36"/><stop offset="1" stop-color="#91b8ff" stop-opacity="0"/></radialGradient>
  <radialGradient id="mintWash"><stop stop-color="#83e4cf" stop-opacity=".34"/><stop offset="1" stop-color="#83e4cf" stop-opacity="0"/></radialGradient>
  <filter id="cardShadow" x="-15%" y="-15%" width="130%" height="140%"><feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#536786" flood-opacity=".16"/></filter>
  <pattern id="dots" width="34" height="34" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.5" fill="#155eef" fill-opacity=".075"/></pattern>
</defs>
<rect width="2400" height="{height}" fill="url(#paper)"/>
<circle cx="240" cy="20" r="450" fill="url(#blueWash)"/>
<circle cx="2220" cy="{height - 70}" r="520" fill="url(#mintWash)"/>
<rect width="2400" height="{height}" fill="url(#dots)"/>

<g font-family="Avenir Next, PingFang SC, Hiragino Sans GB, sans-serif">
  <g transform="translate(104 {header_y})">
    <rect width="410" height="52" rx="26" fill="#155eef"/>
    <circle cx="28" cy="26" r="8" fill="#9ff5df"/>
    <text x="52" y="35" font-size="24" font-weight="730" letter-spacing="2" fill="#ffffff">MORE SCI FIGURE · v0.3.1</text>
  </g>
  <text x="104" y="{title_y}" font-size="82" font-weight="820" letter-spacing="-3" fill="#14213d">AI 全量检查</text>
  <text x="650" y="{title_y}" font-size="82" font-weight="820" letter-spacing="-3" fill="#155eef">｜人只看关键处</text>
  <text x="106" y="{title_y + 61}" font-size="31" font-weight="560" fill="#53627a">从论文图源到可审计候选、科学评判与论文级重绘</text>
  <g transform="translate(1370 {header_y + 8})">
    <rect width="926" height="190" rx="40" fill="#ffffff" stroke="#dce6f5" stroke-width="3"/>
    <rect x="8" y="8" width="910" height="174" rx="33" fill="#eef5ff"/>
    <text x="30" y="43" font-size="22" font-weight="700" fill="#155eef">SKILL 核心功能</text>
    <text x="890" y="43" text-anchor="end" font-size="22" font-weight="700" fill="#047d6f">2 组真实案例 · LOCAL-FIRST</text>
    <g font-size="23" font-weight="670" fill="#23334f">
      <rect x="28" y="62" width="412" height="48" rx="24" fill="#ffffff"/>
      <circle cx="54" cy="86" r="15" fill="#155eef"/><text x="54" y="94" text-anchor="middle" font-size="19" fill="#ffffff">1</text>
      <text x="80" y="94">锁定 PDF / 原始图</text>
      <rect x="464" y="62" width="432" height="48" rx="24" fill="#ffffff"/>
      <circle cx="490" cy="86" r="15" fill="#155eef"/><text x="490" y="94" text-anchor="middle" font-size="19" fill="#ffffff">2</text>
      <text x="516" y="94">提取曲线 / 散点 / 柱形</text>
      <rect x="28" y="122" width="412" height="48" rx="24" fill="#ffffff"/>
      <circle cx="54" cy="146" r="15" fill="#047d6f"/><text x="54" y="154" text-anchor="middle" font-size="19" fill="#ffffff">3</text>
      <text x="80" y="154">七维评分 · 异常优先</text>
      <rect x="464" y="122" width="432" height="48" rx="24" fill="#ffffff"/>
      <circle cx="490" cy="146" r="15" fill="#047d6f"/><text x="490" y="154" text-anchor="middle" font-size="19" fill="#ffffff">4</text>
      <text x="516" y="154">PNG / SVG / PDF 交付</text>
    </g>
  </g>

{case_a}
{case_b}

  <line x1="104" y1="{footer_y - 31}" x2="2296" y2="{footer_y - 31}" stroke="#b8c6da" stroke-width="2"/>
  <text x="104" y="{footer_y}" font-size="25" font-weight="760" fill="#14213d">Dr. Jiang Bingyun</text>
  <text x="365" y="{footer_y}" font-size="25" fill="#52637c">github.com/bingyunjiang/more-sci-figure</text>
  <text x="2296" y="{footer_y}" text-anchor="end" font-size="24" font-weight="650" fill="#155eef">来源锁定 · 候选分离 · 异常优先 · 人工门控</text>
</g>
</svg>'''


def render(svg_path: Path, png_path: Path, width: int, height: int) -> None:
    subprocess.run(
        [
            "/opt/homebrew/bin/rsvg-convert",
            "--width",
            str(width),
            "--height",
            str(height),
            "--output",
            str(png_path),
            str(svg_path),
        ],
        check=True,
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    variants = [
        ("more-sci-figure-promo-16x9", 2400, 1350, 2400, 1350),
        ("more-sci-figure-promo-github-x", 2400, 1200, 1280, 640),
    ]
    for stem, svg_width, svg_height, png_width, png_height in variants:
        svg_path = ASSETS / f"{stem}.svg"
        png_path = ASSETS / f"{stem}.png"
        svg_path.write_text(poster_svg(svg_width, svg_height), encoding="utf-8")
        render(svg_path, png_path, png_width, png_height)
        print(f"generated {svg_path} and {png_path}")


if __name__ == "__main__":
    main()
