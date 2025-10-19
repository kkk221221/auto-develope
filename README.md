# Auto‑Develope: 自进化代码编排系统（本机版）

本项目实现了可在本机运行的自进化编排管线：采样提示 → 生成候选 → L0–L3 分层评测 → 档案更新（NSGA‑II + 新颖度 + MAP‑Elites）→ 提示奖励与遥测 → 状态持久化与回放。已对接 OpenAI 兼容的推理 API（示例使用 Qwen DashScope 兼容接口）。

## 快速开始（本机）

1) 依赖

```bash
python -m pip install --upgrade pip
pip install -e .[dev]
```

2) 配置真实 LLM 可选（建议）

```bash
export LLM_API_MODEL='qwen-plus'
export DASHSCOPE_API_KEY='sk-...'
export LLM_API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export LLM_API_TEMPERATURE=0.6
```

3) 运行编排循环（演示 5 步）

```bash
python -m orchestrator.run_loop
```

Artifacts 将写入 `.artifacts/`：

- `map_elites.json` 与 `dashboard.html`：档案快照与热力图
- `prompt_telemetry.json`：提示臂奖励、温度、invalid 响应与 linucb_alpha
- `run_state.json`：断点续跑快照（档案/种群/Bandit/缓存/队列）
- `fewshot/<problem>.jsonl`：Few‑shot 案例库
- `git_lineage/`：谱系仓库（候选源码 + 补丁元数据）
- `tools/streamlit_app.py`：本地 Streamlit 面板（读取上述 artifacts）

4) 测试

```bash
pytest -q
```

5) 可选：Streamlit 可视化

```bash
pip install streamlit
streamlit run tools/streamlit_app.py
```

## 架构概览

- Orchestrator：`EvolutionOrchestrator` 负责编排与持久化
- 生成：`ProgramGenerator`（模板/AST 交叉/repair + 补丁关键标记校验）
- 评测：`ProblemEvaluator` + `TierExecutor`（L0–L3，AST 安全与超时/内存隔离）
- 档案/选择：`ArchiveManager` + `SelectionStrategy`（NSGA‑II + 新颖度 + MAP‑Elites）
- 提示策略：`PromptBandit`（Thompson Sampling + LinUCB 上下文打分 + invalid 熔断）
- Few‑shot：`.artifacts/fewshot/` 滚动沉淀成功/修复示例并在下次检索注入 Prompt

## 提示策略与上下文

- 强系统提示约束 LLM 仅返回严格 JSON：`{"version":1,"patches":[{"diff_type":"sr", ...}]}`
- Few‑shot：从谱系与候选沉淀 SEARCH/REPLACE 案例，按 `problem_id + failure_tags` 检索 ≤2 条并拼接到 Prompt Context
- LinUCB 上下文向量（归一化）：`[bias, problem_match, failure_density, complexity_norm, invalid_density, recent_reward]`
- α 自适应：成功时缓慢衰减，invalid 时回升；对 invalid 密度施加惩罚并添加 checklist 纠偏

## 分层评测

- L0：语法/类型/AST 安全检查
- L1/L2：核心与全量集，重复运行计算均值/分位数
- L3：对抗/压力集（可选）
- 评测在受限子进程执行，超时/异常会即时失败

## 持久化与回放

- `FilesystemPersistence` 将档案/种群/Bandit/缓存/队列写入 `run_state.json`
- 直接重新运行可断点续跑；删除该文件从头开始

## 观测与可视化

- 打开 `.artifacts/dashboard.html` 查看 MAP‑Elites 热力图
- 读取 `prompt_telemetry.json` 分析奖励趋势、invalid 统计与 `linucb_alpha`
- 可按 `docs/observability.md` 说明扩展到 Streamlit 或 Prometheus/OTEL（可选）

## 目录

- `orchestrator/`：编排、生成、评测、档案、Bandit、持久化等核心代码
- `problems/`：问题资产（数据生成、oracle、bench、tests）
- `solutions/workdir/`：各问题 baseline（含 EVOLVE‑BLOCK）
- `agents/prompts/`：提示模板（性能/鲁棒/repair/交叉）
- `docs/`：运行手册、治理、可观测性与系统设计

## 常见问题

- LLM 返回被拒绝（无 `diff_type="sr"` 或补丁缺少 `def solve`）：系统会回退模板，并在 Bandit 中累计 `PromptValidationError` 与 checklist 纠偏
- 评测卡在 L0：检查 EVOLVE 块是否语法正确且未触发 AST 黑名单
- 重跑从头开始：删除 `.artifacts/run_state.json`

## 当前状态

面向本机运行的目标，核心功能已稳定（完成度约 75–80%）。若未来希望扩展到分布式评测与在线可观测，可参照 `docs/self-evolving-system.md` 与 `docs/observability.md` 的建议继续演进。
