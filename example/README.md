# Jiang & Tian (2021) Fig. 7 与 Fig. 9 处理记录

来源：

- `Jiang和Tian - 2021 - Integrated Prediction of Mechanical Behavior for the Non-Aligned Fiber Composites With Experimental.pdf`
- PDF SHA-256：`cd23603fcbf263c00ead3d69f0cf9eb5d40432db3637d84ad00d9c0f54e90387`
- 处理工具：`more-sci-figure 0.2.0`
- 处理范围：仅使用声明的 PDF 第 6 页与第 8 页，全部在本地完成。

## 朋友圈案例图

最终版采用 2400 × 1500 浅色编辑式版面，左侧为论文原图，右侧为重新设计的
候选数据重绘，并明确保留“待人工复核”状态：

- [Fig. 7 朋友圈案例图最终版](social/jiang-tian-fig7-case-final.png)
- [Fig. 9 朋友圈案例图最终版](social/jiang-tian-fig9-case-final.png)

旧版仍保存在同一目录，未被覆盖。最终版所用的独立科研重绘 PNG/SVG/PDF
位于 `social/showcase-redraws/`。SVG 版式使用本地相对路径引用科研图像，
发布或转发时应使用已经渲染好的独立 PNG 文件。

## Fig. 7

- 位置：PDF 第 6 页。
- 图型：多系列线图。
- 坐标：`True strain` 0–0.12；`True stress (MPa)` 0–150，均为线性轴。
- 已完成：直接提取 PDF 内嵌原始 JPEG、四点坐标标定、图例排除、同色实线/虚线分离、候选数据生成、像素叠加核查和候选重绘。
- 当前候选：221 行，覆盖 6 个系列。实线按连续轨迹提取；虚线只保留可见线段，不跨空白或图例区域推断数据。

主要产物：

- [候选数据](fig7/candidates.csv)
- [候选像素叠图](fig7/overlay.png)
- [人工复核页](fig7/review.html)
- 候选重绘：[PNG](fig7/preview/candidate-preview.png) · [SVG](fig7/preview/candidate-preview.svg) · [PDF](fig7/preview/candidate-preview.pdf)
- [PDF 内嵌原图](fig7/figure-original.jpeg)
- [项目规格](fig7/project.json)
- [提取诊断报告](fig7/extraction-report.json)
- [裁剪与哈希记录](fig7/crop-report.json)
- [状态清单](fig7/manifest.json)

## Fig. 9

- 位置：PDF 第 8 页。
- 图型：多系列线图。
- 坐标：`The Z-position of thickness (mm)` 0–2.0；`Fiber orientation tensor` 0–1.0，均为线性轴。
- 已完成：直接提取 PDF 内嵌原始 JPEG、六点坐标标定、图例排除、同色系列分离、候选数据生成、像素叠加核查和候选重绘。
- 当前候选：330 行，覆盖 6 个系列。µCT a22 使用论文 Table 3 只辅助在真实蓝色像素分支中选轨；表格值未被直接写入图像候选。
- 交叉核对：µCT a11、a22、a33 分别匹配 19、18、19 个 Table 3 位置，平均绝对误差分别约为 0.0109、0.0102、0.0011。

主要产物：

- [候选数据](fig9/candidates.csv)
- [候选像素叠图](fig9/overlay.png)
- [人工复核页](fig9/review.html)
- 候选重绘：[PNG](fig9/preview/candidate-preview.png) · [SVG](fig9/preview/candidate-preview.svg) · [PDF](fig9/preview/candidate-preview.pdf)
- [PDF 内嵌原图](fig9/figure-original.jpeg)
- [Table 3 核对值](fig9/reference-table3.csv)
- [项目规格](fig9/project.json)
- [提取诊断报告](fig9/extraction-report.json)
- [裁剪与哈希记录](fig9/crop-report.json)
- [状态清单](fig9/manifest.json)

## 当前证据状态

| 图 | extraction_status | review_status | render_status | delivery_status |
| --- | --- | --- | --- | --- |
| Fig. 7 | `partial` | `not_run` | `not_run` | `not_run` |
| Fig. 9 | `partial` | `not_run` | `not_run` | `not_run` |

已生成 `candidates.csv`、`overlay.png`、`review.html` 以及带
`CANDIDATE PREVIEW — NOT HUMAN-REVIEWED` 水印的 PNG/SVG/PDF 候选重绘。

尚未生成正式 `data.csv`、`review-decisions.json` 或 `render/` 目录。这是
`more-sci-figure` 的人工复核门控：候选值必须在 `review.html` 中逐项确认，
导出的决策文件还必须与当前 `candidates.csv` 的 SHA-256 绑定，才能成为正式数据。

## 复现与下一步

重新生成原图、图块和基础诊断：

```bash
python3 example/prepare_jiang_tian_figures.py
```

重新提取候选并生成叠图、复核页和候选重绘：

```bash
python3 example/extract_jiang_tian_curves.py
```

下一步分别打开 `fig7/review.html` 和 `fig9/review.html`，逐系列核对叠图并导出
`review-decisions.json`。在该步骤完成前，候选重绘不得作为已审核的正式数据图使用。
