# 项目进度与交付规划

本文档基于《docs/self-evolving-system.md》的体系目标，对当前仓库的实现现状、风险与后续工作进行审视，便于持续跟踪。

## 0. 当前完成度快照

- **整体完成度估算**：约 75%。`EvolutionOrchestrator` 已串联候选生成 → 评测级联 → 档案更新 → 提示奖励 → 持久化快照，三类问题集（示例、最短路、背包）均可端到端运行。
- **核心交付能力**：`ProgramGenerator` 支持模板变异、AST 交叉、自动 repair，并将谱系写入 `.artifacts/git_lineage/`；`ProblemEvaluator` 和 `TierExecutor` 执行 L0–L3 级联、压力样例与分位数统计；`ArchiveManager` + `SelectionStrategy` 实现 NSGA-II 与 MAP-Elites；`PromptBandit` 跟踪提示奖励并导出遥测；`FilesystemPersistence`、`CacheManager` 提供快照与缓存。
- **最新验证**：`pytest -q`（26 项）全部通过；`.github/workflows/evolve.yml` 在 Python 3.11 上执行 lint（Ruff）、类型检查（mypy）与多问题矩阵 demo，确保主干稳定。
- **主要缺口**：评测仍为单机执行，缺乏容器/K8s 调度；观测面板仅有静态 HTML；外部持久化、提示反馈分析、成本审计工具链尚未完备。

## 0. 当前完成度快照

- **整体完成度估算**：约 75% —— 管线运行、档案/选择、跨问题演化与持久化快照均已落地；仍需交付分布式评测、交互式观测面板与提示反馈闭环。
- **核心能力**：候选生成（含 AST 交叉、LLM API 适配、自动 repair）、评测级联（L0→L3）、档案选择（NSGA-II、MAP-Elites、新颖度）、缓存与快照、Git 谱系追踪已全部上线并通过端到端示例验证。
- **剩余重点**：观测面板升级、容器化评测、提示反馈强化、多问题规模化回归、治理审计工具链。

## 1. 愿景回顾

- **目标**：以可直连的 LLM 推理 API 为核心执行器，落地 AlphaEvolve 风格的自进化算法系统，覆盖提示演化、候选生成、评测级联、品质多样性档案、谱系治理与运维观测。
- **原则**：吞吐优先、可复现、安全隔离、可回放、品质多样性、提示共进化。

## 2. 里程碑完成度

| 里程碑 | 目标焦点 | 关键模块 | 当前状态 | 下一步动作 |
| --- | --- | --- | --- | --- |
| **M1：管线冷启动** | 打通候选生成 → 评测 → 档案 → 选择 → 提示奖励 | `run_loop.py`、`generation.py`、`evaluation.py`、`scheduler.py`、`prompt_policy.py` | ✅ 完成 | 增加真实问题资产与更长时间运行的回归脚本，验证多轮稳定性 |
| **M2：档案与多目标** | NSGA-II、新颖度、MAP-Elites 档案 | `selection.py`、`behaviors.py`、`models.py`、`dashboard.py` | ✅ 完成 | 将 MAP-Elites/Pareto 数据导出 Prometheus 或 CSV，叠加历史对比 |
| **M3：高级交叉与压力测试** | AST/语义交叉、L3 压测、分布式评测 | `ast_crossover.py`、`evaluation.py`、`problems/*/bench.py`、`.github/workflows/evolve.yml` | ⏳ 进行中 | 引入容器化/集群评测执行器，扩展多问题矩阵与资源配额治理 |
| **M4：元提示进化与治理** | 提示元变异、观测、审计、治理 | `prompt_policy.py`、`caching.py`、`docs/*`、未来的 `observability/` 组件 | ⏳ 进行中 | 构建交互式面板整合提示遥测/缓存指标，补齐审计与成本报表链路 |

## 3. 子系统梳理

### 3.1 编排与生命周期管理
- **现状**：`EvolutionOrchestrator` 负责种群队列、分层评测、档案更新、Prompt 奖励与快照写入；`RunState` 合并档案、Selection、Bandit、缓存、待评测列表并持久化至 `.artifacts/run_state.json`。
- **缺口**：尚未支持外部存储（PostgreSQL/对象存储），重放脚本与断点分析需手工处理；失败上下文仅在 repair prompt 中使用，尚无标准化回放 API。
- **计划**：实现数据库/Object Storage 版本的 `PersistenceGateway`；暴露 `run replay` CLI 用于失败分析；引入 OpenTelemetry/OpenMetrics 埋点形成 run 级追踪。

### 3.2 候选生成与谱系
- **现状**：`ProgramGenerator` 根据 `configs/problems.json` 自动载入基线，生成 mutate / repair / crossover 候选；`LLMApiAgentAdapter` 通过 OpenAI SDK 拉取流式补丁并透传 telemetry；AST 交叉会生成结构化 `plan` 元数据；`GitLineageTracker` 将源码与补丁提交至问题分支。
- **缺口**：交叉冲突仅以文本记录在 metadata，缺乏差异可视化与降级方案；谱系仓库只存在本地，未接入签名/远端推送策略；LLM 路由策略仍待与多模型权重联动。
- **计划**：生成结构化交叉报告，纳入档案/仪表盘；扩展 `LLMApiAgentAdapter` 支持多后端与退避重试；将谱系推送至受控远端仓库并附加审计标签。

### 3.3 评测级联与调度
- **现状**：`ProblemEvaluator` 运行多次样本、对抗/噪声集并计算分位数；`TierExecutor` 通过 lint/typecheck/AST 规则前置筛查，支持超时/圈复杂度/运行时门限；`bench.py` 脚本验证压力路径。
- **缺口**：执行仍在本地同步 Python 环境，缺乏容器化隔离与资源配额；评测日志未统一落盘，无法与对象存储联动；分层 budget 未结合动态反馈进行自适应调整。
- **计划**：接入 Docker/K8s executor，记录 `EvaluationResult.logs_path` 并上传对象存储；构建 budget 自调节机制与逆向回放工具。

### 3.4 档案、选择与品质多样性
- **现状**：`ArchiveManager` 维护 Pareto Front 和 MAP-Elites 网格，更新时计算行为新颖度；`SelectionStrategy` 结合 NSGA-II 排序、拥挤距离、新颖度奖励与岛屿迁徙机制，并在需要时触发 AST 交叉。
- **缺口**：缺少档案历史对比与热力图版本化，MAP-Elites 当前仅导出单次快照；新颖度距离基于手工定义的 `BehaviorFeatures`，未引入可学习表征。
- **计划**：引入历史快照序列与差异化对比工具；接入覆盖/语义嵌入向量，提高新颖度度量的鲁棒性；为岛屿迁徙设计可配置策略（概率、冷却时间）。

### 3.5 提示策略与模板
- **现状**：`PromptBandit` 使用 Thompson Sampling 对提示臂打分，`PromptGenome` 根据奖励调整温度、指令顺序与 checklist；`agents/prompts/` 覆盖 sample、shortest_path、knapsack 的 mutate/repair 臂，并在失败时自动追加 `Investigate <tier>_fail`。
- **缺口**：提示遥测仅以 JSON 导出，未形成分析面板；实际运行需手动配置 `LLM_API_ENDPOINT`/`LLM_API_MODEL`，缺乏多模型加权与自适应参数；repair 模板依赖规则生成，缺乏数据驱动反馈。
- **计划**：搭建 Prompt 遥测仪表盘与警报机制；为 API 调用增加熔断与退避策略；构建失败案例库驱动 repair 模板进化。

### 3.6 问题资产与配置
- **现状**：`configs/problems.json` 对接 `solutions/workdir/*.py` 基线，`problems/*` 目录提供数据生成、oracle、测试用例；`configs/tiers.yaml`、`configs/scheduler.yaml`、`configs/bandit.yaml` 定义评测与调度参数；Dockerfile 支持容器化运行。
- **缺口**：问题集规模有限，尚未覆盖更复杂数据结构或实战算法；配置缺乏环境差异抽象（如生产/测试不同 budget）；Docker 镜像未包含系统层依赖检测与缓存目录清理。
- **计划**：扩展问题库与基准脚本，引入更大输入规模；拆分环境配置并提供模板；为 Docker 镜像增加健康检查与工件卷挂载约束。

## 4. 工程质量与自动化验证

- **测试覆盖**：`tests/` 目录 26 项 Pytest 全部通过，覆盖候选生成、档案维护、Prompt Bandit、Git 谱系、持久化与 repair 逻辑。
- **静态质量门禁**：GitHub Actions `quality` job 执行 Ruff、mypy 与测试；建议补充 `ruff format` 检查与类型覆盖率统计。
- **交付自动化**：`evolution` job 以问题×运行次数矩阵触发 orchestrator demo，并上传 `.artifacts`；Dockerfile 提供基础镜像，后续需补充执行用户与缓存目录策略。

## 5. 风险清单与应对

| 风险 | 影响 | 应对策略 |
| --- | --- | --- |
| LLM 输出结构不稳定或 API 超时 | 评测失败、补丁损坏、吞吐下降 | 强化 JSON Schema 校验，加入 API 退避/重试与熔断，保留 repair 模板回退路径 |
| 评测成本过高 | 吞吐下降、预算超限 | Successive Halving + 缓存复用；引入容器 quota 与成本监控；定期对样例集降采样校准 |
| 档案早收敛 | 多样性降低，探索不足 | 提升新颖度权重、周期性注入随机变异、扩展岛屿迁徙策略 |
| 安全/合规缺口 | 数据泄露或执行中断 | 保持评测沙箱、AST 白名单、依赖许可证扫描；扩充 `docs/governance.md` 的审计流程并落地日志管道 |
| 部署与回放复杂 | 上线延迟、难以定位问题 | 脚本化部署、提供 replay CLI、将 `.artifacts` 元数据结构化，结合对象存储留痕 |

## 6. 近期交付检查清单

- [x] `ast_crossover.py`：AST 片段混合、冲突记录、行为特征写入。
- [x] `evaluation.py`：L0–L3 级联、压力样例与分位数统计。
- [x] `prompt_policy.py`：提示元进化、失败反馈、遥测导出。
- [x] `caching.py`：内容寻址缓存与命中率统计。
- [x] `docs/`：体系设计、运行手册、治理策略、观测指南。
- [x] `.github/workflows/evolve.yml`：多问题矩阵、质量门禁、artifact 上传。
- [x] `generation.py`：多问题候选、repair 模板、谱系打点。
- [x] `selection.py`：岛屿迁徙、MAP-Elites 快照、人口截断。
- [x] `problems/`：示例、最短路、背包问题包与测试资产。
- [x] `.artifacts/dashboard.html` / `prompt_telemetry.json`：MAP-Elites 热力图与提示遥测。
- [ ] `observability/`：交互式面板（提示 + 缓存 + 档案）、历史回放与告警。
- [ ] `persistence_ext`：数据库/对象存储实现 + replay CLI。
- [ ] `containerized_evaluator`：容器/K8s 执行器与资源配额治理。

> 文档将随功能迭代持续更新，确保里程碑、依赖关系与风险保持透明可追踪。
