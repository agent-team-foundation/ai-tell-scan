# AI Tell Scan

[English](README.md) | [简体中文](README.zh-CN.md)

> Canonical source: [./README.md](README.md)  
> Last synced with: 2026-07-17  
> 英文文档是实现、流程和发布细节的唯一权威来源；如有差异，以英文版为准。

AI Tell Scan 通过源码证据审查 React 和 Next.js 产品中成组出现的通用 UI
默认方案。它最多返回三个经过上下文确认的发现，每个发现都带有真实的
`file:line` 位置。它不判断代码是否由 AI 创作，不生成“AI 百分比”，也不对仓库
排名。

**在线扫描：** [使用 First Tree 扫描公开 GitHub 仓库](https://first-tree.ai/ai-tell-scan?utm_source=github&utm_medium=readme&utm_campaign=ai-tell-scan)

## 检测什么

确定性扫描会检查十类复合信号，包括悬浮玻璃导航、居中极光 hero、可互换的
三列图标卡片、装饰性指标、pill 角色滥用和重复的通用动效。单独一种颜色、
圆角、组件库或关键字永远不足以成为发现。

每个候选项随后都会进行与源码摘要绑定的上下文审查。审查者必须确认完整组合
确实出现在已交付且显著的界面中；若命中来自死代码、测试夹具、明确的品牌语言，
或适合该产品类型，则应拒绝并说明理由。最终报告只保留最值得处理的三个确认项。

## 本地运行

唯一运行时依赖是 Python 3.11 或更高版本。

```bash
git clone https://github.com/agent-team-foundation/ai-tell-scan.git
cd ai-tell-scan

OUT="$(mktemp -d)"
python3 -B ./bin/ats-scan.py /path/to/react-app \
  --target-id your-org/your-app \
  --output "$OUT/candidates.ats-1.json" \
  --review-template "$OUT/review.ats-review-1.json"
```

逐一阅读报告位置，把审查文件中的每个 `pending` 改为 `confirmed` 或
`rejected`，并填写与上下文相关的理由。然后执行：

```bash
python3 -B ./.claude/skills/ai-tell-scan/scripts/finalize.py \
  "$OUT/candidates.ats-1.json" "$OUT/review.ats-review-1.json" \
  --target /path/to/react-app --output "$OUT/report.ats-1.json"

python3 -B ./.claude/skills/ai-tell-scan/scripts/validate_report.py \
  "$OUT/report.ats-1.json"
```

扫描器不会修改目标仓库，也拒绝覆盖已有产物。若没有候选项，报告会直接以带有
限制说明的完成状态结束，无需上下文审查。

## 结果契约

公开的 [`ats-1` JSON Schema](schemas/ats-1.schema.json) 定义扫描状态、源码摘要、
候选集合、审查状态、Top 3 发现和复扫对比。每个最终发现包含：

- 复合规则与用于排序的校准置信度；
- 仓库相对路径和从 1 开始的真实行号；
- 至少三条证据记录；
- 上下文审查理由；
- 对产品可信度的影响与最小可信修正建议。

在线公开仓库试用还会记录规范化仓库 URL 和生成时间，并输出自包含、无脚本的
HTML 报告。发布流程先上传机器 JSON，成功后才上传 HTML；两者都成功之前不会
展示报告 URL。完整门禁见
[`publishing.md`](.claude/skills/ai-tell-scan/references/publishing.md)。

## 精度门禁

受控 `ats-gold-1` 语料包含 30 个紧凑 React/Next.js 项目：15 个正例、13 个困难
负例和 2 个不适用项目。

| 层级 | TP / FP / FN | 精确率 | 召回率 |
| --- | ---: | ---: | ---: |
| 确定性候选 | 23 / 0 / 0 | 1.0000 | 1.0000 |
| 盲审确认 | 20 / 0 / 0 | 1.0000 | 1.0000 |

盲审包含三个真实拒绝；若机械确认所有候选，精确率只有 0.8696，无法通过 0.90
门禁。这是回归语料结果，不代表全量真实仓库的总体准确率。完整结果见
[`eval-report.md`](.claude/skills/ai-tell-scan/references/eval-report.md)。

## 仓库结构与参与方式

```text
.claude/skills/ai-tell-scan/  唯一 skill 源、扫描器、评测器和参考契约
bin/                           本地命令入口
schemas/                       公开 ats-1 契约
examples/                      已校验的真实仓库输出
tests/                         渲染器和仓库契约测试
```

完整开发命令见 [DEVELOPMENT.zh-CN.md](DEVELOPMENT.zh-CN.md)，贡献流程见
[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。参与社区须遵守
[CODE_OF_CONDUCT.zh-CN.md](CODE_OF_CONDUCT.zh-CN.md)，漏洞请按
[SECURITY.zh-CN.md](SECURITY.zh-CN.md) 私密报告。项目采用 Apache-2.0 许可证。
