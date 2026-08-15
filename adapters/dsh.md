# DSh（DeepSeek Harness）适配指南

如果基于 DeepSeek Harness 自建智能体（规则文档 + 角色专家 + skills 模式），agent-evolve 可作为**一个 skill 或外部工具**挂载。

## 方式一：作为外部工具（推荐）

1. 在智能体环境中安装：`pip install agent-evolve`
2. 在规则文档中给负责记忆/偏好的角色专家增加一条职责：

```
角色：记忆管家
职责：当用户表达偏好、纠正输出、或要求"记住"时，
     调用 evolve scan / propose 生成提案，
     向用户展示并等待确认，确认后执行 approve + apply。
     红线：未经用户批准不得 apply；不得直接修改记忆文件。
```

3. 运行时该角色专家通过工具调用执行 `evolve` CLI 命令，解析输出。

## 方式二：作为 skill 包

将 `adapters/claude-code/SKILL.md` 作为模板，改写为你的 skill 格式（规则文档风格），挂到记忆管家角色上，流程一致。

## 审批通道

DSh 无内置审批 UI 时，使用文件签名通道：

1. 生成提案后，将提案内容发送给用户
2. 用户回复"同意"或明确批准
3. 在用户监督下执行 `evolve approve` + `evolve apply`
4. 台账保留审批记录，可审计

## 注意事项

- scan/propose 可挂定时任务自动执行，approve/apply 必须人工
- 学习档案配置（active / conservative / off）在 `rules/config.json` 中调整
- 受保护文件列表按你的记忆文件路径修改
