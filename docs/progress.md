# 项目进度追踪

本页根据《docs/self-evolving-system.md》提出的里程碑与实施路线，汇总当前代码仓库的实现状态。内容会随着每次提交更新，以便快速了解整体推进情况。

## 里程碑状态

| 里程碑 | 目标摘要 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| M1：管线冷启动 | 打通 L0/L1 评测级联、提示多臂调度、缓存与影响面 | 进行中 | 已落地真实的候选生成器与问题评测器，可在 L0/L2 运行语法/AST 校验与样例基准；缓存仍为内存占位，影响面尚待实现。 |
| M2：档案与多目标 | 引入 NSGA-II、新颖度与 MAP-Elites | 未开始 | 已放置档案管理与候选选择器接口，但仅提供占位实现，缺乏非支配排序和品质多样性策略。 |
| M3：高级交叉与压力测试 | AST 级交叉、语义合并、L3 压测 | 未开始 | `orchestrator/ast_crossover.py` 暂为占位，尚未编码 AST 变换与冲突处理逻辑；评测级联也未扩展到压力层。 |
| M4：元提示进化与治理 | 提示元进化、观测治理完善 | 未开始 | 提示多臂框架已具雏形，但缺少元提示变异、指标面板与审计功能。 |

## 已交付能力

- **编排主循环**：`EvolutionOrchestrator` 负责候选采样、评测级联、档案回写与提示奖励更新，为后续接入真实评测提供统一入口。该类已接通缓存、档案与 bandit 接口，并支持异步运行多个步骤。源码：`orchestrator/run_loop.py`
- **真实评测执行**：`ProblemEvaluator`、`TierExecutor` 组合可加载候选代码、执行语法/AST 校验，并对样本数据集进行准确率与性能评分；`EvaluationScheduler` 现已调用该执行器而非随机模拟。源码：`orchestrator/evaluation.py`、`orchestrator/scheduler.py`
- **候选生成器**：`ProgramGenerator` 会基于 EVOLVE-BLOCK 模板生成多套候选实现并写入隔离目录，为后续接入 Gemini CLI 或补丁策略提供占位。源码：`orchestrator/generation.py`
- **提示多臂管理**：`PromptBandit` 支持从 `agents/prompts/` 目录加载提示臂，使用 Thompson Sampling 采样臂，并依据评测奖励调整 Beta 分布先验。源码：`orchestrator/prompt_policy.py`
- **模型与配置结构**：`orchestrator/models.py` 定义候选、指标、档案、缓存等数据结构，配合 `configs/` 下的 YAML 示例展示默认人口、级联预算与提示臂配置。源码：`orchestrator/models.py`、`configs/*.yaml`

## 主要缺口

1. **影响面与缓存写入**：`CacheManager` 仍未实现内容哈希与分层缓存写入策略，需要结合候选工作副本与评测日志设计键空间。
2. **多目标选择策略**：缺失 NSGA-II 排序、拥挤距离与新颖度奖励，档案更新逻辑需扩展以维护 Pareto 与 MAP-Elites 网格。
3. **提示元进化与奖励模型**：Bandit 虽已切换 Thompson Sampling，但尚未接入加权奖励、退火与元提示变异流程。
4. **评测扩展**：当前评测覆盖 L0/L2 样例，尚未对接 L3 压测、GitHub Actions 或 Docker 沙箱。
5. **安全与治理**：缺乏日志、指标采集以及更严格的安全策略，需要结合部署环境补齐。

## 下一步建议

- 优先落地评测执行路径（例如封装 `gemini-cli` GitHub Action 或本地 Docker 流程），以便验证从补丁生成到 L0/L2 的闭环。
- 在 `SelectionStrategy` 中实现 NSGA-II 与新颖度估计，引入 `ArchiveManager` 的 MAP-Elites 网格更新，配合档案抽样形成多样性维护机制。
- 扩展 `PromptBandit`，实现 Thompson Sampling 奖励更新与元提示变异入口，并补充提示模板的结构化约束示例。
- 搭建最小化观测栈（日志、事件与指标），确保后续扩展可复现并具备审计能力。

> 本进度页旨在提供高层可见性，随着模块逐步补齐会持续更新状态。
