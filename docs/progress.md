# 项目进度与交付规划

本文档基于《docs/self-evolving-system.md》的体系目标，对当前代码仓库进行全面梳理，并给出余下工作的实施计划，便于持续追踪。

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
- **现状**：`generation.py` 内的 `ProgramGenerator` 支持基于 EVOLVE-BLOCK 的多样随机生成，跟踪父代与提示臂；新增 `GeminiAgentAdapter` 可直接调用已登录的 `gemini-cli` 并在失败时回退模板。
- **缺口**：交叉与修复策略尚未纳入；谱系信息未写回 Git；CLI 仍需接入远程存储与错误分级重试。
- **计划**：
  1. 扩展 `GeminiAgentAdapter` 接入提示上下文的失败日志摘要，并支持多模型路由。
  2. 集成 `ast_crossover.py` 与 `repair` 流程，实现交叉或失败修复的候选注入。
  3. 与 `solutions/workdir/` 建立 Git 分支或工作树写入，记录 `patch.diff` 与谱系元数据。

### 3.3 评测级联与调度
- **现状**：`ProblemEvaluator.evaluate` 支持 L3 压测、对抗/噪声数据、运行时分位数；`TierExecutor` 依据 `TierSpec.max_cyclomatic/max_runtime_ms` 判定通过，`bench.py` 可在压力模式下输出 JSON。
- **缺口**：容器化执行与资源隔离仍为后续工作；评测报告尚未落盘对象存储。
- **计划**：
  1. 接入容器/K8s 执行后端，落实资源配额与网络沙箱。
  2. 将 `EvaluationResult` 的日志与分位数写入工件，结合对象存储形成回放。
  3. 在多问题集上回归评测，以验证压力样例的泛化效果。

### 3.4 档案、选择与品质多样性
- **现状**：评测行为特征已由 `ProblemEvaluator` 填充运行时分位数与覆盖度；`selection.py` 引入 AST 交叉与失败回退，MAP-Elites 继续更新。
- **缺口**：MAP-Elites 快照与岛屿迁徙仍未实现；需要生成可视化报表。
- **计划**：
  1. 将档案快照导出为 CSV/JSON，并在 `docs/observability.md` 提到的面板中展示。
  2. 实装岛屿迁徙策略，结合失败标签调度移民。
  3. 为交叉流程添加冲突降级与谱系可视化。

### 3.5 缓存与可复现
- **现状**：`CacheManager` 支持环境指纹、命中率统计与 `FilesystemCacheBackend` 持久化；`CacheEntry` 可序列化 JSON。
- **缺口**：仍需接入 Redis/数据库等共享缓存；需建立 TTL/清理策略。
- **计划**：
  1. 提供网络化缓存实现（如 Redis）。
  2. 引入 TTL 与垃圾回收策略，防止磁盘膨胀。
  3. 将缓存指标上报至可观测性面板。

### 3.6 提示工程与多臂老虎机
- **现状**：`PromptBandit` 引入 `PromptGenome`，支持指令随机化、温度调节、失败标签 checklist；奖励衰减结合历史轨迹。
- **缺口**：尚未根据评测日志自动注入上下文片段；提示 A/B 统计需要持久化。
- **计划**：
  1. 将失败日志摘要注入提示上下文，形成领域化反馈。
  2. 记录每臂调用次数与收益，导出 A/B 指标至观测面板。
  3. 探索模板交叉/突变策略以扩大提示基因库。

### 3.7 问题库与基线解决方案
- **现状**：`problems/sample_problem/` 提供基线问题、数据生成、测试、基准脚本；`solutions/workdir/sample_solution.py` 包含 EVOLVE-BLOCK。
- **缺口**：问题库规模有限，未覆盖性能/鲁棒/多目标场景；`data_gen.py` 与 `bench.py` 仅包含示例级逻辑。
- **计划**：
  1. 新增多个问题包（如最短路、背包、排序优化），每个问题包括 spec、oracle、数据生成、测试与 benchmark。
  2. 扩展基准脚本输出（性能中位数/IQR、内存峰值），并与评测缓存集成。
  3. 为每个问题提供初始解与 EVOLVE-BLOCK 标注，确保可复现起点。

### 3.8 CI/CD 与自动化
- **现状**：`evolve` workflow 包含质量门禁（ruff/mypy/pytest）与两轮候选演示，并上传 `.artifacts`；`pyproject.toml` 提供 dev 依赖。
- **缺口**：缺少 Secrets 管理与多问题矩阵；需要集成基准数据与报告汇总。
- **计划**：
  1. 扩展矩阵维度（问题集、运行模式），引入密钥管理模板。
  2. 将评测结果汇总为 JSON artifact，供后续管线消费。
  3. 在 README 中补充 GitHub Actions 使用指南。

### 3.9 文档、观测与治理
- **现状**：新增《docs/runbook.md》《docs/governance.md》《docs/observability.md》覆盖操作、治理、指标；总体设计与进度文档同步更新。
- **缺口**：开发者 API 指南仍待撰写；观测面板需落地原型。
- **计划**：
  1. 编写 API/模块参考文档，便于扩展模块接入。
  2. 实现观测面板 MVP（Streamlit 或 Grafana）。
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

> 随着功能推进，此文档将持续更新，确保每个里程碑的工作量、依赖关系与风险透明可跟踪。
