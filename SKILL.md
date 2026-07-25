---
name: more-sci-figure
description: 从栅格图片、PDF 图表、CSV、JSON 或 Excel 数据建立可审计的科研图表工作流。适用于检查图源、标定坐标轴、提取可见曲线/散点/柱形数据、人工复核候选值、论文级重绘、导出 PNG/SVG/PDF、比较参考图并分别验证提取、复核、重绘和交付状态。
---

# More Sci Figure

从原始图源到正式数据和验证重绘建立一条可复核证据链。除非用户明确授权远程 OCR 或视觉服务，否则全部在本地处理。

当前版本：`0.2.0`

## 核心规则

1. 测量前保留来源文件并记录 SHA-256。
2. 只测量原始栅格或声明的 PDF 页面，不测量预览图或缩放截图。
3. 数值提取前必须确认绘图区，并为每个数值轴提供至少两个有效锚点。
4. 算法候选值、人工接受值、外部提供数据和重绘产物必须分开保存。
5. 不推断隐藏点、原始重复实验、误差含义或作者模型参数。
6. 算法输出先进入 `candidates.csv`；只有绑定候选哈希的人工复核记录才能生成 `data.csv`。
7. 独立记录以下状态：
   - `extraction_status`：可见候选值是否通过自动质量门；
   - `review_status`：人工是否接受、部分接受或拒绝候选值；
   - `render_status`：声明数据是否成功重绘；
   - `delivery_status`：用户要求的交付物和检查是否完整。
8. 重绘成功不能提升不确定的提取或复核状态。

## 标准工作流

统一入口是 `scripts/more_sci_figure.py`。

### 1. 检查来源

```bash
python scripts/more_sci_figure.py inspect \
  --input figure.png --chart-type line --out-dir evidence
```

检查 `source-report.json`，补全生成的 `project.json`。如果图表类型、绘图区、坐标变换或锚点仍不确定，应在提取前停止。

### 2. 提取候选值

先阅读 [数据提取协议](references/extraction-protocol.md)，再运行：

```bash
python scripts/more_sci_figure.py extract \
  --spec evidence/project.json --out-dir evidence
```

支持颜色可区分的 `line`、紧凑实心 `scatter`、竖直实色 `bar` 和 `histogram`。该命令生成候选数据、证据叠图、质量报告和本地复核页面，但不会直接授权正式数值。

### 3. 人工复核

在浏览器打开 `evidence/review.html`，逐项接受或拒绝候选值，并导出 `review-decisions.json`。然后运行：

```bash
python scripts/more_sci_figure.py review-apply \
  --project-dir evidence \
  --decisions review-decisions.json
```

复核文件必须覆盖全部候选值，且候选哈希必须与当前 `candidates.csv` 一致。只有接受项会进入正式 `data.csv`。

### 4. 重绘

先阅读 [重绘协议](references/rendering-protocol.md)，再运行：

```bash
python scripts/more_sci_figure.py render \
  --spec evidence/project.json \
  --data evidence/data.csv \
  --out-dir evidence/render
```

同一图形对象统一导出 PNG、SVG 和 PDF。不得自行添加误差条、显著性、平滑或拟合。

### 5. 验证

```bash
python scripts/more_sci_figure.py validate \
  --project-dir evidence \
  --reference figure.png
```

验证来源与交付物哈希、产物完整性、清单一致性，并在画布相同时计算全图及绘图区残差、输出残差热图。

### 6. 门控管线

项目规格完整后才能使用 `pipeline`。第一次运行会停在人工复核门：

```bash
python scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json --out-dir evidence
```

完成人工复核后，可带复核文件继续：

```bash
python scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json \
  --out-dir evidence \
  --review-decisions review-decisions.json
```

## 直接数据重绘

使用外部 CSV、TSV、JSON、XLSX 或 XLSM 时，提取与人工复核状态应为 `not_applicable`。工具会生成规范化的 `data.csv`，但不会把外部数据冒充为图像提取结果。

## 项目与交付契约

修改项目规格前阅读 [交付物契约](references/artifact-contract.md)，并从 `assets/project-template.json` 开始。

图像提取项目的主要交付物：

- `candidates.csv`：算法检测到的候选值；
- `overlay.png`：原始分辨率证据叠图；
- `extraction-report.json`：标定、覆盖率、排除项、质量门与局限；
- `review.html`：本地人工复核页面；
- `review-decisions.json`：与候选哈希绑定的人工决定；
- `data.csv`：仅包含人工接受值；
- `render/render.png`、`render.svg`、`render.pdf`：一致重绘；
- `manifest.json`：哈希、工具版本及独立状态；
- `validation-report.json`：最终结构与可选视觉检查。

## 拒绝条件

遇到下列情况时，应只返回诊断，不提供正式数值：

- 图表类型未知或不支持；
- 绘图区或坐标变换未确认；
- 任一数值轴少于两个有效锚点；
- 锚点像素或数值退化，或对数轴含非正锚点；
- 来源哈希或测量栅格与声明不一致；
- 图形颜色无法与图例、坐标轴或注释分离；
- 标记粘连、遮挡或歧义超出提取器范围；
- 人工复核未运行、哈希不匹配或拒绝全部候选值。

项目专用修正不得写入通用技能。新增提取器必须同时提供合成夹具、保留测试、证据叠图和回归测试。真实图表基准必须标注来源与授权，不得用合成数据冒充。
