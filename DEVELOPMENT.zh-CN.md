# 本地开发

[English](DEVELOPMENT.md) | [简体中文](DEVELOPMENT.zh-CN.md)

> Canonical source: [./DEVELOPMENT.md](DEVELOPMENT.md)  
> Last synced with: 2026-07-17  
> 英文版是开发、架构和发布细节的权威来源；如有差异，以英文版为准。

本文档给出可复现的 AI Tell Scan 贡献者工作流。仓库没有运行时包依赖；扫描器、
审查、渲染器、评测器和校验器只使用 Python 标准库。

## 前置条件

- Python 3.11 或 3.12
- Git
- 可选：`uvx`，用于无需持久安装的 Ruff 检查
- 可选：已认证的 GitHub CLI (`gh`)，用于受限公开仓库物化和在线可见性测试
- 可选：仅维护者在获授权的在线运行环境测试发布器时需要 AWS CLI

## 初始化

```bash
git clone https://github.com/agent-team-foundation/ai-tell-scan.git
cd ai-tell-scan
python3 --version
python3 -B scripts/validate_skill.py
```

无需 `pip install`、包锁文件或构建步骤。扫描时绝不能安装或运行目标仓库的依赖。

## 本地运行

扫描 React 或 Next.js checkout，并把产物写到该 checkout 之外：

```bash
OUT="$(mktemp -d)"
python3 -B bin/ats-scan.py /path/to/react-app \
  --target-id owner/repository \
  --output "$OUT/candidates.ats-1.json" \
  --review-template "$OUT/review.ats-review-1.json"
```

随后按 [README.zh-CN.md](README.zh-CN.md#本地运行) 完成上下文审查与 finalize。
扫描器会拒绝覆盖文件，也会拒绝向目标仓库内部写入产物。

## 测试与检查

```bash
python3 -B .claude/skills/ai-tell-scan/scripts/test_ats.py -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B .claude/skills/ai-tell-scan/scripts/evaluate.py \
  --output /tmp/ats-eval-1.json
python3 -B scripts/validate_skill.py
python3 -m compileall -q .claude/skills/ai-tell-scan bin scripts tests
uvx ruff check .
```

项目没有单独的类型检查或自动格式化命令。请保持现有 Python 风格；Ruff lint、
Python 编译检查、可执行报告校验和公开 JSON Schema 共同覆盖已发布契约。

## 架构地图

- `.claude/skills/ai-tell-scan/`：唯一 skill 源、确定性引擎、agent 审查流程、
  参考契约和受控语料
- `bin/ats-scan.py`：仓库级扫描入口
- `schemas/ats-1.schema.json`：公开报告契约
- `examples/`：已校验的机器报告和无脚本 HTML
- `tests/`：公开仓库物化、渲染、发布、schema 与仓库契约测试

确定性阶段只生成候选项。Agent 上下文审查在同一源码摘要上确认或拒绝候选项。
Finalize 最多报告三个确认项。在线发布是独立的 fail-closed 步骤。

## 环境与凭证

普通开发不需要环境变量。测试公开 checkout 时，可通过 `gh auth login` 或已有的
`GH_TOKEN` 认证 GitHub CLI。在线发布器从获授权的运行环境读取 AWS 凭证；不得
把凭证写入仓库文件、fixture、命令示例或测试输出。

## 排障

- **超过源码、索引或规则预算：** 缩小扫描根目录，或增加带回归测试的受限预筛选；
  预筛选必须继续识别跨父子组件拆分的组合。不要简单提高上限。
- **没有 React/Next.js 信号：** 确认所选根目录包含所属 `package.json`，而不是
  只有一个嵌套 UI 文件。
- **输出已存在或位于目标内部：** 在目标 checkout 之外使用全新的目录。
- **公开 checkout 或可见性校验失败：** 检查 `gh auth status` 与精确的
  `https://github.com/<owner>/<repo>` URL。身份无法确认时，在线流程必须失败关闭。
- **评测结果意外变化：** 在生成的 evaluation JSON 中检查 candidate、confirmed、
  rejected、framework、status 和 evidence 错误。

## 发布前检查

请求批准前，运行“测试与检查”中的每条命令，确认示例可复现，扫描一个有代表性的
公开仓库且不执行目标代码，并记录被审查的精确提交。规则或安全边界变化必须接受
独立审查。`main` 由 Python 3.11/3.12 必需检查和至少一个非作者批准保护。
