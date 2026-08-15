---
name: agent-evolve
description: 从对话中发现用户偏好与习惯，生成提案，经用户确认后沉淀为长期记忆。当用户表达偏好、纠正输出、或说"记住/以后都这样"时使用。
---

# agent-evolve

从对话中学习用户偏好，透明且可审计。发现是自动的，写入永远需要用户批准。

## 何时使用

- 用户纠正你的输出（"说了别用冒号"）
- 用户表达偏好（"配图要白底""以后报告都用表格"）
- 用户说"记住""写进记忆""以后都这样"

## 使用步骤

1. 扫描对话历史，统计偏好信号：

```bash
evolve scan --root .agent-evolve
```

2. 生成提案（过阈值且未重复的主题）：

```bash
evolve propose --root .agent-evolve
```

3. 向用户展示提案内容（`evolve list`），请求确认。**未获用户明确同意前，不得执行 approve/apply。**

4. 用户同意后：

```bash
evolve approve <id> --root .agent-evolve --approver <用户名>
evolve apply <id> --root .agent-evolve
```

5. 若用户反悔，可回滚：

```bash
evolve rollback <id> --root .agent-evolve
```

## 红线

- 永远不自行 approve 自己的提案，批准必须来自用户
- 提案未批准前不产生任何持久效果
- 不直接编辑受保护记忆文件，一律走提案流程
