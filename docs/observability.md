# 观测与可视化指南

本文描述如何监控自进化系统的吞吐、质量、多样性与失败原因，便于快速定位问题与评估优化效果。

## 1. 指标体系

| 指标 | 来源 | 说明 |
| --- | --- | --- |
| `candidate_throughput` | Orchestrator | 每小时完成的候选数量，可由执行日志统计或未来接入 OTEL Counter |
| `tier_pass_rate` | TierExecutor | 各级通过率，可通过 `EvaluationResult` 的 `passed` 字段累计 |
| `runtime_mean` / `runtime_pXX` | ProblemEvaluator | 在 `BehaviorFeatures.hotspots` 中输出，来自多次重复评测的均值/分位数 |
| `robustness` | ProblemEvaluator | 结合常规样本与 `stress_suites` 评分，反映对抗稳定性 |
| `cache_hit_rate` | CacheManager | `report()` 返回的 `hit_rate`，衡量缓存复用效果 |
| `novelty_score` | ArchiveManager | 每个候选的行为距离，可绘制代际趋势 |

## 2. 日志与追踪

- **Orchestrator**：`logging` 默认 INFO 级别，记录候选入队、缓存命中、级联失败等事件。建议在生产环境将日志重定向至集中式平台（如 Cloud Logging、ELK）。
- **Prompt 反馈**：`PromptBandit.ingest_feedback` 会把失败标签写入 checklist，可序列化成 JSON 供可视化使用。
- **评测记录**：`EvaluationResult.completed_at` 提供时区安全的时间戳，可用于构建甘特图或瀑布图。

## 3. 数据导出

1. **档案热力图**：遍历 `ArchiveManager.state.map_elites_cells`，统计 `(complexity_bin, robustness_bin)` 占用情况，可生成矩阵图像；系统默认同时渲染 `.artifacts/dashboard.html` 提供静态可视化。
2. **MAP-Elites 快照**：`EvolutionOrchestrator` 会将 `ArchiveManager.snapshot()` 写入 `.artifacts/map_elites.json`，可直接供面板或离线分析使用。
3. **Pareto 前沿**：`ArchiveManager.state.pareto_front` 提供候选 ID，结合 `ProgramCandidate.metrics` 绘制多目标散点。
4. **缓存统计**：`CacheManager.report()` 返回 `lookups/hits/hit_rate/entries`，可按时间序列写入 Prometheus Gauge。
5. **提示臂表现**：`PromptBandit.export_telemetry` 会生成 `.artifacts/prompt_telemetry.json`，其中包含成功率、温度与 checklist，适合作为 A/B 报表输入。

## 4. 可视化建议

- **Streamlit 仪表盘**：快速构建交互式面板，展示 Pareto 点云、MAP-Elites 热力图、缓存命中率曲线、提示臂奖励趋势；可直接读取 `.artifacts/map_elites.json`、`.artifacts/dashboard.html` 与 `.artifacts/prompt_telemetry.json`。
- **Grafana/Prometheus**：若部署在集群中，可将指标上报至 Prometheus，Grafana 中配置仪表盘：
  - 图表 1：每级评测通过率（Stacked Bar）；
  - 图表 2：性能分位数（Line + Filled Area）；
  - 图表 3：缓存命中率与缓存条目数；
  - 图表 4：提示臂奖励 Top-K。

## 5. 告警基线

- `cache_hit_rate < 0.2`：提示缓存失效或环境指纹漂移。
- `tier_pass_rate[L0] < 0.5`：说明生成候选质量较差，应检查提示或交叉逻辑。
- `runtime_p90` 连续上升：可能出现性能回退，需回滚至较优候选。
- `novelty_score` 下降：多样性不足，可调高 `novelty_alpha` 或提高交叉概率。

## 6. 后续规划

- 接入 OpenTelemetry Trace：串联 prompt 采样→LLM 调用→评测→缓存命中，形成端到端追踪。
- 将 `EvaluationResult.logs_path` 指向对象存储，供日志检索与失败分析。
- 构建自动化报表，结合 `docs/progress.md` 中的里程碑，周期性发布演化摘要。

