# 贡献指南

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

> Canonical source: [./CONTRIBUTING.md](CONTRIBUTING.md)  
> Last synced with: 2026-07-17  
> 英文版是贡献流程和审查要求的权威来源；如有差异，以英文版为准。

AI Tell Scan 把精确率放在首位。修改规则前，请先阅读
`.claude/skills/ai-tell-scan/references/` 中的信号说明与 gold set 契约。

## 先确认工作范围

- 开始前搜索已有 issue 和 pull request。
- 新信号族、公开契约变化、在线试用行为变化应先建 issue。小型测试、文档和明确
  bug 修复可以直接提交 PR。
- 不要在 issue 中粘贴私有仓库、专有截图、凭证或未脱敏的在线报告。

分支名应简短，例如 `fix/bounded-aurora-scan` 或 `docs/local-development`。
提交保持聚焦并使用祈使式主题，例如 `fix: bound aurora source windows`。

## 规则与契约变更

每次规则变更必须：

1. 新增或更新至少一个正例和一个困难负例；
2. 保持候选与上下文确认精确率均不低于 0.90；
3. 保持真实 `file:line` 证据、framework 和状态分类正确；
4. 对可能合理或有意使用的组合提供上下文拒绝路径；
5. 通过扫描器测试、仓库/渲染器测试、评测器和 skill 校验器。

Schema、发布、公开仓库物化、摘要或在线 handoff 的变化还必须有针对性负向测试，
并进行独立安全/契约审查。除非目标仓库数据是虚构、脱敏、授权用于该目的且明确
属于受控语料，否则不得提交到仓库。

## Pull request

提交 PR 前运行 [DEVELOPMENT.zh-CN.md](DEVELOPMENT.zh-CN.md#发布前检查)
中的所有命令。PR 描述应：

- 说明用户可见结果和保持不变的安全边界；
- 列出所有新增或修改的 fixture；
- 报告候选、确认精确率与拒绝数量；
- 列出实际运行的命令和未覆盖的限制；
- 对安全、资源预算或公开契约变化请求独立审查。

维护者可能先要求缩小 diff、补充困难负例或重新评测，再讨论代码风格。批准取决于
证据和契约，而不仅是测试变绿。任何推断作者、执行目标代码、削弱只读边界或隐藏
评测限制的改动都会被关闭。

参与即表示同意 [CODE_OF_CONDUCT.zh-CN.md](CODE_OF_CONDUCT.zh-CN.md)。
疑似漏洞必须按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md) 私密报告，不能建公开 issue。
