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
- `render`：数据列映射、标签、标题和可选坐标尺度。

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
      ├── SHA-256 ──> review-decisions.json
      │                         │
      └─────────────────────────┴──> data.csv
```

- `candidates.csv` 可以包含自动质量门未完全通过的可见候选；
- `review-decisions.json` 必须覆盖全部候选编号并绑定候选文件哈希；
- `data.csv` 只能包含人工明确接受的记录；
- 外部官方数据可以核对 `data.csv`，但不能覆盖图像提取证据。

## 交付物血缘

必须保持以下不可逆方向：

```text
来源哈希
  → 坐标标定
  → 像素证据与质量门
  → candidates.csv
  → 人工复核记录
  → data.csv
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
