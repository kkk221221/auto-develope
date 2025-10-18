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

## 3. 排障指南

| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| **候选频繁卡在 L0** | 语法/类型检查失败、AST 黑名单命中 | 查阅 `.artifacts/candidates/<id>/` 中的源文件，确认 EVOLVE-BLOCK 范围内的语法；必要时使用 `agents/prompts/repair.v1.md` 臂重试。
| **评测缓存未命中** | 环境指纹或补丁载荷变化 | 调用 `CacheManager.report()` 查看命中率，确认 `environment_fingerprint`、补丁 metadata 是否一致，必要时配置 `FilesystemCacheBackend` 共享缓存。
| **L3 鲁棒性得分过低** | 未能通过 `generate_adversarial_samples`、`generate_noisy_samples` | 在 Prompt 模板中加入“对抗样例”“噪声鲁棒”检查项，或查看日志添加更严格的输入验证。
| **CI `evolution` 作业失败** | Orchestrator 抛异常或 artifact 写入失败 | 查看 GitHub Actions 日志，确认 `python -m orchestrator.run_loop` 是否成功执行；失败时下载上传的 `.artifacts` 分析候选，并检查 `dashboard.html` 与 `prompt_telemetry.json` 是否生成。

## 4. 运维要点

- **提示演化**：`PromptBandit.ingest_feedback()` 会在候选失败时自动标注 `Investigate <tier>_fail` 到 checklist，手工运行时亦可调用：
  ```python
  bandit.ingest_feedback("mutate.robust_first", ["custom_error"])
  ```
- **档案回放**：`ArchiveManager.state` 中的 Pareto front 与 MAP-Elites 网格可序列化保存，用于离线分析；也可直接使用自动导出的 `.artifacts/map_elites.json` 与 `.artifacts/dashboard.html`。
- **缓存治理**：当缓存落盘时，结合 `CacheManager.report()` 观察 `lookups/hits/hit_rate`，并定期清理 `.cache/evals/*.json`。

## 5. 持续集成与部署

- GitHub Actions `evolution` job 以 2 轮并发矩阵演示候选评测，并上传 `.artifacts`；默认矩阵包含 `sample_problem`、`shortest_path`、`knapsack`，可通过调整 `matrix.problem` 或环境变量 `EVOLVE_PROBLEM` 控制首个问题岛。
- Docker 部署：使用项目根目录的 `Dockerfile` 构建镜像，运行容器后按上述命令启动 orchestrator 或 CLI 工具。

## 6. 参考链接

- 《docs/self-evolving-system.md》：总体架构与设计原则。
- 《docs/governance.md》：安全、合规、审计要求。
- 《docs/observability.md》：指标、日志与可视化方案。

> 💡 若已安装并登录 `gemini-cli`，可通过环境变量 `GEMINI_CLI_COMMAND="gemini prompt --output json"` 启用真实 LLM 生成。Orchestrator 会自动实例化 `GeminiAgentAdapter`，将 `PromptBandit` 渲染的提示文本发送给 CLI，并在解析失败时回退到内置模板变异。

