# 治理与安全策略

本文档梳理自进化系统在安全、合规、审计方面的操作边界，确保大规模自动化演化保持可控。

## 1. 角色与责任

- **系统维护者**：负责配置 GitHub Actions、Docker 镜像、密钥与访问控制。
- **问题负责人**：定义 `problems/<name>/` 资产、评测指标与验收准则。
- **审核者**：定期复查档案（Pareto/MAP-Elites）、提示日志、缓存命中率，必要时回滚候选。

## 2. 安全边界

1. **沙箱执行**：
   - 评测阶段（L0–L3）默认断网，仅允许白名单 I/O；
   - `TierExecutor` 的 AST 规则禁止 `os`、`subprocess` 等危险模块；
   - 容器化运行时设置 CPU/内存限额，配合 `timeout_s` 控制单体预算。
2. **补丁约束**：
   - 所有候选必须位于 EVOLVE-BLOCK 范围内，补丁采用 SEARCH/REPLACE 或统一 diff；
   - `ProgramGenerator`、`perform_ast_crossover` 生成的 `patch_payload.metadata` 记录策略与说明，方便审计。
3. **提示防护**：
   - `PromptBandit` 在 `ingest_feedback` 中对失败标签进行标准化（`Investigate <tag>`），避免原始日志注入指令；
   - 默认系统提示（`DEFAULT_SYSTEM_PROMPT`）强制 LLM 输出 `{version:1, patches:[{diff_type:"sr", ...}]}` 结构，若模型偏离会被 `LLMApiAgentAdapter` 拒绝；
   - 演化请求携带 `problem_id`、目标文件路径与 EVOLVE-BLOCK 原始文本上下文，确保 `payload.search` 锚点可审计、可重放；
   - `ProgramGenerator` 追加提示校验（例如 EVOLVE 块中若存在 `def solve`，LLM 补丁必须保留该定义），不满足时自动回退模板并在提示遥测中记录 `PromptValidationError`；
   - 元提示演化仅调整权重、顺序与 checklist，禁止注入动态执行代码。

## 3. 合规要求

- **许可证检查**：引入第三方依赖时需在 `pyproject.toml` 声明，并确保许可证兼容；
- **数据合规**：`problems/` 中的数据生成函数不得使用受限数据集；
- **审计日志**：
  - GitHub Actions 的 `evolution` job 自动上传 `.artifacts/`，形成可追踪的候选与日志快照；
  - `CacheManager.report()` 输出命中率，辅助监控缓存滥用或异常失效。

## 4. 审计与回放

1. **档案追踪**：`ArchiveManager.state` 保存 Pareto front 与 MAP-Elites cell，`map_elites.json`、`dashboard.html` 在每轮运行后自动生成，可定期导出 CSV/JSON。
2. **补丁回放**：`.artifacts/candidates/<id>/` 存放候选源码，`.artifacts/git_lineage/` 记录 commit + patch metadata，可按 `patch_payload` 或 Git 索引复现；`CrossoverPlan.description` 有助于理解交叉组合方式。
3. **运行快照**：`FilesystemPersistence` 写入 `.artifacts/run_state.json`，涵盖候选队列、Bandit 权重、缓存摘要，支持断点续跑与离线审计。
4. **提示遥测**：`.artifacts/prompt_telemetry.json` 追踪每个臂的成功率、最新奖励、checklist 变更，属于提示治理的主数据源。
5. **事件记录**：若需集中可观测性，可在现有 JSON 工件基础上引入 OpenTelemetry，将 `EvolutionOrchestrator`、`PromptBandit` 的关键事件（提示臂选取、奖励、失败标签）推送至日志/指标系统。

## 5. 变更流程

- 所有变更（代码、配置、问题资产、提示模板）均需通过 Pull Request，并触发 `evolve` workflow；
- 对高风险模块（提示策略、评测配置）应添加 CODEOWNERS 审批；
- 重大配置（如禁用沙箱、扩展网络白名单）必须在变更说明中记录影响评估与回滚方案。

## 6. 风险应对

| 风险 | 预防措施 | 缓解策略 |
| --- | --- | --- |
| LLM 输出结构失控 | JSON schema 验证、`PromptBandit` checklist | 触发 repair 流程，更新提示权重并记录失败标签 |
| 演化早收敛 | NSGA-II + 新颖度 + MAP-Elites + 交叉 | 定期注入随机变异、调整 `novelty_alpha` |
| 安全突破沙箱 | AST 黑名单、容器资源限制 | 立即停机，回放候选，更新黑名单和提示模板 |

