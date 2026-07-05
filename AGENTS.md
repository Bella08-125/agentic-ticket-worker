# AGENTS.md

本仓库是一个面向母婴/客服工单场景的执行型 Agent / 数字员工 Demo。目标是证明任务执行能力，而不是做普通 RAG Chatbot。

## 项目定位

- 主线链路必须保持为 `Task -> Planning -> Progressive Context -> Skill/Tool Call -> ReACT Trace -> Human Approval -> Final Action`。
- RAG/检索只能作为 `policy_lookup` 一类辅助能力，不要把项目改成一次性塞上下文的问答系统。
- 面试展示优先级高于生产级复杂度：代码要清楚、可解释、可测试、可快速演示。

## 架构边界

- `app/planner.py`: `SupervisorAgent` 负责任务拆解和结构化 `PlanStep`。
- `app/agent.py`: `AgentExecutor` 负责执行链路、状态流转、重试、审批和最终输出。
- `app/skills.py`: `SkillRegistry` 和业务 skills，维护能力元数据、schema、risk 和 capability。
- `app/context.py`: `ContextManager` 负责按阶段加载渐进式上下文。
- `app/memory.py`: `MemoryStore` 负责轻量长期记忆/客户画像抽象。
- `app/storage.py`: SQLite 持久化任务和执行步骤日志。
- `app/main.py`: FastAPI 路由层，只做请求/响应适配，不承载业务编排。

## 修改规则

- 修改前先读相关模块和测试，不凭文件名猜实现。
- 保持小模块和明确职责；不要把 Planner、Context、Skill、Memory 逻辑混进 API 路由。
- 新增行为时优先补测试，尤其是计划生成、状态流转、上下文加载、审批、重试和 ReACT trace。
- 不提交 `.venv/`、`data/`、`__pycache__/`、`.pytest_cache/` 或本地生成的数据库。
- 变更 README 或 docs 时，确保它们仍然服务“岗位展示”和录屏演示。

## 默认验证

```powershell
.\.venv\Scripts\python -m pytest -q
```

必要时再检查：

```powershell
git status --short
rg --files -g '! .venv' -g '!data' -g '!.git' -g '!__pycache__'
```

## 完成标准

- 测试通过，或明确说明无法运行的原因。
- API 行为、README、docs 与代码保持一致。
- 总结中说明架构影响、测试结果、剩余风险和下一步建议。
