# 项目与交付物契约

## 目录

1. 项目规格
2. 坐标标定
3. 候选值与正式值
4. 交付物血缘
5. 状态模型

## 项目规格

项目使用 `more-sci-figure.project.v1`。正式 JSON Schema 位于 `schemas/project.schema.json`，模板位于 `assets/project-template.json`。项目文件中的相对路径以项目文件所在目录为基准。

关键字段：

- `source`：来源路径、哈希、PDF 页码和测量栅格；
- `chart`：图表类型、绘图区、坐标轴锚点和系列检测参数；
- `quality_gates`：按项目声明的自动质量门；
- `assessment.acceptance_profile`：趋势预览、工程分析或论文定量数据的操作门槛；
- `render`：数据列映射、标签、标题和可选坐标尺度。

曲线系列还可声明 `extraction_mode=guided_path`、`guided_group_path` 或 `marker_centers`、`shared_color_group`、引导点、搜索走廊、标记形状、中心定位半宽和局部排除框。`curve_topology=continuous|segmented` 定义正式数据拓扑，默认连续；`curve_data_mode=observations|guide_constrained` 定义正式坐标来自复核观测，还是来自确认引导路径与可见残差。`marker_centers` 的最低标记数只作质量门，不代表完整性。可见标记/线条字形半宽与坐标中心定位不确定度分别保存，前者不得冒充误差棒。`polar_line` 另行声明中心、角度轴、径向轴、内外半径和 `polar_radial` 角度走廊。重绘只声明画布与视觉样式，不再决定曲线连续性。

## 坐标标定

使用全部锚点对像素到变换后数值进行最小二乘拟合：

- `linear`：直接拟合数值；
- `log10`：拟合 `log10(value)` 后再反变换。

报告斜率、截距、锚点数、逐锚点残差、RMSE、归一化 RMSE 和可评估性。少于三个锚点时，RMSE 不能作为独立质量证据。

## 候选值与正式值

算法输出和正式数据必须分开：

```text
project.json ── SHA-256 ──> spec-review.json + spec-review.png
                                  │
                                  └── 用户明确确认 ──> spec-confirmation.json
                                                            │
candidates.csv
      │
      ├── SHA-256 ──> review-assessment.json ──> review-anomalies.csv
      │                              │
      │                              └──> 用户对话批量确认
      │
      ├── SHA-256 ──> review-decisions.json
      │                         │
      └─────────────────────────┴──> observations.csv
                                        │
                                        └── 已确认曲线拓扑 ──> data.csv
```

- `spec-review.json` 绑定项目、来源与测量栅格哈希；`spec-review.png` 只显示提取规格，不含候选值；
- `spec-confirmation.json` 保存确认人、用户原始确认语句、项目/来源/测量栅格/叠图哈希；项目规格或来源声明变化后不得继续使用；
- `extract` 和 `pipeline` 必须拒绝缺失、无效或过期的提取前规格确认；
- `candidates.csv` 可以包含自动质量门未完全通过的可见候选；
- `review-assessment.json` 融合七个可重复证据维度，给出综合评分、最低维度、硬门、用途阈值、系列摘要、异常组、判定和下一步指令；不得把评分冒充新的像素证据；
- `review-anomalies.csv` 只承载异常深挖清单，不要求用户逐点复核全部候选；
- `review-uncertainty.csv` 保存以已确认坐标轴量程归一化的候选级不确定度与连续区间编号；不得使用单条曲线自身跨度作为分母，默认由 Agent 先处理，不自动转成逐点人工决定；
- `review-decisions.json` 必须覆盖全部候选编号并绑定候选文件哈希；
- `observations.csv` 只能包含人工明确接受的可见记录，并保留原始 `segment_break`；
- `data.csv` 是样式无关的正式数据集。每行必须记录 `data_provenance`、`curve_topology`、`curve_order`、正式 `segment_break` 和原证据断点 `evidence_segment_break`；默认连续曲线不得把虚线空白、遮挡或 JPEG 缺色提升为正式断点；
- `formal-data-report.json` 必须绑定项目、候选、复核、观测和正式数据哈希，并逐系列报告观测段数、正式段数和归一化的视觉断点数；
- 外部官方数据可以核对 `data.csv`，但不能覆盖图像提取证据。

复核保存位置由项目上下文决定，不由用户在页面选择：`review-serve` 只监听本机回环地址，校验完整复核载荷后固定原子写入 `<project-dir>/review-decisions.json`。保存动作本身不生成 `data.csv`，也不改变正式复核、重绘或交付状态；页面必须回显实际路径与文件 SHA-256。

复核动作允许 `accepted`、`rejected`、`corrected` 和 `reassigned`。坐标校正至少提供一个有限校正值；重新归属必须指向项目中的另一系列；两者都必须填写理由。正式记录使用 `original_*` 字段保留修改前血缘。

只有 `review-anomalies.csv` 为空且 `review-assessment.json` 给出 `recommended_action=batch_confirm` 时，用户的“下一步”“继续”或页面确认才可批量接受全部普通候选。存在异常时，页面必须把异常候选与普通候选分表展示，为每个异常提供局部像素证据、原因和独立决定；普通候选可预置为批量接受。例外仅限用户明确授权 Agent 截图检查并接受全部异常，且 Agent 已实际完成视觉检查：此时 `review-confirm --accept-anomalies` 可把 `review_anomaly_groups` 中的全部异常接受，并必须记录异常编号、原始授权、候选哈希与专用复核方法。该例外不得用于 `re_extract`、来源错误或 `stop`。`high` 只允许处理异常区；`critical` 必须停止。

`preview` 只读取 `candidates.csv` 并输出带有 `CANDIDATE PREVIEW · NOT REVIEWED` 水印的预览。它不得生成 `data.csv`、不得修改项目 `manifest.json`，也不得把 `render_status` 标为通过。

## 交付物血缘

必须保持以下不可逆方向：

```text
来源哈希
  → 提取前规格叠图与用户确认
  → 坐标标定
  → 像素证据与质量门
  → candidates.csv
  → 人工复核记录
  → observations.csv（复核可见观测）
  → data.csv（已确认曲线拓扑与正式坐标）
  → 可选 display-geometry.csv（仅绘制采样，不决定曲线连续性）
  → 声明的数据映射
  → PNG/SVG/PDF
  → 结构与视觉验证
```

`manifest.json` 记录工具版本、项目规格、来源哈希、各阶段状态和交付物哈希。

`review-assessment.json.acceptance.responsibility` 固定 Agent/用户责任边界。高不确定区间可以触发重新提取或用途判断，但不得单独抬升或降低四类正式状态。

## 状态模型

通用阶段状态：

- `pass`：该阶段要求的检查通过；
- `partial`：恢复或接受了部分可见值，并声明缺口；
- `failed`：阶段已运行但未通过门槛；
- `not_run`：阶段尚未运行；
- `not_applicable`：该阶段不属于本次请求。

人工复核状态：

- `accepted`：全部候选值被接受；
- `partial`：部分候选值被接受；
- `rejected`：没有候选值被接受；
- `not_run`：尚未复核；
- `not_applicable`：使用外部提供数据，不涉及图像候选复核。

`delivery_status=pass` 只表示用户要求的阶段与交付物通过，并不表示隐藏或歧义数据被恢复。图像提取项目未经人工复核不得交付为 `pass`。

`validation-report.json.delivery_assessment` 单独评价重绘技术交付的文件/哈希、格式、数据映射和规格执行。它不得改变或抬升提取、复核、重绘、交付四类正式状态；参考图残差只作诊断。
