# 运行手册（Runbook）

本运行手册提供在本仓库部署与操作自进化算法系统的常见流程、命令及排障指引。配合《docs/self-evolving-system.md》设计说明与《docs/governance.md》《docs/observability.md》一起使用。

## 1. 环境准备

1. **Python 3.11**：系统以 3.11 为基线，推荐使用 `pyenv` 或项目提供的 Dockerfile。
2. **依赖安装**：
   ```bash
   python -m pip install --upgrade pip
   pip install -e .[dev]
   ```
   `dev` 额外安装 `pytest`、`ruff`、`mypy` 以支持 CI 与本地质量检查。
3. **目录约定**：候选工作目录写入 `.artifacts/candidates/`，缓存目录默认为内存，可通过 `CacheManager(environment_fingerprint=..., backend=FilesystemCacheBackend(Path(".cache/evals")))` 持久化。
4. **LLM API 凭据管理**：将访问令牌保存在 CI/CD 密钥或本地 `.env` 文件中，运行前导出 `LLM_API_KEY`；如需细粒度审计，可结合密钥轮换服务或使用短期会话令牌。系统内置 `DEFAULT_SYSTEM_PROMPT` 约束 LLM 输出结构，如需自定义可显式设置 `LLM_API_SYSTEM_PROMPT`，但必须保持 `version=1`、`diff_type="sr"` 的 JSON schema。

## 2. 常见操作

### 2.1 启动编排循环

```bash
python -m orchestrator.run_loop
```

该命令执行 `EvolutionOrchestrator.demo_run()`：
- 读取 `configs/tiers.yaml` 级联配置，依序运行 L0→L3；
- 解析 `configs/problems.json` 并根据 `problem_id` 轮转候选生成/修复队列；可通过环境变量 `EVOLVE_PROBLEM` 指定起始问题岛；
- 调用 `PromptBandit` 采样提示臂，包含元提示随机化与失败反馈；
- 使用 `ProgramGenerator.spawn_candidate(arm_name, PromptMaterialization)` 或 `spawn_crossover_candidate()` 产生候选；
- 通过 `TierExecutor` 调用 `ProblemEvaluator`，获取指标与 `BehaviorFeatures`；
- 将结果写入 `ArchiveManager`、`SelectionStrategy` 与缓存。
- 将 MAP-Elites 快照写入 `.artifacts/map_elites.json` 并自动渲染 `.artifacts/dashboard.html` 热力图，同时把提示臂遥测导出至 `.artifacts/prompt_telemetry.json`。
- 通过 `GitLineageTracker` 将候选源代码与补丁元数据提交至 `.artifacts/git_lineage/` Git 仓库，便于审计与回放。
- 每次 step 结束都会刷新 `.artifacts/run_state.json`，其中包含候选队列、Bandit 权重与缓存统计；若想从干净状态启动，可删除该文件重新运行。

> ℹ️ Demo 运行会自动启用 `FilesystemPersistence`，将档案、种群、Bandit 状态、缓存摘要与待评估队列写入 `.artifacts/run_state.json`。重新执行命令将从快照恢复；如需重新开始，可手动删除该文件。

### 2.2 断点续跑与持久化

- 生产模式建议显式实例化 `FilesystemPersistence(Path("/path/to/state.json"))`，并传入 `EvolutionOrchestrator` 构造函数。
- 利用 `orchestrator/persistence.py` 中的 `RunState` 可对 `pending_candidates` 做离线分析，或在 CI 结束后保存状态供下次运行继续。
- 若需导出数据库版本，可实现自定义 `PersistenceGateway`（例如写入 PostgreSQL/对象存储），再传入 orchestrator。

### 2.3 运行测试与静态检查

```bash
ruff check .
mypy orchestrator
pytest -q
```

CI Workflow `evolve` 会在 `quality` job 中执行以上三步，确保提交满足质量门槛。

### 2.4 运行基准脚本

```bash
python problems/sample_problem/bench.py
python problems/shortest_path/bench.py
python problems/knapsack/bench.py
```

脚本利用 `ProblemEvaluator` 在 `stress=True`、多次重复下输出 JSON 指标，供回归分析或成本估算；可据此扩展新的问题包。

### 2.5 查看谱系与仪表盘工件

- **谱系仓库**：`GitLineageTracker` 会在 `.artifacts/git_lineage/` 初始化 Git 仓库，按问题域分支保存候选源文件与补丁元数据。运行 orchestrator 后可执行：
  ```bash
  cd .artifacts/git_lineage
  git log --stat
  ```
  查看候选的提交历史；如需重新开始，可删除该目录并重新运行 orchestrator。
- **观测工件**：运行结束后在 `.artifacts/dashboard.html` 打开 MAP-Elites 热力图与 Pareto 摘要，在 `.artifacts/prompt_telemetry.json` 查看提示臂奖励与温度历史。
- **Streamlit 面板（可选）**：`streamlit run tools/streamlit_app.py` 即可本地查看档案、提示遥测、Few-shot 样例与候选源码预览。
- **Few-shot 案例库**：系统会在 `.artifacts/fewshot/<problem_id>.jsonl` 落地成功补丁与失败→修复样例，Prompt 在下一轮会自动检索以提升针对性，可按需备份或清理。

## 3. 排障指南

| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| **候选频繁卡在 L0** | 语法/类型检查失败、AST 黑名单命中 | 查阅 `.artifacts/candidates/<id>/` 中的源文件，确认 EVOLVE-BLOCK 范围内的语法；必要时使用 `agents/prompts/repair.v1.md` 臂重试。
| **评测缓存未命中** | 环境指纹或补丁载荷变化 | 调用 `CacheManager.report()` 查看命中率，确认 `environment_fingerprint`、补丁 metadata 是否一致，必要时配置 `FilesystemCacheBackend` 共享缓存。
| **L3 鲁棒性得分过低** | 未能通过 `generate_adversarial_samples`、`generate_noisy_samples` | 在 Prompt 模板中加入“对抗样例”“噪声鲁棒”检查项，或查看日志添加更严格的输入验证。
| **CI `evolution` 作业失败** | Orchestrator 抛异常或 artifact 写入失败 | 查看 GitHub Actions 日志，确认 `python -m orchestrator.run_loop` 是否成功执行；失败时下载上传的 `.artifacts` 分析候选，并检查 `dashboard.html`、`prompt_telemetry.json` 与 `run_state.json` 是否生成。
| **LLM 输出被拒绝** | 缺少 `version`/`diff_type="sr"` 或 `payload.replace` 非完整 EVOLVE block | 检查 orchestrator 日志中的 `LLM API fallback` 警告，修订提示模板 checklist 或补充上下文后重试。

## 4. 运维要点

- **提示演化**：`PromptBandit.ingest_feedback()` 会在候选失败时自动标注 `Investigate <tier>_fail` 到 checklist，手工运行时亦可调用：
  ```python
  bandit.ingest_feedback("mutate.robust_first", ["custom_error"])
  ```
- **提示遥测**：`PromptBandit.export_telemetry()` 会刷新 `.artifacts/prompt_telemetry.json`，记录各臂奖励、温度与 checklist。若某臂奖励长期低于 0.3，可调整提示指令或增加 few-shot 示例后观察变化。
- **档案回放**：`ArchiveManager.state` 中的 Pareto front 与 MAP-Elites 网格可序列化保存，用于离线分析；也可直接使用自动导出的 `.artifacts/map_elites.json` 与 `.artifacts/dashboard.html`。
- **缓存治理**：当缓存落盘时，结合 `CacheManager.report()` 观察 `lookups/hits/hit_rate`，并定期清理 `.cache/evals/*.json`。

## 5. 持续集成与部署

- GitHub Actions `evolution` job 以 2 轮并发矩阵演示候选评测，并上传 `.artifacts`；默认矩阵包含 `sample_problem`、`shortest_path`、`knapsack`，可通过调整 `matrix.problem` 或环境变量 `EVOLVE_PROBLEM` 控制首个问题岛。
- Docker 部署：使用项目根目录的 `Dockerfile` 构建镜像，运行容器后按上述命令启动 orchestrator 或 CLI 工具。

## 6. 参考链接

- 《docs/self-evolving-system.md》：总体架构与设计原则。
- 《docs/governance.md》：安全、合规、审计要求。
- 《docs/observability.md》：指标、日志与可视化方案。

> 💡 要启用真实 LLM 生成，可配置直连推理 API 的环境变量：
> ```bash
> export LLM_API_MODEL='qwen3-max'
> export DASHSCOPE_API_KEY='sk-...'
> export LLM_API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
> export LLM_API_TEMPERATURE=0.7             # 可选，控制多样性
> export LLM_API_RATE_LIMIT_RPM=60           # 可按配额调整
> export LLM_API_RATE_LIMIT_CONCURRENCY=4    # 控制并发
> export LLM_API_RATE_LIMIT_BURST=6          # 允许的瞬时突发
> python -m orchestrator.run_loop
> ```
> Orchestrator 会自动实例化 `LLMApiAgentAdapter`，通过 OpenAI Python SDK 与流式响应消费 JSON patch；若 API 响应异常，则回退到内置模板变异。
> Agent **必须** 返回包含 `"version": 1` 与 `diff_type="sr"` 的 JSON，缺失时响应会被拒绝并触发短期熔断回退。

> `ProblemEvaluator` 在独立子进程沙箱中执行候选 `solve()`，强制施加 `execution_timeout_s` 与 `memory_limit_mb` 限额；若进程超时或异常退出，会立即终止并记录失败信号。
