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
| **M3：高级交叉与压力测试** | AST/语义交叉、L3 压测、分布式评测 | `ast_crossover.py`、`evaluation.py`、`.github/workflows/evolve.yml` | ⏳ 进行中 | 实现 AST 节点拼接 + 冲突修复，补齐 L3 测试矩阵与 GitHub Actions 集成 |
| **M4：元提示进化与治理** | 提示元变异、观测、审计、治理 | `prompt_policy.py`、`caching.py`、`docs/`、未来的 `observability/` 组件 | ⏳ 进行中 | 引入提示模板基因库、指标采集、run replay 工具，完善安全策略 |

## 3. 子系统梳理

### 3.1 编排与生命周期管理
- **现状**：`orchestrator/run_loop.py` 管理父代采样、缓存命中、评测级联、档案更新与提示奖励；`models.py` 定义候选/指标/档案数据类。
- **缺口**：缺少与外部存储（PostgreSQL、对象存储）的接口，运行记录仅驻留内存；缺乏失败回放与断点续跑。
- **计划**：
  1. 抽象仓储接口（`PersistenceGateway`），在 `run_loop.py` 中替换内存状态。
  2. 提供 run checkpoint 序列化（候选、档案、bandit、缓存）及恢复脚本。
  3. 对接指标日志（OpenTelemetry/OpenMetrics），实现 `run_id` 级追踪。

### 3.2 候选生成与谱系
- **现状**：`generation.py` 内的 `ProgramGenerator` 支持基于 EVOLVE-BLOCK 的多样随机生成，跟踪父代与提示臂。
- **缺口**：缺乏对 Gemini CLI 或其它 LLM 代理的实际调用；交叉与修复策略尚未纳入；谱系信息未写回 Git。
- **计划**：
  1. 在 `generation.py` 新增 `GeminiAgentAdapter`，封装 `gemini-cli` CLI/API 调用，支持 JSON-only 输出与补丁结构校验。
  2. 集成 `ast_crossover.py` 与 `repair` 流程，实现交叉或失败修复的候选注入。
  3. 与 `solutions/workdir/` 建立 Git 分支或工作树写入，记录 `patch.diff` 与谱系元数据。

### 3.3 评测级联与调度
- **现状**：`evaluation.py` 实现 `ProblemEvaluator`、`TierExecutor`，可执行语法检查、AST 规则、数据集评估；`scheduler.py` 结合 Successive Halving 调度层级。
- **缺口**：L3 压测与压力数据集缺失；未封装 Docker/K8s/GitHub Actions 环境；安全策略（沙箱、资源配额）未落实。
- **计划**：
  1. 扩充 `problems/sample_problem/tests/` 与 `bench.py`，加入压力测试与对抗样例。
  2. 为 `TierExecutor` 增加容器执行后端（Docker API 或 GitHub Actions 驱动），并实现资源/网络限制。
  3. 输出标准化评测报告（JSON），写入对象存储并在 `run_loop` 中引用。

### 3.4 档案、选择与品质多样性
- **现状**：`selection.py` 维护 NSGA-II 非支配排序、拥挤距离、新颖度奖励；`behaviors.py` 定义特征提取；MAP-Elites 网格更新已实现。
- **缺口**：行为特征仍以占位数据生成；MAP-Elites 持久化和可视化缺失；迁徙/岛屿模型未落地。
- **计划**：
  1. 接入真实行为特征（覆盖率、热点、输出签名），需要从评测结果回传解析。
  2. 在 `selection.py` 中实现岛屿模型与迁徙策略（定期稀疏格采样、失败驱动移民）。
  3. 生成档案快照（CSV/JSON/可视化热力图），供 `docs/` 和观测面板使用。

### 3.5 缓存与可复现
- **现状**：`caching.py` 使用内容哈希实现评测结果复用。
- **缺口**：缺少跨进程/跨节点共享机制；缓存键未包含环境指纹；未集成指标以衡量命中率。
- **计划**：
  1. 提供 Redis/数据库后端，实现跨节点缓存共享。
  2. 扩展键结构（问题 ID、环境 fingerprint、评测配置 hash、随机种子）。
  3. 输出缓存统计与治理策略（TTL、清理、命中率跟踪）。

### 3.6 提示工程与多臂老虎机
- **现状**：`prompt_policy.py` 加载 `agents/prompts/*.md` 并使用 Thompson Sampling；`configs/bandit.yaml` 给出奖励配方。
- **缺口**：模板仍为静态文件；缺少元提示变异、随机格式化、性能退火；未将失败分类反馈给提示。
- **计划**：
  1. 设计 `PromptGenome` 结构体，记录模板权重、Checklist、Mutations；实现突变与交叉策略。
  2. 基于 `evaluation` 返回的失败类型/指标，建立奖励路由与上下文注入（例如提示中动态嵌入失败日志片段）。
  3. 引入提示 A/B 实验追踪（成功率、预算占比、平均收益）。

### 3.7 问题库与基线解决方案
- **现状**：`problems/sample_problem/` 提供基线问题、数据生成、测试、基准脚本；`solutions/workdir/sample_solution.py` 包含 EVOLVE-BLOCK。
- **缺口**：问题库规模有限，未覆盖性能/鲁棒/多目标场景；`data_gen.py` 与 `bench.py` 仅包含示例级逻辑。
- **计划**：
  1. 新增多个问题包（如最短路、背包、排序优化），每个问题包括 spec、oracle、数据生成、测试与 benchmark。
  2. 扩展基准脚本输出（性能中位数/IQR、内存峰值），并与评测缓存集成。
  3. 为每个问题提供初始解与 EVOLVE-BLOCK 标注，确保可复现起点。

### 3.8 CI/CD 与自动化
- **现状**：`Dockerfile`、`.github/workflows/evolve.yml`、`pyproject.toml` 支持构建与测试；`tests/` 内含单元测试覆盖档案与缓存逻辑。
- **缺口**：CI 未串联真实评测与报告汇总；缺乏静态分析/格式化；GitHub Action 未配置密钥管理与 artifact 上传。
- **计划**：
  1. 在 workflow 中增加并发矩阵（候选评测）、artifact 上传（补丁、metrics、日志）。
  2. 集成 `ruff`/`mypy`/`pytest`/`bench` 等检查，确保质量门禁。
  3. 编写部署文档与示例 GitHub Action 使用说明（结合 `gemini-cli` 官方 Action）。

### 3.9 文档、观测与治理
- **现状**：`docs/self-evolving-system.md` 描述总体设计；`docs/progress.md` 用于追踪进度。
- **缺口**：缺少操作手册、API 文档、治理策略细则（安全、合规、审计）；缺少观测面板与图表。
- **计划**：
  1. 编写《运行手册》《开发者指南》《治理与安全策略》三大文档。
  2. 设计观测面板（Grafana/Streamlit）原型，展示吞吐、档案热力图、失败分类等。
  3. 提供审计流程（变更记录、日志格式、Run Replay 指南）。

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

- [ ] `ast_crossover.py`：实现补丁拼接 → AST 片段组合 → 语义合并最小版。
- [ ] `evaluation.py`：新增 L3 压测入口、压力数据、资源限制。
- [ ] `prompt_policy.py`：引入元提示变异（权重/Checklist/示例采样）。
- [ ] `caching.py`：支持外部缓存后端与命中率指标。
- [ ] `docs/`：补充运行手册、治理策略、观测面板草图。
- [ ] `.github/workflows/evolve.yml`：并发矩阵、artifact 上传、静态检查。

> 随着功能推进，此文档将持续更新，确保每个里程碑的工作量、依赖关系与风险透明可跟踪。
