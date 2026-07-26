[![Codex](https://img.shields.io/badge/Codex-Skill-0B1120?logo=openai&logoColor=white)](https://github.com/bingyunjiang/more-paper-workflow)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-6B46F7?logo=anthropic&logoColor=white)](https://github.com/bingyunjiang/more-paper-workflow)
[![Hermes](https://img.shields.io/badge/Hermes-Skill-FF6B35?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyem0tMSAxNy45M2MtMy45NS0uNDktNy0zLjg1LTctNy45MyAwLS40NC4wNC0uODcuMTEtMS4yOWwxLjg4IDEuODhjLjEuMTEuMjYuMjYuNDcuNDQgMi4yMiAxLjk3IDMuMjYgMi44NyAzLjI2IDIuODcuMjYgMCAuNTItLjEzLjc4LS4zOSAxLjI2LTEuMjYgMS4xMi0zLjI5LS4zMy00Ljg2bC0xLjg5LTEuODljLS4yMi0uMjItLjMzLS4zMy0uNDQtLjQ0LS40Ny0uNDctLjQ3LTEuMjQgMC0xLjcxLjQ3LS40NyAxLjI0LS40NyAxLjcxIDBsLjQ0LjQ0Yy4wMi4wMi4wNC4wNCAxLjQyIDEuNDJsLjIyLS4wNGMxLjY4LS4zMSAzLjI0LjQ2IDMuOTcgMi4wMi0xLjU5IDEuMTktMy4yOSAxLjg5LTQuOTcgMi4wOHoiLz48L3N2Zz4=)](https://github.com/nousresearch/hermes-skills)
(https://github.com/openclaw/openclaw)
[![Platform](https://img.shields.io/badge/macOS_|_Windows_|_Linux-lightgrey?logo=apple)]()
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg)](requirements.txt)
[![License: MIT](https://img.shields.io/badge/License-MIT-16844b.svg)]

> **作者：** Dr. Jiang Bingyun　|　**微信：** Bingyunjiang　|　**邮箱：** bingyunjiang@qq.com
>  **GitHub：** [bingyunjiang/more-sci-figure](https://github.com/bingyunjiang/more-sci-figure)


# More Sci Figure

本地优先、证据可追溯的科研图表数据提取、人工复核、论文级重绘与交付验证工具。
版本：v0.3.1
**关键词：** 科研图表数字化 · 同色曲线分离 · 引导路径 · 曲线/散点/柱图提取 · 人工复核 · 候选预览 · 论文级重绘 · PNG/SVG/PDF · 哈希证据链 · 本地优先

> 核心原则：算法检测到的只是候选值。只有经过哈希绑定的人工复核，候选值才能进入正式 `data.csv`。

| 关键词 | 链接 |
| --- | --- |
| 功能总览 | [功能总览](#功能总览) |
| 详细操作图 | [标准工作流与人工门控](#标准工作流与人工门控) |
| 快速使用 | [快速开始](#快速开始) |
| 完整流程 | [标准工作流与人工门控](#标准工作流与人工门控) |
| 命令行 | [CLI 命令](#cli-命令) |
| 输入与输出 | [输入与交付物](#输入与交付物) |
| 项目配置 | [项目规格与质量门](#项目规格与质量门) |
| 科研可信度 | [证据边界与拒绝条件](#证据边界与拒绝条件) |
| 测试 | [开发与验收](#开发与验收) |
| 版本历史 | [版本历史](#版本历史) |
| 版本计划 | [路线图](#路线图) |
| 许可证 | [MIT License](#许可证) |
| 变更记录 | [CHANGELOG.md](CHANGELOG.md) |

## 功能总览

[![More Sci Figure 功能总览图](assets/more-sci-figure-overview.svg)](https://github.com/bingyunjiang/more-sci-figure)

总览图用于快速理解该 skill 的输入、核心能力与交付结果，包含两条入口：

- **图片 / PDF 证据提取：** 必须依次经过来源锁定、项目规格确认、候选提取、自动质量门、哈希绑定的人工复核、重绘与交付验证。
- **外部结构化数据直接重绘：** CSV、TSV、JSON、XLSX 或 XLSM 规范化为 `data.csv` 后进入重绘；此时提取与人工复核状态明确记录为 `not_applicable`。

四类状态相互独立：`extraction_status`、`review_status`、`render_status` 和 `delivery_status`。重绘成功不能提升不确定的提取或复核状态。

## 功能亮点

### 1. 来源不可静默替换

检查阶段记录原始文件 SHA-256、尺寸、PDF 页码、DPI 和测量栅格哈希。后续运行发现来源变化时会拒绝提取。

### 2. 候选值与正式值分离

```text
原图 → candidates.csv → 人工复核 → data.csv → 重绘
```

算法结果先写入 `candidates.csv`。复核决定必须覆盖全部候选编号并绑定候选文件 SHA-256；只有明确接受的记录会进入 `data.csv`。

### 3. AI 综合评判与异常优先

`extract` 自动融合来源完整性、候选哈希、坐标标定残差、质量门、逐系列覆盖率、最大缺口、引导残差、像素支持和模型辅助比例，生成 `review-assessment.json` 与 `review-anomalies.csv`。普通候选进入独立批量区；异常候选进入单独复核区，逐项显示原始分辨率局部证据、坐标、异常原因，并允许接受、拒绝、校正或重归属。异常项未处理完时不能生成完整复核文件，也不会和普通候选一起被一键接受。只有异常清单为空时，用户才可回复“下一步/继续”直接批量确认。

### 4. 数据辅助质量判断

工具提供：

- 坐标标定斜率、截距、逐锚点残差和归一化 RMSE；
- 曲线覆盖率、最大连续缺口和分段信息；
- 散点面积、宽高、填充率和长宽比；
- 柱图矩形度、基线距离和组件统计；
- 像素量化与可评估标定残差形成的局部不确定度；
- 全图及绘图区残差和残差热图。

这些指标形成可重复的本地综合评估，帮助用户把精力集中在异常组；AI 解释不替代原始像素证据或来源哈希。

### 5. 缺口和坐标尺度保持一致

观测数据始终保留 `segment_break`。项目可以为连续曲线声明有上限的显示补线、形状保持几何，或使用 `geometry_source=guide_constrained` 从已声明引导路径和可见像素残差生成连续展示。所有派生点只写入 `render/display-geometry.csv`，不会回写 `data.csv`。`linear` 与 `log10` 坐标变换会同时用于标定和重绘。

### 6. 同色系列与图内图例

`guided_path` 使用人工确认的稀疏引导点限定搜索走廊，但只接受走廊内真实存在的源像素。`guided_group_path` 进一步对同色系列执行排他式联合分配：实线与虚线分别声明语义，同一个像素簇不能同时归入两个系列；无法唯一判断的分配标记为模型辅助证据。每个系列可声明局部 `exclude_boxes_px`，避免过去用一个大图例框误删真实曲线。

### 7. 多格式与矢量导出

- 图源：PNG、JPEG、TIFF、BMP、WebP、PDF；
- 外部数据：CSV、TSV、JSON、XLSX、XLSM；
- 重绘输出：PNG、SVG、PDF。

旧版二进制 `.xls` 当前不支持，避免“检查时声称支持、重绘时失败”的不一致。

## 安装

推荐 Python 3.11 或更新版本。

```bash
python3 -m pip install -r requirements.txt
python3 scripts/more_sci_figure.py --help
```

作为 Codex 或其他 Agent skill 使用时，把本目录放入对应的 skills 目录，并要求 Agent 在执行前完整阅读 `SKILL.md`。

## 快速开始

### 第一步：检查并锁定来源

```bash
python3 scripts/more_sci_figure.py inspect \
  --input figure.png \
  --chart-type line \
  --out-dir evidence
```

打开 `evidence/project.json`，确认绘图区、坐标尺度、锚点、系列颜色和质量门。

### 第二步：提取候选值

```bash
python3 scripts/more_sci_figure.py extract \
  --spec evidence/project.json \
  --out-dir evidence
```

此时会生成 `candidates.csv`、`review-assessment.json`、`review-anomalies.csv` 和可选深挖用的 `review.html`，但不会生成正式 `data.csv`。

可选：生成不改变正式状态的水印预览：

```bash
python3 scripts/more_sci_figure.py preview \
  --spec evidence/project.json \
  --candidates evidence/candidates.csv \
  --out-dir evidence/candidate-preview
```

### 第三步：查看综合评判并回复“下一步”

Agent 自动读取综合评分、风险等级、逐系列指标和异常组。默认不打开逐点复核页。风险允许时，用户只需回复“下一步”或“继续”；Agent 内部执行：

```bash
python3 scripts/more_sci_figure.py review-assess \
  --project-dir evidence

python3 scripts/more_sci_figure.py review-confirm \
  --project-dir evidence \
  --reviewed-by "可追溯用户身份" \
  --confirmation "用户原始确认语句"
```

`critical` 风险强制停止；`high` 风险只要求处理异常区；`low/medium` 只允许批量处理普通候选。任何异常候选都必须在独立表中获得明确决定。保存成功或失败均显示明确状态与实际路径；随后仍需通过 `review-apply` 的哈希和覆盖检查。

```bash
python3 scripts/more_sci_figure.py review-apply \
  --project-dir evidence \
  --decisions evidence/review-decisions.json
```

### 第四步：重绘并验证

```bash
python3 scripts/more_sci_figure.py render \
  --spec evidence/project.json \
  --data evidence/data.csv \
  --out-dir evidence/render

python3 scripts/more_sci_figure.py validate \
  --project-dir evidence \
  --reference figure.png
```

## 标准工作流与人工门控

[![More Sci Figure 详细操作流程图](assets/more-sci-figure-workflow.svg)](https://github.com/bingyunjiang/more-sci-figure)

详细操作图保留 1–7 步命令、质量门、拒绝分支、直接数据旁路以及四类独立状态。完整流程按以下顺序执行：

1. `inspect` 保留并锁定来源，生成 `source-report.json` 和待补全的 `project.json`。
2. 人工确认图表类型、绘图区、坐标尺度、系列颜色以及每个数值轴至少两个有效锚点。
3. `extract` 生成候选、证据叠图、质量报告、AI 综合评估和异常清单，不会生成正式数据。
4. Agent 汇报综合评分、风险等级、系列指标和异常组；风险允许时，用户回复“下一步/继续”即可生成哈希绑定的批量确认。只有异常深挖才使用逐点页面。
5. `review-apply` 校验哈希和决策覆盖率，仅把接受项写入正式 `data.csv`。
6. `render` 从声明数据统一导出 PNG、SVG 和 PDF；可选展示几何单独记录，不覆盖正式观测值。
7. `validate` 检查来源与交付物哈希、清单、状态、产物完整性，并可计算参考图残差与残差热图。

`pipeline` 第一次运行会输出综合评分、风险等级和异常组，并停在对话确认门：

```bash
python3 scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json \
  --out-dir evidence
```

用户回复“下一步/继续”、Agent 生成批量复核记录后继续：

```bash
python3 scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json \
  --out-dir evidence \
  --review-decisions evidence/review-decisions.json
```

## CLI 命令

| 命令 | 关键词 | 功能 |
| --- | --- | --- |
| `inspect` | 来源、哈希、PDF 页面 | 检查输入并生成项目模板 |
| `extract` | 标定、候选值、证据叠图 | 提取可见候选值并生成复核页 |
| `review-assess` | AI 综合评分、异常组 | 融合质量指标并生成对话式评判摘要 |
| `review-confirm` | 下一步、批量确认 | 把用户对话确认转为覆盖全部候选的审计记录 |
| `review` | 本地页面、逐项决策 | 重新生成 `review.html` |
| `review-serve` | 固定路径、本机回环 | 启动复核会话并把决定固定保存到当前项目目录 |
| `review-apply` | 哈希绑定、正式数据 | 应用复核决定并生成 `data.csv` |
| `render` | 重绘、矢量、中文字体 | 导出 PNG、SVG 和 PDF |
| `preview` | 未复核、水印、候选轨迹 | 预览 `candidates.csv`，不生成正式数据或推进状态 |
| `validate` | 完整性、状态、残差 | 验证交付物和可选参考图 |
| `pipeline` | 门控管线 | 按顺序执行并在复核点暂停 |

查看详细参数：

```bash
python3 scripts/more_sci_figure.py COMMAND --help
```

## 输入与交付物

### 图像提取项目

```text
evidence/
├── project.json
├── source-report.json
├── candidates.csv
├── overlay.png
├── extraction-report.json
├── review-assessment.json
├── review-anomalies.csv
├── review.html
├── review-template.json
├── candidate-preview/
│   ├── candidate-preview.png
│   ├── candidate-preview.svg
│   ├── candidate-preview.pdf
│   └── candidate-preview-report.json
├── review-decisions.json
├── data.csv
├── manifest.json
├── validation-report.json
└── render/
    ├── render.png
    ├── render.svg
    ├── render.pdf
    ├── display-geometry.csv
    └── render-report.json
```

### 直接数据重绘

外部数据直接重绘时：

- `extraction_status=not_applicable`；
- `review_status=not_applicable`；
- 原始数据保持不变；
- 项目目录内生成规范化 `data.csv`；
- 清单同时记录外部数据和规范化数据的哈希。

## 项目规格与质量门

从 [assets/project-template.json](assets/project-template.json) 开始。正式 Schema：

- [schemas/project.schema.json](schemas/project.schema.json)
- [schemas/review-assessment.schema.json](schemas/review-assessment.schema.json)
- [schemas/review-decisions.schema.json](schemas/review-decisions.schema.json)

质量门示例：

```json
{
  "quality_gates": {
    "calibration": {
      "max_normalized_rmse": null,
      "require_three_anchors": false
    },
    "line": {
      "min_coverage": 0.5,
      "max_gap_fraction": null
    },
    "scatter": {
      "min_accepted_components": 1,
      "max_rejected_ratio": null
    }
  }
}
```

`null` 表示不设置该自动阈值。阈值应由图像分辨率、用途和研究要求决定，不能把示例值当作跨项目通用标准。

同色系列的最小声明示例：

```json
{
  "id": "model-red",
  "color": "#ff0000",
  "extraction_mode": "guided_group_path",
  "shared_color_group": "red",
  "guide_interpolation": "shape_preserving",
  "line_semantics": "solid",
  "guide_corridor_px": 7,
  "guide_points_px": [[120, 500], [260, 240], [420, 110]],
  "exclude_boxes_px": [[210, 400, 275, 425]]
}
```

同一 `guided_group_path` 颜色组至少需要两个系列。引导点限定查找范围，不直接成为候选数值；没有源像素支持的列仍保持缺口。实线和虚线可使用不同覆盖率与最大缺口质量门。

## 证据边界与拒绝条件

工具不会推断：

- 被遮挡或隐藏的数据点；
- 原始重复实验；
- 误差条统计含义；
- 作者拟合模型或显著性；
- 图中没有声明的单位和样本量。

以下情况不生成正式数值：

- 图表类型、绘图区或坐标变换未确认；
- 任一数值轴少于两个有效锚点；
- 来源或测量栅格哈希不匹配；
- 图例、文字和数据标记无法分离；
- 标记粘连、遮挡或存在无法解决的歧义；
- 人工复核缺失、候选哈希不一致或全部拒绝。

## 开发与验收

运行单元和回归测试：

```bash
python3 -m unittest discover \
  -s scripts/tests \
  -p "test_*.py" \
  -v
```

运行完整发布验收：

```bash
python3 scripts/release_acceptance.py
```

真实图表基准框架见 [benchmarks/README.md](benchmarks/README.md)。合成夹具只能用于回归测试，不能冒充真实世界基准。

## 版本历史

按发布日期倒序排列：

- **v0.3.1 · 2026-07-26（当前版本）**
  - 默认复核改为 AI 综合评分、异常分组和对话式批量确认，逐点页面降级为异常深挖工具。
  - 增加 `review-assess`、`review-confirm`、评估哈希与用户原始确认语句审计。
  - 将异常候选与普通批量候选彻底分区；异常项逐项显示局部原图、定位标记、原因及接受/拒绝/校正/重归属决定，未决异常阻止正式复核文件生成。
  - 本地复核保存增加明确的成功/失败提示、固定项目路径、复核人必填和综合评估哈希校验。
- **v0.3.0 · 2026-07-26**
  - 增加同色曲线 `guided_path`、逐系列局部排除框和共享颜色歧义标记。
  - 增加 `guided_group_path` 排他式全局分配、形状保持引导和实线/虚线语义质量门。
  - 人工复核增加坐标校正与系列重新归属，并保留修改前血缘。
  - 增加带水印 `preview`，未复核候选不能更新清单或生成正式数据。
  - 增加固定画布、逐系列线型/标记和独立 `display-geometry.csv`。
  - 增加同色实/虚线、图内图例、受限补线和固定画布回归测试。
- **v0.2.0 · 2026-07-25**
  - 建立 `candidates.csv → review-decisions.json → data.csv` 的人工复核闭环。
  - 增加候选哈希绑定、本地中文复核页面、项目级质量门和四类独立状态。
  - 增加不确定度辅助字段、Lab 颜色距离、形状诊断、绘图区残差和热图。
  - 修复曲线缺口跨接、坐标尺度应用及直接数据重绘状态等问题。
- **v0.1.0 · 2026-07-24**
  - 发布首个本地版本。
  - 支持来源检查、线图/散点图/柱图候选提取、PNG/SVG/PDF 重绘和基础交付验证。

完整变更内容见 [CHANGELOG.md](CHANGELOG.md)。

## 路线图

- **v0.3.1 持续增强（不升版本）**
  - 建立带来源、授权和标注协议的真实图表基准集。
  - 增加可审计 OCR 候选和半自动图例定位。
  - 增加更丰富的逐系列残差和误检/漏检指标。
  - 在真实基准证据充分后扩展更多图表类型。

## 贡献

新增提取器或检测规则时，必须同时提交：

1. 合成单元夹具；
2. 至少一个未参与调参的保留样例；
3. 原尺寸证据叠图；
4. 拒绝和歧义测试；
5. 对交付契约与状态模型的说明。

## 许可证

本项目采用 [MIT License](LICENSE)。Copyright © 2026 Dr.Jiang。
