---
name: more-sci-figure
description: 从栅格图片、PDF 图表、CSV、JSON 或 Excel 数据建立可审计的科研图表工作流。适用于检查图源、锁定 PDF 嵌入图像、标定笛卡尔或极坐标轴、提取可见曲线/散点/柱形数据、人工复核候选值、论文级重绘、导出 PNG/SVG/PDF、比较参考图并分别验证提取、复核、重绘和交付状态。
---

# More Sci Figure

从原始图源到正式数据和验证重绘建立一条可复核证据链。除非用户明确授权远程 OCR 或视觉服务，否则全部在本地处理。

当前版本：`0.3.1`

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

PDF 页内包含独立栅格图对象时，优先锁定原始嵌入对象而不是重采样整页；索引来自声明页面且从 0 开始：

```bash
python scripts/more_sci_figure.py inspect \
  --input article.pdf --page 9 --pdf-image-index 1 \
  --chart-type line --out-dir evidence
```

`source-report.json` 会同时记录 PDF 哈希、页码、对象索引、xref、编码、尺寸和测量栅格哈希。

检查 `source-report.json`，补全生成的 `project.json`。如果图表类型、绘图区、坐标变换或锚点仍不确定，应在提取前停止。

### 2. 提取候选值

先阅读 [数据提取协议](references/extraction-protocol.md)，再运行：

```bash
python scripts/more_sci_figure.py extract \
  --spec evidence/project.json --out-dir evidence
```

支持颜色可区分的 `line`、单值径向 `polar_line`、紧凑实心 `scatter`、竖直实色 `bar` 和 `histogram`。`polar_line` 必须声明中心、内外半径、至少两个角度锚点、至少两个径向锚点、零度方位和增角方向；候选按声明角度采样，并保留真实颜色像素支持。同色曲线可声明 `guided_path` 独立引导，或使用 `guided_group_path` 对同一颜色组执行排他式联合分配；后者结合 `line_semantics=solid|dashed`、形状保持引导、连续性代价和局部排除框，避免同一像素同时进入两个物理系列。每个候选仍必须有真实像素支持，引导线本身不是数据。模型辅助分配标记为 `model_assisted_exclusive_assignment`。该命令生成候选数据、证据叠图、质量报告和本地复核页面，但不会直接授权正式数值。

需要在复核前检查整体轨迹时，只能生成带水印候选预览：

```bash
python scripts/more_sci_figure.py preview \
  --spec evidence/project.json \
  --candidates evidence/candidates.csv \
  --out-dir evidence/candidate-preview
```

`preview` 不生成 `data.csv`、不修改 `manifest.json`，也不推进正式重绘或交付状态。

### 3. AI 综合评判与对话确认

默认流程不得要求用户逐点校对大量候选。`extract` 自动生成 `review-assessment.json` 和 `review-anomalies.csv`；Agent 应读取综合评分、风险等级、逐系列覆盖率/缺口/引导残差、模型辅助比例和异常组，只向用户汇报关键结论。

综合评分由七个维度组成：来源与证据完整性 10%、坐标标定质量 15%、像素证据质量 20%、系列分离与连续性 20%、不确定度与稳定性代理 15%、异常负担 10%、项目质量门符合度 10%。必须同时报告总分、最低维度分、最差维度、最差曲线、硬门结果和下一步指令，不能只报总分。

`project.assessment.acceptance_profile` 定义用途门槛：`exploratory` 为总分 85/单项 75，`engineering` 为 90/85（默认），`publication` 为 95/90。来源与哈希、自动质量门、候选编号完整性和未决高危异常是不可补偿硬门。分数是 v0.3.1 的保守操作基线，不是统计准确率；论文用途尤其不得把高分当作真值验证。

不达标时必须先由 Agent 工作，不得立即把全部候选交给用户：

- 自动执行锚点留一扰动稳定性，至少三个锚点时逐次移除一个锚点重新拟合；
- 计算每个候选相对所属系列跨度的归一化不确定度；
- 将高不确定候选合并为连续区间，完整写入 `review-uncertainty.csv`，页面最多展示 12 个最高风险代表区间；
- 读取 `acceptance.responsibility`，先完成 `agent_next`；只有 `user_required_now=true` 时才请求用户操作；
- 用户不负责运行命令、选择保存路径、调整提取参数或逐点复核普通候选；
- 不得为提高分数自动放宽颜色阈值、抹去 `segment_break` 或把派生几何写回候选。

综合评估使用可重复的本地证据指标，Agent 负责压缩与解释结果。它不会把 AI 判断冒充新的像素证据：来源哈希、候选哈希、质量门和异常记录仍保留。风险处理规则：

- `low` 或 `medium` 且没有异常候选、`recommended_action=batch_confirm`：普通候选可以通过“下一步”“继续”或本地页面批量确认；
- 存在异常候选时：普通候选仍可批量处理，但异常候选必须在独立复核区查看原始分辨率局部证据，并分别接受、拒绝、校正或重归属；异常项不得混入普通批次，也不得仅用一个总确认替代逐项决定；
- `high`：只处理独立异常区，不展开全部普通候选；
- `critical` 或 `recommended_action=stop`：立即停止，不得批量确认；
- 用户主动要求抽查、校正或重新归属时，才启动 `review-serve` 并展开逐点高级复核页。

Agent 内部执行以下命令；不要要求用户复制命令或选择路径：

```bash
python scripts/more_sci_figure.py review-assess --project-dir evidence
python scripts/more_sci_figure.py review-confirm \
  --project-dir evidence \
  --reviewed-by "可追溯用户身份" \
  --confirmation "用户原始确认语句"
```

`review-confirm` 只有在综合评估允许批量确认且 `review-anomalies.csv` 为空时，才会生成固定路径的 `review-decisions.json`。存在异常时必须使用页面独立处理异常项；页面把普通候选预置为批量接受，异常候选保持待决策，只有全部异常都有明确决定后才生成覆盖全部候选的复核文件。然后应用复核：

若综合评估返回 `recommended_action=apply_review`，表示完整复核记录已经保存；Agent 应直接执行应用与哈希校验，不得再次要求用户批量确认。

```bash
python scripts/more_sci_figure.py review-apply \
  --project-dir evidence \
  --decisions evidence/review-decisions.json
```

复核文件仍必须覆盖全部候选值，且候选哈希必须与当前 `candidates.csv` 一致。只有接受项会进入正式 `data.csv`。逐点页面保留为异常深挖工具，不再是默认入口。

### 4. 重绘

先阅读 [重绘协议](references/rendering-protocol.md)，再运行：

```bash
python scripts/more_sci_figure.py render \
  --spec evidence/project.json \
  --data evidence/data.csv \
  --out-dir evidence/render
```

同一图形对象统一导出 PNG、SVG 和 PDF。不得自行添加误差条、显著性或拟合。只有项目明确声明时，才可为展示生成形状保持的派生几何；派生点写入独立 `display-geometry.csv`，不得覆盖人工接受的 `data.csv`。

### 5. 验证

```bash
python scripts/more_sci_figure.py validate \
  --project-dir evidence \
  --reference figure.png
```

验证来源与交付物哈希、产物完整性、清单一致性，并在画布相同时计算全图及绘图区残差、输出残差热图。

`validation-report.json` 还包含独立的重绘技术交付评分：交付物与哈希完整性 30%、三格式完整性 20%、数据到图形可追溯性 25%、重绘规格符合度 25%。它不抬升 `extraction_status` 或 `review_status`，参考图像素残差也只作诊断，不冒充数据准确率或视觉审美评分。

### 6. 门控管线

项目规格完整后才能使用 `pipeline`。第一次运行会输出综合评分与异常组，并停在对话确认门：

```bash
python scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json --out-dir evidence
```

用户对综合评估确认“下一步/继续”、Agent 生成批量复核记录后，可带复核文件继续：

```bash
python scripts/more_sci_figure.py pipeline \
  --spec evidence/project.json \
  --out-dir evidence \
  --review-decisions evidence/review-decisions.json
```

## 直接数据重绘

使用外部 CSV、TSV、JSON、XLSX 或 XLSM 时，提取与人工复核状态应为 `not_applicable`。工具会生成规范化的 `data.csv`，但不会把外部数据冒充为图像提取结果。

## 项目与交付契约

修改项目规格前阅读 [交付物契约](references/artifact-contract.md)，并从 `assets/project-template.json` 开始。

图像提取项目的主要交付物：

- `candidates.csv`：算法检测到的候选值；
- `overlay.png`：原始分辨率证据叠图；
- `extraction-report.json`：标定、覆盖率、排除项、质量门与局限；
- `review.html`：本地人工复核页面；异常候选独立于普通候选批量区，并提供局部像素证据；
- `review-assessment.json`：AI 综合评分、风险等级、系列指标和异常组；
- `review-anomalies.csv`：仅供异常深挖的候选清单；
- `review-uncertainty.csv`：候选级归一化不确定度、连续区间编号和 Agent 优先处理标记；
- `candidate-preview/`：可选的未复核水印预览，不属于正式交付；
- `review-decisions.json`：与候选哈希绑定的人工决定；
- `data.csv`：仅包含人工接受值；
- `render/render.png`、`render.svg`、`render.pdf`：一致重绘；
- `render/display-geometry.csv`：可选的派生展示几何及其血缘；
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
