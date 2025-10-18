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
   - 元提示演化仅调整权重、顺序与 checklist，禁止注入动态执行代码。

## 3. 合规要求

- **许可证检查**：引入第三方依赖时需在 `pyproject.toml` 声明，并确保许可证兼容；
- **数据合规**：`problems/` 中的数据生成函数不得使用受限数据集；
- **审计日志**：
  - GitHub Actions 的 `evolution` job 自动上传 `.artifacts/`，形成可追踪的候选与日志快照；
  - `CacheManager.report()` 输出命中率，辅助监控缓存滥用或异常失效。

## 4. 审计与回放

1. **档案追踪**：`ArchiveManager.state` 中保存 Pareto front 与 MAP-Elites cell，可定期导出 CSV/JSON。
2. **补丁回放**：每个候选目录包含完整源码，可通过 Git 分支或 `patch_payload` 复现；`CrossoverPlan.description` 有助于理解交叉组合方式。
3. **事件记录**：建议在后续引入 OpenTelemetry，将 `EvolutionOrchestrator`、`PromptBandit` 的关键事件（提示臂选取、奖励、失败标签）写入集中式日志。

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

