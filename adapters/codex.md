# Codex CLI 适配指南

OpenAI Codex CLI 通过 `AGENTS.md` 了解项目约定，并可直接调用命令行工具。接入方式：安装核心工具 + 在项目 AGENTS.md 声明使用规则。

## 安装

```bash
pip install agent-evolve
```

## 项目接入

在项目根目录 `AGENTS.md` 追加：

```markdown
## 偏好学习（agent-evolve）

当用户表达偏好、纠正输出或要求"记住"时：
1. 运行 `evolve scan --root .agent-evolve` 检查偏好信号
2. 有信号时运行 `evolve propose --root .agent-evolve` 生成提案
3. 向用户展示提案，用户确认后运行：
   `evolve approve <id> --root .agent-evolve --approver <user>` 然后 `evolve apply <id> --root .agent-evolve`
4. 禁止自行 approve/apply，禁止直接修改受保护记忆文件
```

## 说明

- Codex 无原生 hook 时，可在用户明确要求"记住这个"时主动触发 scan/propose
- 提案文件是纯 Markdown，Codex 可以直接阅读并展示给用户
- 台账（ledger/approval.jsonl）与备份保证全程可审计、可回滚
