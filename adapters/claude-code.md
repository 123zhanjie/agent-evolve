# Claude Code 适配指南

agent-evolve 以两种方式接入 Claude Code：**Skills**（让 Claude 知道何时使用）与 **hooks**（自动触发扫描）。

## 安装

```bash
# 1. 安装核心工具（任选其一）
pip install agent-evolve          # PyPI 发布后
# 或本地安装
cd universal-evolution && pip install -e .

# 2. 安装 Skill 入口
mkdir -p ~/.claude/skills/agent-evolve
cp adapters/claude-code/SKILL.md ~/.claude/skills/agent-evolve/SKILL.md
```

## 工作流

1. Claude 在对话中读取 `~/.claude/skills/agent-evolve/SKILL.md`，知道用户表达偏好/纠正时可运行 `evolve scan`
2. 用户对话中出现偏好表达后，Claude 建议运行：

```bash
evolve scan --root .agent-evolve
evolve propose --root .agent-evolve
evolve list --root .agent-evolve
```

3. 用户确认提案内容后，Claude 执行：

```bash
evolve approve <id> --root .agent-evolve --approver <用户名>
evolve apply <id> --root .agent-evolve
```

## 自动触发（Stop hook 可选）

在项目 `.claude/settings.json` 配置：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "evolve scan --root .agent-evolve --quiet"
          }
        ]
      }
    ]
  }
}
```

hook 只做扫描（只读），提案与审批始终由 Claude 在对话中引导，最终由用户确认。
