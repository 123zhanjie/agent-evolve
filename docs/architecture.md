# Architecture

agent-evolve 的设计目标：**零依赖、纯文件、平台无关、发现与写入分离**。

## 设计原则

1. **文件即状态**：所有状态（信号、提案、台账、备份）都是磁盘上的普通文件，git 友好、可审计、可手工修复。
2. **零第三方依赖**：仅用 Python 标准库，任何环境 `python3 -m evolve.cli` 即可运行。
3. **发现自动、写入审批**：scan/propose 可全自动跑（cron）；apply 前必须有 `approve` 且写入台账。
4. **证据链**：每条提案附信号样本（类型、原文引用、来源文件），人类可核查。

## 数据流

```
conversation logs (history/*.md|txt|jsonl)
        │  scan_history(): 段落级扫描，topic 关键词命中 + trigger 词分类
        ▼
signals[] {topic, type, quote, source, decay}
        │  aggregate(): 按 topic 计数，score = Σ(次数 × weight × decay)
        ▼
stats[] {topic, counts, score, samples}
        │  build_proposals(): 过阈值 + 去重 → proposals/pending/{id}.md
        ▼
pending proposal (front matter + 建议改动 + 理由 + 候选依据)
        │  approve()（人类动作，ledger 记录 approver）
        ▼
approved proposal
        │  apply(): 备份到 backups/{id}/ → 合并进 protected file → ledger
        ▼
applied  →  rollback(): 从 backups/ 恢复 → 台账留痕
```

## 安全不变量

| # | 不变量 | 实现 |
|---|--------|------|
| 1 | 智能体不能自批 | approve 是 CLI 显式命令，提案 front matter 只有状态流转，无任何自动批准路径 |
| 2 | 受保护文件只经提案修改 | apply 强制要求 status=approved；core 不提供直接写 protected file 的公开入口 |
| 3 | 批准前无持久效果 | scan/propose 只写 proposals/ 与 ledger，不触碰 memory/ |
| 4 | 失败不学习 | 扫描只看对话文本，工具错误日志不在扫描范围 |
| 5 | 全程可追溯 | ledger/approval.jsonl 追加式记录 approve/reject/apply/rollback |

## 信号分类

| 类型 | 触发词（正则） | 权重 |
|------|----------------|------|
| correction | 别用 / 不要 / 别再 / 说了别 / 又用 / 又犯 / 应该用 / 改回 / 不能用 / 禁止 / 总是用 / 老是 | 1.0 |
| explicit | 记住 / 写进记忆 / 记下来 / 以后都这样 / 以后都用 | 1.0 |
| repeat | 以后 / 每次都 / 都用 / 一律 / 统一 / 默认 / 仍然 / 还是要 | 0.7 |
| acceptance | 无触发词命中（弱信号） | 0.3 |

时间衰减：`decay = 1.0 if days <= decay_days else max(0.2, 1.0 - (days - decay_days) / (decay_days * 2))`

## 模块职责

| 模块 | 职责 |
|------|------|
| `core.scan_history` | 遍历历史目录，提取信号 |
| `core.aggregate` | 主题聚类、计分、采样证据 |
| `core.build_proposals` | 阈值判断、去重、生成提案文件 |
| `core.parse_proposal` | front matter 解析 |
| `core.set_status` | 状态流转（pending → approved/rejected → applied） |
| `core.ledger_append` | 追加式台账 |
| `core.apply_proposal` | 备份 + 合并 + 台账 |
| `core.rollback_proposal` | 按备份恢复 + 台账 |

## 与宿主智能体的适配

适配层只有 5 个接口，见设计蓝图：

| 接口 | agent-evolve 实现 | OpenClaw | Claude Code |
|------|-------------------|----------|-------------|
| trigger | cron 或手动 `evolve scan` | evolution-check 消息 | Stop hook |
| propose | `evolve propose` | evolution_proposal | proposals/ 目录 |
| approve | `evolve approve` | 桌面审批卡片 | 聊天确认 |
| apply | `evolve apply` | 应用事务 | 脚本 |
| audit | ledger/approval.jsonl | 应用日志 | git 台账 |

## 后续演进

- **v0.2 规则细化**：把已有条目的增量补充识别为 refinement 信号，生成 diff 提案，版本化更新
- **v0.2 语义匹配**：可选 embedding 后端（接口预留，不破坏零依赖）
- **v1.0 硬写保护**：宿主框架集成文件系统权限，软约束升级为硬约束
