# OpenClaw 适配指南

agent-evolve 的机制设计与 OpenClaw 的 Hermes 进化同源，可作为 OpenClaw 的补充工具使用。

## 安装

```bash
pip install agent-evolve
```

## 接入方式

1. **手动触发**：在会话中要求 OpenClaw 运行 `evolve scan` / `evolve propose`，用户确认后 `approve` + `apply`
2. **定时扫描**：用 cron 定期执行扫描与提案生成，把提案内容推送到会话：

```
evolve scan --root <你的记忆工作区>
evolve propose --root <你的记忆工作区>
```

3. **受保护文件**：将你的 MEMORY.md / AGENTS.md 列入 `rules/config.json` 的 `protected_files`，apply 时自动备份与台账

## 与 Hermes 的关系

- Hermes 是 OpenClaw 内置的进化机制（桌面端审批卡片）
- agent-evolve 是通用的、平台无关的实现，适用于 OpenClaw 之外的所有智能体
- 两者可并存：agent-evolve 负责跨平台统一规则，Hermes 负责 OpenClaw 内的深度集成
