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

曲线系列还可声明 `extraction_mode=guided_path`、`shared_color_group`、引导点、搜索走廊和局部排除框。`polar_line` 另行声明中心、角度轴、径向轴、内外半径和 `polar_radial` 角度走廊。重绘可声明固定画布、逐系列样式与派生展示几何。

## 坐标标定

使用全部锚点对像素到变换后数值进行最小二乘拟合：

- `linear`：直接拟合数值；
- `log10`：拟合 `log10(value)` 后再反变换。

报告斜率、截距、锚点数、逐锚点残差、RMSE、归一化 RMSE 和可评估性。少于三个锚点时，RMSE 不能作为独立质量证据。

## 候选值与正式值

算法输出和正式数据必须分开：

```text
candidates.csv
      │
      ├── SHA-256 ──> review-assessment.json ──> review-anomalies.csv
      │                              │
      │                              └──> 用户对话批量确认
      │
      ├── SHA-256 ──> review-decisions.json
      │                         │
      └─────────────────────────┴──> data.csv
```

- `candidates.csv` 可以包含自动质量门未完全通过的可见候选；
- `review-assessment.json` 融合七个可重复证据维度，给出综合评分、最低维度、硬门、用途阈值、系列摘要、异常组、判定和下一步指令；不得把评分冒充新的像素证据；
- `review-anomalies.csv` 只承载异常深挖清单，不要求用户逐点复核全部候选；
- `review-decisions.json` 必须覆盖全部候选编号并绑定候选文件哈希；
- `data.csv` 只能包含人工明确接受的记录；
- 外部官方数据可以核对 `data.csv`，但不能覆盖图像提取证据。

复核保存位置由项目上下文决定，不由用户在页面选择：`review-serve` 只监听本机回环地址，校验完整复核载荷后固定原子写入 `<project-dir>/review-decisions.json`。保存动作本身不生成 `data.csv`，也不改变正式复核、重绘或交付状态；页面必须回显实际路径与文件 SHA-256。

复核动作允许 `accepted`、`rejected`、`corrected` 和 `reassigned`。坐标校正至少提供一个有限校正值；重新归属必须指向项目中的另一系列；两者都必须填写理由。正式记录使用 `original_*` 字段保留修改前血缘。

只有 `review-anomalies.csv` 为空且 `review-assessment.json` 给出 `recommended_action=batch_confirm` 时，用户的“下一步”“继续”或页面确认才可批量接受全部普通候选。存在异常时，页面必须把异常候选与普通候选分表展示，为每个异常提供局部像素证据、原因和独立决定；普通候选可预置为批量接受，但任一异常未决定都必须阻止生成复核文件。`high` 只允许处理异常区；`critical` 必须停止。

`preview` 只读取 `candidates.csv` 并输出带有 `CANDIDATE PREVIEW · NOT REVIEWED` 水印的预览。它不得生成 `data.csv`、不得修改项目 `manifest.json`，也不得把 `render_status` 标为通过。

## 交付物血缘

必须保持以下不可逆方向：

```text
来源哈希
  → 坐标标定
  → 像素证据与质量门
  → candidates.csv
  → 人工复核记录
  → data.csv
  → 可选 display-geometry.csv（派生展示几何）
  → 声明的数据映射
  → PNG/SVG/PDF
  → 结构与视觉验证
```

`manifest.json` 记录工具版本、项目规格、来源哈希、各阶段状态和交付物哈希。

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
