# 项目进度与交付规划

本文档基于《docs/self-evolving-system.md》的体系目标，对当前代码仓库进行全面梳理，并给出余下工作的实施计划，便于持续追踪。

## 0. 当前完成度快照

- **整体完成度估算**：约 75% —— 管线运行、档案/选择、跨问题演化与持久化快照均已落地；仍需交付分布式评测、交互式观测面板与提示反馈闭环。
- **核心能力**：候选生成（含 AST 交叉、Gemini CLI 适配、自动 repair）、评测级联（L0→L3）、档案选择（NSGA-II、MAP-Elites、新颖度）、缓存与快照、Git 谱系追踪已全部上线并通过端到端示例验证。
- **剩余重点**：观测面板升级、容器化评测、提示反馈强化、多问题规模化回归、治理审计工具链。

## 1. 愿景回顾

- **目标**：基于 `google-gemini/gemini-cli` 的能力，实现 AlphaEvolve 思路的自进化算法系统，覆盖提示演化、候选生成、评测级联、NSGA-II+MAP-Elites 档案、补丁应用、观测治理等全链路。
- **原则**：吞吐优先、可复现、安全隔离、可回放、品质多样性、提示共进化。

## 2. 里程碑完成度

| 里程碑 | 目标焦点 | 关键模块 | 当前状态 | 下一步动作 |
| --- | --- | --- | --- | --- |
| **M1：管线冷启动** | 打通候选生成→评测→档案→选择→提示奖励 | `run_loop.py`、`generation.py`、`evaluation.py`、`scheduler.py`、`prompt_policy.py` | ✅ 已完成 | 补充更多真实问题样例，验证在多问题场景下的稳定性 |
| **M2：档案与多目标** | NSGA-II、新颖度、MAP-Elites 档案 | `selection.py`、`behaviors.py`、`models.py` | ✅ 已完成 | 引入档案持久化与可视化导出（热力图、Pareto 序列） |
| **M3：高级交叉与压力测试** | AST/语义交叉、L3 压测、分布式评测 | `ast_crossover.py`、`evaluation.py`、`.github/workflows/evolve.yml` | ⏳ 进行中 | 已交付 AST 拼接候选 + L3 压测，后续扩展多问题集与分布式执行 |
| **M4：元提示进化与治理** | 提示元变异、观测、审计、治理 | `prompt_policy.py`、`caching.py`、`docs/`、未来的 `observability/` 组件 | ⏳ 进行中 | 引入提示模板基因库、指标采集、run replay 工具，完善安全策略 |

## 3. 子系统梳理

### 3.1 编排与生命周期管理
- **现状**：`orchestrator/run_loop.py` 管理父代采样、缓存命中、评测级联、档案更新与提示奖励；`models.py` 定义候选/指标/档案数据类；新增 `PersistenceGateway` 与 `FilesystemPersistence`，可将档案、种群、Bandit、缓存与待评估队列落盘并在重启后恢复。
- **缺口**：仍缺乏与外部存储（PostgreSQL、对象存储）的连接，断点数据目前仅存于本地 JSON；失败回放尚未接入统一 API。
- **计划**：
  1. 将 `PersistenceGateway` 扩展至数据库/对象存储实现，支撑集群共享状态。
  2. 在持久化快照基础上输出 run replay 脚本与指标重放流程。
  3. 对接指标日志（OpenTelemetry/OpenMetrics），实现 `run_id` 级追踪。

### 3.2 候选生成与谱系
- **现状**：`generation.py` 的 `ProgramGenerator` 现已从 `configs/problems.json` 载入多问题基线，按 `problem_id` 生成候选并在修复路径中注入失败上下文；`GeminiAgentAdapter` 保持 CLI 集成并支持元数据透传；`perform_ast_crossover` 结合 `SelectionStrategy` 的岛屿调度，允许在同问题域内进行 AST 拼接。新增的 `GitLineageTracker` 会在 `.artifacts/git_lineage/` 内为每个候选提交代码与补丁元数据，并回填 `git_commit` 至候选谱系。
- **缺口**：交叉冲突目前仅在日志和候选元数据中标注，尚未生成差异级联或可视化报告；Git 谱系同步仍局限于本地仓库，未对接远端推送与签名；CLI 多模型路由与限流策略尚未实现。
- **计划**：
  1. 基于冲突元数据生成结构化报告（含冲突类型、涉及函数、降级路径）并纳入档案/仪表盘。
  2. 拓展 `GeminiAgentAdapter` 支持多后端选择与速率控制，加入失败重试与退避策略。
  3. 将 `.artifacts/git_lineage/` 与远端 Git 仓库对接（含签名、审计分支），并在重播流程中引用对应 commit。

### 3.3 评测级联与调度
- **现状**：`ProblemEvaluator.evaluate` 支持 L3 压测、对抗/噪声数据、运行时分位数；`TierExecutor` 依据 `TierSpec.max_cyclomatic/max_runtime_ms` 判定通过，`bench.py` 可在压力模式下输出 JSON。
- **缺口**：容器化执行与资源隔离仍为后续工作；评测报告尚未落盘对象存储。
- **计划**：
  1. 接入容器/K8s 执行后端，落实资源配额与网络沙箱。
  2. 将 `EvaluationResult` 的日志与分位数写入工件，结合对象存储形成回放。
  3. 在多问题集上回归评测，以验证压力样例的泛化效果。

### 3.4 档案、选择与品质多样性
- **现状**：评测行为特征已由 `ProblemEvaluator` 填充运行时分位数与覆盖度；`ArchiveManager` 在更新时同步写出 MAP-Elites/ Pareto 快照，并触发 `.artifacts/dashboard.html` 热力图渲染；`SelectionStrategy` 引入岛屿成员表、按问题域约束交叉并触发 10% 迁徙，快照恢复时同步重建岛屿信息，同时会记录 AST 交叉冲突并写入候选元数据。
- **缺口**：岛屿迁徙策略仍缺少基于失败标签的动态调度，可视化尚未展示历代指标曲线；交叉质量报告待进一步量化并导出成图表。
- **计划**：
  1. 扩展迁徙策略，结合失败类型与 MAP-Elites 稀疏格定向采样移民，并将迁徙日志写入快照。
  2. 在观测面板中叠加历代 Pareto 指标、迁徙记录以及冲突统计，完善 `.artifacts/dashboard.html`。
  3. 为交叉产物生成差异摘要与冲突降级报告，并输出谱系可视化数据。

### 3.5 缓存与可复现
- **现状**：`CacheManager` 支持环境指纹、命中率统计与 `FilesystemCacheBackend` 持久化；`CacheEntry` 可序列化 JSON。
- **缺口**：仍需接入 Redis/数据库等共享缓存；需建立 TTL/清理策略。
- **计划**：
  1. 提供网络化缓存实现（如 Redis）。
  2. 引入 TTL 与垃圾回收策略，防止磁盘膨胀。
  3. 将缓存指标上报至可观测性面板。

### 3.6 提示工程与多臂老虎机
- **现状**：`PromptBandit` 引入 `PromptGenome`，支持指令随机化、温度调节、失败标签 checklist；奖励衰减结合历史轨迹，并自动导出 `.artifacts/prompt_telemetry.json` 供观测面板消费。
- **缺口**：尚未根据评测日志自动注入上下文片段；提示成效暂未与问题域、岛屿标签进行关联分析。
- **计划**：
  1. 将失败日志摘要注入提示上下文，形成领域化反馈。
  2. 在 `prompt_telemetry.json` 基础上生成多臂老虎机分析图表（成功率、迁徙贡献等）。
  3. 探索模板交叉/突变策略以扩大提示基因库。

### 3.7 问题库与基线解决方案
- **现状**：`problems/sample_problem/`、`problems/shortest_path/`、`problems/knapsack/` 均提供 spec、数据生成、对抗样本与基准脚本；对应 `solutions/workdir/` 下 baseline 已包含 EVOLVE-BLOCK 标注。
- **缺口**：仍缺乏更多性能/鲁棒双目标案例及跨领域问题；benchmark 输出尚未纳入集中报表。
- **计划**：
  1. 扩展问题集至并行/数值稳定等场景，并为每类问题准备性能与鲁棒双指标基线。
  2. 将基准脚本的 JSON 输出汇总至统一目录，供 CI 与观测面板消费。
  3. 构建多问题回归套件（如矩阵或夜间作业）以评估扩展后的岛屿与迁徙策略。

### 3.8 CI/CD 与自动化
- **现状**：`evolve` workflow 包含质量门禁（ruff/mypy/pytest）与两轮候选演示，并上传 `.artifacts`；`pyproject.toml` 提供 dev 依赖。
- **缺口**：缺少 Secrets 管理与多问题矩阵；需要集成基准数据与报告汇总。
- **计划**：
  1. 扩展矩阵维度（问题集、运行模式），引入密钥管理模板。
  2. 将评测结果汇总为 JSON artifact，供后续管线消费。
  3. 在 README 中补充 GitHub Actions 使用指南。

### 3.9 文档、观测与治理
- **现状**：新增《docs/runbook.md》《docs/governance.md》《docs/observability.md》覆盖操作、治理、指标；总体设计与进度文档同步更新；观测面板章节已记录 `.artifacts/dashboard.html` 及 prompt telemetry 导出方式。
- **缺口**：开发者 API 指南仍待撰写；观测面板需从静态 HTML 拓展至交互式仪表盘，并叠加缓存/提示指标。
- **计划**：
  1. 编写 API/模块参考文档，便于扩展模块接入。
  2. 实现交互式观测面板 MVP（Streamlit 或 Grafana），消费地图、Pareto、提示与缓存数据。
  3. 形成 run replay 指南与自动化报表模板。

## 4. 综合路线图

1. **冲刺 A（完成 M3 基础）**
   - 实装 AST 补丁拼接 + 冲突降级；在 `generation.py` 中调用。
   - 为 `evaluation.py` 增加 L3 压测与资源沙箱，扩充 sample_problem 的压力用例。
   - 更新 GitHub Actions，触发端到端评测矩阵。

2. **冲刺 B（完善提示与治理）**
   - 交付 `PromptGenome` 与元提示变异机制，接入失败日志反馈。
   - 实现档案/缓存持久化、指标采集与可视化导出。
   - 编写运行手册、治理策略，并设置安全审计开关。

3. **冲刺 C（扩展问题集与规模化）**
   - 新增至少两个问题包，覆盖性能与鲁棒双目标。
   - 完善分布式执行（K8s/GitHub Actions），验证 24h ≥ 10,000 次 L0 评测目标。
   - 交付 Run Replay 工具与观测面板最小可用版本。

## 5. 风险与缓解

| 风险 | 影响 | 缓解策略 |
| --- | --- | --- |
| LLM 输出结构不稳定 | 评测失败、补丁损坏 | 强制 JSON schema 校验、幂等补丁应用、Fail-fast repair 模板 |
| 评测成本过高 | 吞吐下降、预算超限 | Successive Halving + 缓存复用、影响面分析、定期校准 |
| 安全/合规问题 | 数据泄露、运行中断 | 沙箱执行、AST 白名单、依赖与许可证扫描、审计日志 |
| 档案早收敛 | 多样性降低 | 新颖度奖励、MAP-Elites 稀疏格采样、岛屿迁徙 |
| 部署复杂度 | 上线延迟 | Docker 化、脚本化部署、提供参考 GitHub Actions |

## 6. 近期交付检查清单

- [x] `ast_crossover.py`：实现补丁拼接 → AST 片段组合 → 语义合并最小版。
- [x] `evaluation.py`：新增 L3 压测入口、压力数据、资源限制。
- [x] `prompt_policy.py`：引入元提示变异（权重/Checklist/示例采样）。
- [x] `caching.py`：支持外部缓存后端与命中率指标。
- [x] `docs/`：补充运行手册、治理策略、观测面板草图。
- [x] `.github/workflows/evolve.yml`：并发矩阵、artifact 上传、静态检查。
- [x] `generation.py`：接入自动化 `repair` 模板、按问题维度生成候选并保留 CLI 元数据。
- [x] `selection.py`：输出岛屿迁徙快照与 MAP-Elites JSON 工件。
- [x] `problems/`：新增最短路与背包问题包，并在 CI 中引入多问题矩阵演示。
- [x] `.artifacts/map_elites.json`：导出后触发 `dashboard.html` 生成，提供热力图与 Pareto 概览。
- [x] `prompt_policy.py`：输出 `prompt_telemetry.json` 供提示分析。
- [ ] `observability/`：在 HTML 仪表盘基础上扩展交互式面板并叠加缓存/提示指标。

> 随着功能推进，此文档将持续更新，确保每个里程碑的工作量、依赖关系与风险透明可跟踪。
