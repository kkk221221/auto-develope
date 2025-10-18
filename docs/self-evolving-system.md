# 基于 Gemini CLI 的自进化算法系统设计

> 面向在 `google-gemini/gemini-cli` 基础上搭建一个与 AlphaEvolve 思路一致的自进化算法系统。本设计围绕体系结构、数据与接口、演化算法细节、提示工程与 LLM 编排、评测级联与调度、变异/交叉实现路线、观测与治理、安全与合规、成本与伸缩、可复现性、落地里程碑与验收标准等核心主题展开，并对关键外部事实提供出处。

‼️ 关键参考：
- **Gemini CLI**：官方 README 明确其是开源 AI 代理，终端优先、支持文件操作、Shell、Web 抓取、Google Search grounding、MCP 扩展，提供 GitHub Action 集成，并在“登录 Google 账户”形态下提供 1M tokens 上下文与 60 RPM / 1000 RPD 的免费配额（以官方文档为准）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))
- **AlphaEvolve**：DeepMind 公布的进化式代码代理：用户定义“做什么（What）”，系统自动完成“怎么做（How）”；核心组件包括程序数据库、提示采样器、LLM 组、评测池、分布式控制器循环；支持多目标优化，对代码库进行 diff/patch 级别演化；被演化区域通过 `# EVOLVE-BLOCK-START/END` 标注；还采用 “SEARCH/REPLACE” 差异格式产生可定位的修改。([Google DeepMind](https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ "AlphaEvolve: A Gemini-powered coding agent for designing advanced algorithms - Google DeepMind"))
- **MAP‑Elites**：品质多样性（QD）族算法，维护维度化网格以同时保留多样且高质量的精英方案。([arXiv](https://arxiv.org/abs/1504.04909?utm_source=chatgpt.com "Illuminating search spaces by mapping elites"))

---

## 0. 设计原则

1. **吞吐优先（Throughput over latency）**：用分层评测与预算调度，在同等计算成本下评估更多候选。
2. **可复现（Reproducible by default）**：Docker 镜像、固定种子、硬件指纹、统一统计（中位数/IQR）。
3. **安全边界（Hard sandbox）**：评测阶段闭网、资源配额、AST 规则屏蔽危险 API。
4. **可解释与可回放（Explainable & Replayable）**：每次修改以结构化补丁与因果日志记录，可一键回放。
5. **品质多样性（Quality‑Diversity）**：NSGA‑II + 新颖度 + MAP‑Elites；避免早收敛。
6. **提示也进化（Prompts evolve too）**：Bandit 调度与元提示进化闭环。

---

## 1. 系统架构（System Architecture）

### 1.1 组件与数据流（对齐 AlphaEvolve）

```
┌──────────────┐   样本/精英/失败   ┌─────────────┐   结构化Prompt  ┌───────────┐
│ Program DB   │ ─────────────────▶ │ Prompt     │ ───────────────▶ │ LLMs      │
│ + Archive    │   指标/特征/谱系   │ Sampler    │   (多臂/元进化)   │ Ensemble  │
└─────┬────────┘                   └────┬────────┘                  └────┬──────┘
      │                                   │                           代码diff│
      │                                   ▼                                 ▼
      │                           ┌──────────────┐  并行执行/打分   ┌─────────────┐
      └──────────────────────────▶│ Evaluators   │────────────────▶ │ Orchestrator│
                                  │  Pool (L0-3) │  指标/日志/特征  │  (NSGA-II/QD)│
                                  └──────┬───────┘                 └─────┬────────┘
                                         │ 更新DB/Archive/缓存             │ 选拔/迁徙
                                         └─────────────────────────────────┘
```

**落地基座**：

- **执行代理**：Gemini CLI（文件编辑、Shell、Web 抓取、MCP 扩展、GitHub Action 集成）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))
- **分布式控制器**：Python `asyncio` 服务（支持多实例选主）。
- **存储**：PostgreSQL（元数据）、对象存储（工件/补丁）、向量库（特征/提示语义）、Git（谱系）。
- **队列**：Redis/Cloud PubSub（任务/回执/心跳）。
- **评测节点**：K8s Jobs 或 GitHub Actions 并发矩阵（与 gemini‑cli action 结合）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))

### 1.2 用户定义（What）

- **初始程序**：可执行、包含 `# EVOLVE-BLOCK-START/END` 标注的可演化区段；即便是“返回常量”也可。
- **评估函数 `h`**：接受程序，输出一组可自动评分的标量（默认最大化）。
- **可选配置**：提示模板/背景知识（PDF/公式/代码片段）、LLM 清单、资源预算。

### 1.3 自动化流程（How）

- **程序数据库**：存储代码、分数、失败分类、行为特征 φ；支持按“灵感”抽样。
- **提示采样器**：从数据库抽优、取背景、拼装动态 Prompt；可随机格式化与元提示进化。
- **LLM 组**：以 Flash→多产、Pro→突破的分工进行两段式生成与加审；可替换后端。
- **评测池**：对新程序并行运行评估级联与基准。
- **分布式控制器循环**：异步推进 sample→generate→validate→apply→evaluate→select。

### 1.4 当前实现映射（2024Q4 仓库快照）

- **编排循环与持久化**：`EvolutionOrchestrator` 负责装载级联配置、调度 `EvaluationScheduler`、处理缓存命中并将档案/种群/提示臂快照写入 `RunState`；若存在历史快照会在启动时自动恢复待评估队列与缓存统计。【F:orchestrator/run_loop.py†L35-L188】【F:orchestrator/persistence.py†L13-L108】
- **候选生成与 Gemini 集成**：`ProgramGenerator` 根据提示臂渲染 EVOLVE 区块；若配置了 `GeminiAgentAdapter` 则优先消费 CLI 的 SEARCH/REPLACE 片段并保留遥测元数据，失败时退回内置模板变异；同一组件也提供 AST 引导的双亲交叉能力。【F:orchestrator/generation.py†L106-L210】【F:orchestrator/agents.py†L28-L124】
- **提示老虎机与元提示**：`PromptBandit` 从模板目录解析臂配置，使用 Thompson Sampling 采样，并在奖励或失败反馈到来时更新温度、指令顺序与 checklist，以形成轻量元提示进化闭环。【F:orchestrator/prompt_policy.py†L13-L223】
- **评测级联与行为特征**：`ProblemEvaluator` 在 `TierExecutor` 驱动下执行 L0→L3 检查，输出稳健统计、对抗套件评分、行为特征（覆盖哈希、运行时分位数）；配置由 `configs/tiers.yaml` 加载。【F:orchestrator/evaluation.py†L18-L240】
- **档案与选择策略**：`ArchiveManager` 维护 NSGA-II Pareto 前沿、新颖度评分与 MAP-Elites 网格；`SelectionStrategy` 结合交叉概率、拥挤距离与新颖度权重挑选下一代或触发 AST 交叉。【F:orchestrator/selection.py†L106-L386】
- **评测缓存**：`CacheManager` 基于环境指纹、补丁 payload 与源文件内容构建哈希键，支持内存或文件系统后端并统计命中率，既能复用评测结果也能通过快照恢复命中状态。【F:orchestrator/caching.py†L1-L205】
- **基准与问题资产**：`problems/sample_problem` 提供数据生成、对抗样本与 `bench.py` JSON 基准脚本，支持在压力模式下验证评测路径。【F:problems/sample_problem/bench.py†L1-L41】

---

## 2. 数据与接口（Schemas & APIs）

### 2.1 Program（个体）与谱系

```yaml
program:
  id: str
  parents: [str]                 # 支持1或2亲本（交叉）
  gen: int                       # 代数
  repo_ref: {commit, tree}       # Git 快照
  patch: {format: "unified|sr", payload: "..."}   # 统一diff或SEARCH/REPLACE
  prompt_arm: str                # 产出该候选的提示“臂”
  llm_backend: {flash|pro|...}
  features:                      # 行为/结构特征φ（用于新颖度与MAP-Elites）
    coverage_bits: bitset
    hotspots: {fn: time_ratio}
    output_sig: hash
  metrics:                       # 多目标
    acc: float
    runtime_ms: float
    mem_peak_mb: float
    loc: int
    cyclomatic: float
    robustness: float
    llm_style: float             # 由“打分LLM”给出的可读性/设计质量
  eval_pass: [L0, L1, L2, L3]
  status: {pending|running|succeeded|failed}
  seeds: {rng:int, compile:int}
  created_at: ts
  evaluated_at: ts
```

### 2.2 Prompt 资产（A/B + 元进化）

```yaml
prompt_variant:
  name: str
  template: str                  # 强制 JSON-only 输出
  priors: {success: float, fail: float}
  recent_reward: float
  horizon_gens: int
  mutation_space:
    - {key: goal_weights.time, range: [0.1, 0.6]}
    - {key: checklist, ops: [add, remove, rephrase]}
```

### 2.3 Archive（QD + Pareto）

```yaml
archive:
  pareto_front: [program_id]     # NSGA-II 精英
  map_elites:
    dims: [complexity_bin, robustness_bin]
    cells: {"(i,j)": program_id}
```

### 2.4 控制器 gRPC / HTTP（示例）

- `POST /orchestrate/tick`：推进一小步（采样→触发 LLM→入队 L0）。
- `POST /eval/submit`：评测结果回传（附指标/日志/特征 φ）。
- `GET /archive/pareto`：查询当前 Pareto 集。
- `POST /prompts/bandit/update`：按奖励更新臂权重。

---

## 3. LLM 编排与提示工程（Prompting & LLM Ensemble）

### 3.1 结构化输出与最小可变更

- 要求 LLM 仅输出 JSON，字段：`plan[] / patches[] / risk[] / checklist[] / telemetry_tags[]`。
- 补丁格式：
  - `unified diff`（大改动/跨文件）。
  - **SEARCH/REPLACE**（对齐 AlphaEvolve 的局部替换语法，定位精确、可幂等）。
- 大仓改动必须先输出迁移计划（多步小补丁），再按步执行。

### 3.2 Prompt Sampler（信息来源与组装）

- **来源**：Program DB 的精英/失败多样本、行为远点（novel）、用户背景 PDF/公式、评测摘要。
- **组装**：Few-shot 引入 2–3 个高分方案及“失败→修复”的因果链；随机格式化增强多样性；目标权重随代数退火。

### 3.3 生成级联与模型分工

- **阶段 A（探索）**：Gemini Flash 多产候选（较低温度 + 语义多样性约束）。
- **阶段 B（打磨）**：对 A 的 Top‑K 由 Pro 复查与二次变异/融合（更严格 checklist）。
- **失败快速修复**：独立的 `repair.md` 模板读取编译/测试日志，生成微补丁。

### 3.4 提示 A/B 与 Bandit 调度

- 臂 = 模板变体（性能优先/鲁棒优先/简洁优先/探索优先）。
- 奖励 = `0.6*Δacc + 0.3*Δruntime_gain + 0.1*Δrobust`（3 代滚动）。
- 算法：**Thompson Sampling**；冷启均匀探索，热启承继历史。

### 3.5 元提示进化（Meta‑Prompt Evolution）

- 每 `K` 代对模板的权重/checklist/指令顺序/示例取样做小步变异。
- 在 L0/L1 沙箱对候选 Prompt 快测，胜者进入“臂池”。

---

## 4. 演化算法（Evolution: NSGA‑II + 新颖度 + MAP‑Elites）

### 4.1 个体与操作符

- **个体**：代码库快照 + 结构化补丁 + 谱系与运行环境元数据。
- **变异**（主力）：数据结构替换、算法范式切换、参数/启发式调优、并行化、缓存化、边界稳健化。
- **交叉**（分阶段，见 §6）：补丁拼接 → AST 片段重组 → 语义合并。

### 4.2 选择与多目标

- 指标：`acc, runtime_ms, mem_peak, loc, cyclomatic, robustness, llm_style`。
- **NSGA‑II** 非支配排序 + 拥挤距离。
- **新颖度**：`novelty = mean_dist(φ_i, Archive ∪ Cohort)`（cosine / Jaccard）。
- 选择分数：
  
  \[
  S = \text{rank}_{\text{NSGA-II}} + \alpha_t \cdot \text{novelty} - \beta \cdot \text{instability}
  \]
  
  其中 \(\alpha_t\) 退火，前期鼓励探索。

### 4.3 MAP‑Elites（品质多样性）

- 网格维度示例：`complexity_bin(LOC/圈复杂度)` × `robustness_bin(对抗集得分)`。
- 新个体落格后胜过格内精英则替换；定期从稀疏格采样“移民”，维持多样性。([arXiv](https://arxiv.org/abs/1504.04909?utm_source=chatgpt.com "Illuminating search spaces by mapping elites"))

### 4.4 岛屿模型与迁徙

- 岛屿按策略标签划分（性能岛/鲁棒岛/简洁岛/探索岛）。
- 每 `M` 代按互补性（失败类型/热点/行为距离）迁徙 5–10%。

---

## 5. 高效评测（Evaluation Cascade & Scheduling）

### 5.1 评测级联（L0→L3）

- **L0 Fast（≤10s/体）**：语法/类型/Lint、AST 规则、复杂度预估、影响面分析、冷编译。
- **L1 Core（≤60s）**：核心单测 + 属性测试子集（固定种子）、失败分类。
- **L2 Full+Bench（≤6min）**：全量测试 + 多次运行取中位/IQR、峰值内存。
- **L3 Stress & Adversarial（≤20min，仅 Top 20–30%）**：对抗/混沌/大样本。

### 5.2 预算化调度

- **Successive Halving / Hyperband**：层层淘汰与预算提升。
- **优先队列**：按上层分数 + 不确定度（方差/置信区间）排程。
- **缓存与影响面**：
  - 内容哈希（按子树/目标函数）→ L1/L2 结果复用。
  - 测试影响分析：构建“用例→覆盖文件/函数”的倒排索引，只跑受影响子集。
  - 定期全量回归以校准缓存。

### 5.3 统计与去抖

- 性能采用稳健统计（中位数 + IQR）。
- 控制 CPU 亲和/频率、重复次数与 warm‑up。
- 标注 Flaky 测试，纳入“稳定度阈值”门控。

---

## 6. 变异与交叉（Operators）——从简到强

### 6.1 变异（Mutate）

- **语义变异**：替换数据结构/范式（分治↔动态规划；朴素↔启发式；单机↔并行）。
- **参数调优**：剪枝阈值、评估步数、近似比例。
- **瓶颈导向**：依据剖析热点与失败分类，定向优化与修复。

**mutate 模板（片段，JSON only）**

```json
{
  "plan": [{"step":"改写函数X为堆优化","files":["..."],"effect":"O(n log n)→O(n)"}],
  "patches": [{"file":"...", "diff_type":"sr", "payload":"<<<<< SEARCH ... >>>>>>> REPLACE ..."}],
  "risk": ["边界k=0"],
  "checklist": ["tests/core_* 通过", "cyclomatic(functionX)<=10"],
  "telemetry_tags": ["ds:heap","hotpath","pruning"]
}
```

### 6.2 交叉（Crossover）

- **阶段 1：补丁拼接（MVP）**：非重叠补丁直接合并；冲突则回退到单亲本+微变异。
- **阶段 2：AST 片段重组**：以函数/类为“基因”，按接口相容性匹配与重命名，缺失符号用适配层补齐。
- **阶段 3：语义合并（LLM 引导）**：先产出融合设计与冲突表，再生成最小补丁。
- **失败降级**：无法通过 L0 → 回退单亲本 + repair。

---

## 7. 补丁语法与应用引擎（Patcher）

1. **SEARCH/REPLACE（SR）**

```
<<<<< SEARCH
<anchor 或原片段>
=======
<替换片段>
>>>>> REPLACE
```

- 用锚点 + 语义上下文行稳定匹配。
- 多锚点+容错（空白/注释忽略）。
- **幂等**：重复应用不产生副作用。

2. **Unified diff**

- 适合大范围或跨文件变更。
- 变更前后格式化 + 静态检查防止脏补丁落库。

3. **应用流程**

- schema 校验 → 干跑（dry‑run）→ 冲突检测 → 最小化补丁 → 生成工作副本 → 构建 → 入队 L0。

---

## 8. 存储、缓存与向量检索

- **PostgreSQL**：Program 元数据、指标、事件、谱系。
- **对象存储**：工作副本压缩包、补丁、评测报告、剖析火焰图。
- **向量库**：
  - 代码片段/设计备忘录/提示语义的嵌入检索。
  - 行为特征 φ 的近邻搜索（新颖度）。
- **缓存键**：`{problem_id}-{subtree_hash}-{env_fingerprint}-{seed}`。

---

## 9. 观测、度量与回放（Observability）

- **指标**：吞吐（个体/小时）、层级通过率、平均耗时、CPU/GPU 时、缓存命中、失败分类、超时率。
- **SLO/SLA**：在给定预算下 24h 内完成 ≥N 次 L0/L1。
- **日志**：关键节点（生成→应用→L0/L1/L2/L3→选择/淘汰）打点。
- **追踪**：OpenTelemetry 贯穿控制器、LLM 调用、评测节点。
- **回放**：依据 `run_id` 恢复镜像与种子，复现实验并生成误差条。

---

## 10. 安全、合规与治理

- **闭卷评测**：评测（L0–L3）阶段默认禁网；仅“计划阶段”可白名单抓取参考。
- **许可证与依赖**：SPDX 扫描、依赖体积上限、License 变更提醒。
- **AST 规则**：禁用危险 API（文件写入外逸、子进程联网等）。
- **Prompt 注入防护**：对来自代码/数据的文本上下文去指令化（只读、转义、分通道）。
- **Git 治理**：每个体独立分支/目录、必经 CI、可一键回滚。
- **人机协作**：语义合并须输出“冲突表 + 取舍理由”，便于审计。

---

## 11. 伸缩与成本

- **LLM 成本**：Flash 承担高吞吐探索，Pro 只在 Top‑K 上“深思考”；阈值与 K 动态调参（队列长度/错误率/收益）。
- **评测成本**：Successive Halving + 缓存 + 影响面。
- **算力编排**：K8s 自动扩缩，GitHub Actions 矩阵并行（与 gemini‑cli action 集成）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))
- **配额与节流**：遵循 gemini‑cli 免费配额与速率限制（60 RPM/1000 RPD 以官方为准）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))

---

## 12. 可复现性（Reproducibility）

- **环境**：Docker 镜像 + 依赖锁（PiP/Poetry）+ OS 指纹 + 固定 `PYTHONHASHSEED`。
- **统计**：重复运行、稳健统计（中位/IQR）、误差条。
- **谱系**：Git 分支 + `run_id` → 一键回放。

---

## 13. 具体配置样例

### 13.1 层级与预算

```yaml
scheduler:
  population: 64
  retention: {L0: 0.65, L1: 0.40, L2: 0.20, L3: 0.05}
  budgets_s: {L0: 10, L1: 60, L2: 360, L3: 1200}
novelty:
  probes: 128
  metric: cosine
  alpha_0: 1.0
  tau: 8
map_elites:
  bins: {complexity: 8, robustness: 8}
bandit:
  arms: [perf_first, robust_first, simplicity_first, exploration]
  priors: {success: 1.5, fail: 1.0}
  reward: "0.6*acc_gain + 0.3*time_gain + 0.1*robust_gain"
  horizon_gens: 3
```

### 13.2 `tiers.yaml`（评测级联）

```yaml
L0:
  timeout_s: 10
  checks: [lint, typecheck, ast_rules]
  max_cyclomatic: 12
L1:
  timeout_s: 60
  tests: ["core_*", "prop_*"]
L2:
  timeout_s: 360
  repeats: 5
  percentiles: [0.5, 0.9]
L3:
  timeout_s: 1200
  stress_suites: ["adversarial_*", "chaos_*"]
```

---

## 14. 控制器主循环（伪代码）

```python
while not budget_exhausted:
    # 采样父本与灵感
    parents, inspirations = sample(DB, Archive, islands=True)

    # 组装提示并选择 Prompt“臂”
    arm = bandit.pick()
    prompt = assemble_prompt(parents, inspirations, arm, context=bg_knowledge)

    # 生成候选（Flash→Pro 级联）
    cand = generate_with_ensemble(prompt)  # JSON-only; patches in {sr|unified}

    # 补丁校验与应用
    if not validate_schema(cand): continue
    workdir = apply_patch(repo_base, cand.patches)  # 幂等干跑+最小化补丁

    # 入队评测（层级淘汰与预算提升）
    enqueue_eval(workdir, tier='L0', run_id=uid())
    for tier in ['L0','L1','L2','L3']:
        res = await_result(run_id, timeout=budget[tier])
        log_metrics(DB, res)
        if pass_to_next(res, tier):
            enqueue_eval(workdir, next_tier(tier))
        else:
            break

    # 更新档案与选择
    phi = extract_behavior_features(res)      # coverage/hotspots/output_sig
    update_archive(DB, Archive, cand, phi)
    bandit.update(arm, reward=res.delta)      # 多臂老虎机
    select_next_generation(DB, Archive)       # NSGA-II + novelty + MAP-Elites
```

---

## 15. 端到端例子（问题：最短路 / 背包）

- `problems/shortest_path/spec.yaml`：数据分布（稀疏/稠密）、约束、目标权重。
- `oracle.py`：对照或性质判定。
- `tests/`：核心 + 属性 + 对抗。
- `bench.py`：生成规模与重复次数，输出统一 JSON。
- `solutions/workdir/`：初始实现（Dijkstra/多源 BFS），EVOLVE‑BLOCK 包围关键函数。

> 这与 AlphaEvolve 在不同领域以“最小骨架 + 评估器 h”启动实验的做法一致。

---

## 16. GitHub Actions（与 gemini‑cli 集成）

- **矩阵并发**：每个体一个 Job。
- **步骤**：Checkout → 构建 Docker → `gemini smart-edit` 变异 → 运行 L0/L1/L2 → 上传工件（`fitness.json`/`patch.diff`/剖析报告） → 汇总 Job 计算 Pareto 与档案 → 写回报告。
- README 中提供了官方 Action 可直接集成（PR 审阅、Issue 分拣、@gemini‑cli on-demand）。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))

---

## 17. 里程碑与验收

- **M1（1–2 周）**：L0/L1 跑通；Bandit 冷启；缓存与影响面生效。
- **M2（2–3 周）**：NSGA‑II + 新颖度 + MAP‑Elites 档案。
- **M3（2 周）**：AST 级交叉 MVP + 语义合并 + L3 压力集。
- **M4（持续）**：元提示进化、指标面板、治理与审计完善。

**验收（DoD）**

- 在固定预算下 24h 内完成 ≥10,000 次 L0 评测。
- ≥2 个公开基准集上，Pareto 集明显优于初始程序。
- 任意 `run_id` 可一键回放并在误差条内复现。
- 报表含：代际曲线、档案热力图、失败谱系、提示臂贡献度。

---

## 18. 深入反思与风险缓释（关键点逐条）

1. **提示工程上限**：
   - 采用结构化 JSON+最小补丁+checklist 硬约束。
   - Bandit + 元进化使模板自适应，避免人工“炼丹”。
   - 失败类型驱动为模板注入领域化子指令，闭环学习。
2. **评测成本**：
   - 以 Successive Halving 配合缓存/TIA。
   - 对 Top‑K 再跑 L3。
   - 针对不稳定用例做 Flaky 隔离并设稳定度门槛。
3. **交叉难度**：
   - 由简入难：补丁拼接 → AST 重组 → 语义合并。
   - 全链路失败降级（回退单亲本 + repair）。
4. **早收敛**：
   - 新颖度奖励 + 移民机制 + MAP‑Elites。
   - 选择阶段加拥挤度惩罚。
   - α 退火策略保证前期探索、后期收敛。
5. **性能测量噪声**：
   - 绑定 CPU 亲和/频率、重复多次取中位/IQR。
   - 控制背景进程与 I/O 抖动。
   - 使用控制变量（基线例程）校准。
6. **安全与注入**：
   - 评测闭网、白名单工具。
   - 代码/数据注释与外部文本去指令化。
   - AST 禁用危险 API。
   - 依赖与许可证持续审计。
7. **上下文管理**：
   - 利用 gemini‑cli 的长上下文与会话检查点；Prompt 只拼装必要子集，避免上下文污染。([GitHub](https://github.com/google-gemini/gemini-cli "GitHub - google-gemini/gemini-cli: An open-source AI agent that brings the power of Gemini directly into your terminal."))
   - 大文档（PDF/公式）只抽取片段摘要进入 Prompt。
8. **法律与道德**：
   - 开源合规（SPDX）与第三方素材的版权标注。
   - “打分 LLM”的主观属性仅作软约束，保留人工复核入口。

---

## 19. 可直接落库的目录骨架（建议）

```
repo/
  orchestrator/
    run_loop.py
    selection.py       # NSGA-II + novelty
    behaviors.py       # 行为特征抽取
    scheduler.py       # Successive Halving / Hyperband
    caching.py         # 内容哈希 + TIA
    prompt_policy.py   # Bandit + 元提示进化
    ast_crossover.py   # AST 重组（MVP 可留空）
  agents/prompts/
    mutate.perf_first.md
    mutate.robust_first.md
    mutate.simple_first.md
    crossover.v1.md
    repair.v1.md
  problems/<name>/
    spec.yaml
    oracle.py
    data_gen.py
    tests/
    bench.py
  solutions/workdir/
  configs/
    tiers.yaml
    scheduler.yaml
    bandit.yaml
  .github/workflows/evolve.yml
  Dockerfile
  pyproject.toml
```

---

### 结语

以上方案最大化复用 Gemini CLI 的工程能力（多文件编辑、Shell、Web 抓取、MCP 扩展、GitHub Actions 集成），并对齐 AlphaEvolve 的核心思想与接口约定（EVOLVE-BLOCK、搜索/替换式 diff、程序数据库/提示采样/评估池/分布式控制器）。在实践中，建议先从一两个“结构清晰、评测可靠”的算法问题启动，快速打通 M1–M2，再逐步引入 AST‑级交叉与元提示进化。
