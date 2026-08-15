#!/usr/bin/env bash
# agent-evolve 一键安装脚本
# 用法: bash install.sh [--local]
set -euo pipefail

echo "==> agent-evolve 安装"

if [[ "${1:-}" == "--local" ]]; then
  pip install -e .
else
  pip install agent-evolve
fi

echo "==> 验证安装"
evolve --help >/dev/null && echo "OK: evolve 命令可用"

echo ""
echo "下一步（按你的智能体选择）："
echo "  Claude Code : mkdir -p ~/.claude/skills/agent-evolve && cp adapters/claude-code/SKILL.md ~/.claude/skills/agent-evolve/"
echo "  Codex CLI   : 按 adapters/codex.md 在 AGENTS.md 添加使用规则"
echo "  DSh/自研    : 按 adapters/dsh.md 挂载为 skill 或工具"
echo "  OpenClaw    : 按 adapters/openclaw.md 接入"
