# Polaris → PAS 采用矩阵

## 1. 结论与范围

本文件评估如何从 [ZJU-REAL/Polaris](https://github.com/ZJU-REAL/Polaris)
选择性借鉴能力，增强 Paper Attribution System（PAS）。评估所依据的 Polaris
版本为提交
[`bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed`](https://github.com/ZJU-REAL/Polaris/tree/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed)，
审查日期为 2026-08-10。

采用结论：

- 借鉴 Polaris 的持久化任务运行时、文献治理、确定性验收、运行可观测性和只读工具边界。
- 不把 Polaris 当成 PAS 归因算法、Attribution Evidence Tree（AET）或 GNN 分类器的替代品。
- 第一阶段只增强固定流水线的可靠性；不引入自主规划、多 Agent 辩论、SSH 实验或论文自动写作。
- 本文件是采用计划，不代表 Polaris 代码已经进入 PAS。本次审查没有复制第三方代码。

## 2. 不可改变的 PAS 语义边界

以下边界优先于任何 Polaris 实现：

1. **PAS 的产品是可审计归因证据路径。** 标签、置信度、支持证据、反对证据、时间有效性、来源和人工审核路由必须保持一等数据。
2. **Attribution Skill 保持只读。** 归因判断和证据收集不能顺带修改研究网络；任何网络变更必须是独立、确认后的操作。
3. **请求与结果可重放。** 现有 invocation ID、请求哈希、输入快照、policy version、typed outcome 和 fail-closed 行为保持权威。
4. **中立事实层与政策判断层分离。** 每篇论文可以有一份中立摘要，但 AC/SDL 归因必须依据明确版本的政策重新计算，不能从通用摘要反推。
5. **LLM 不拥有事实。** 论文、证据、数字、citation、edge 和 provenance 来自数据库、原文 chunk、manifest 或确定性聚合；LLM 只能组织已有材料。
6. **图能力不越权。** 当前 graph export 和 leakage-safe graph-feature baseline 不等于完整 GNN；Polaris 的 concept graph 也不能改变这一状态。
7. **先 shadow、再恢复、最后接管。** 新运行时先旁路记录现有流水线，验证 replay 后才允许承担 resume/cancel；不能一次性替换生产执行入口。
8. **合并默认可审计且可逆。** 不照搬直接删除重复论文的策略；不确定重复项必须进入人工审核。

## 3. 当前 PAS 基线

| 能力 | 当前权威实现 | 已有保证 | 真实缺口 |
|---|---|---|---|
| 日常流水线 | [`scheduled_pipeline.py`](../app/services/scheduled_pipeline.py)、[`pipeline_run.py`](../app/models/pipeline_run.py) | 固定步骤、幂等执行、结果汇总和错误记录 | `steps` 仍是运行后 JSON 汇总；没有权威 step row、attempt archive、checkpoint、lease、resume、cancel 或 gate |
| Attribution Skill | [`attribution_skill_service.py`](../app/services/attribution_skill_service.py)、[`attribution_skill_contract.py`](../app/attribution_skill_contract.py) | typed intent、请求哈希、输入快照、policy version、预算、replay、fail-closed | 不应被通用 Agent tool loop 重写；未来只需要统一的只读暴露层和运行可观测性 |
| AET 与证据 Wiki | [`attribution_evidence_tree.py`](../app/services/attribution_evidence_tree.py)、[`wiki_compiler.py`](../app/services/wiki_compiler.py) | supporting/contradicting evidence、chunk/page/provider、时间有效性、staleness、确定性编译 | 可以增加非权威论文摘要，但不能覆盖证据 Wiki 或被分类器当作事实来源 |
| Zotero 权威语料 | [`zotero_ingestion_service.py`](../app/services/zotero_ingestion_service.py)、[`zotero_manifest_service.py`](../app/services/zotero_manifest_service.py) | Tier、collection key、corpus source、checksum/manifest、幂等 replay batch | collection membership 主要嵌在 paper/raw metadata 和 manifest；缺少独立、可查询、带生命周期的 membership 表 |
| 论文身份与去重 | [`paper.py`](../app/models/paper.py)、[`dedup_service.py`](../app/services/dedup_service.py) | DOI 唯一约束；作者去重有人工决策 | 缺少完整的论文 merge dry-run、关联迁移报告、合并 lineage 和非破坏性 tombstone |
| Graph/ML | [`graph_ml_dataset_service.py`](../app/services/graph_ml_dataset_service.py)、[`graph_feature_baseline.py`](../app/services/graph_feature_baseline.py) | graph contract/export 和离线 leakage-safe baseline | 没有端到端 GNN training、weights、inference 或生产 classifier wiring；本采用计划不改变它 |
| 报告可核验性 | [`reporting_service.py`](../app/services/reporting_service.py)、[`report_evidence_policy.py`](../app/report_evidence_policy.py) | 数字来自结构化聚合，带 filter fingerprint、paper-set hash 和可重放 deep link | 可扩展为逐 claim 的 citation/support 检查，但不能把 LLM reviewer 当作最终证据 |

## 4. 模块级采用矩阵

采用方式：

- **模式 A：设计借鉴**——重写为 PAS 原生实现，不复制代码。
- **模式 B：选择性移植**——仅在许可证登记后复制小型、边界清晰的实现并改造成 PAS contract。
- **不采用**——与 PAS 目标、权限或验证边界冲突。

| ID | Polaris 来源 | PAS 落点 | 采用方式 | 优先级 | 必须保留或改造的语义 | 验收证据 |
|---|---|---|---|---|---|---|
| P0-1 | [`models/voyage.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/models/voyage.py)、[`docs/task-system.md`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/docs/task-system.md) | 扩展 `PipelineRun`，增加权威 `PipelineStep`；新增最小 `pipeline_runtime.py` | A | P0 | 固定 plan；step rows 是权威源，JSON 只作派生快照；保留 seq、status、attempts、observation、verdict、provenance、started/finished timestamps | SQLite 与 PostgreSQL migration round trip；step snapshot 可从 rows 重建；旧 `PipelineRun` API 兼容 |
| P0-2 | [`checks.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/agents/voyage/checks.py) | 新增 `pipeline_checks.py` | A，必要时 B | P0 | 只采用确定性 checks：no error、artifact exists、schema valid、minimum count、hash/manifest match、source snapshot fresh；不以 LLM rubric 决定流水线成功 | 每种 check 有正反测试；未知 check fail closed；检查不修改业务状态 |
| P0-3 | [`engine.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/agents/voyage/engine.py)、[`worker/tasks.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/worker/tasks.py) | `pipeline_runtime.py`、执行入口和启动 reconciliation | A | P0 | 采用 DB checkpoint、attempt archive、cancel request、过期 lease reconciliation；执行语义为 at-least-once，因此每个可恢复 step 必须有幂等键；先不选定 ARQ/Redis | 在每个步骤前后模拟进程崩溃；恢复后无重复论文、evidence、manifest 或 invocation；cancel 后状态一致 |
| P0-4 | [`plan_edit.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/agents/voyage/plan_edit.py) | 仅借鉴确定性 branch table，放入 PAS 固定 pipeline 定义 | A | P0 | 不启用 LLM 自主规划；只有版本化代码能添加/跳过步骤；任何计划变更记录原因、旧/新步骤和 policy version | 同一 signal 重放不重复插入步骤；未知 signal 拒绝；历史计划可重建 |
| P0-5 | [`paper.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/models/paper.py)、[`library_direction.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/models/library_direction.py) | 新增 `PaperSourceMembership` 模型和 ingestion/backfill service | A | P0 | 一个 canonical paper 对应多个来源 membership；记录 provider、collection、tier、source record ID、first/last seen、manifest/hash、active/removed 状态；不得把 membership 当作归因标签 | 同一 DOI/标题跨 Tier 只生成一篇 paper、多条 membership；collection 移除不删除 paper/evidence；历史可查询 |
| P0-6 | [`paper_merge.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/services/paper_merge.py) | 新增论文 merge preview/apply service 和 merge audit model | A，局部 B | P0 | 默认 dry-run；显式 keep/drop；关联迁移覆盖 author links、classification、review、evidence、sections/chunks、propositions、references、wiki、Skill invocation 和 memberships；drop 变成 tombstone/alias，不立即硬删 | DOI/规范化标题重复测试；冲突字段报告；关联数前后守恒；重复 apply 幂等；未确认候选不改变数据 |
| P1-1 | [`voyage_logs.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/services/voyage_logs.py)、Voyage SSE | 后端 task API 和前端运行详情 | A | P1 | 持久化低频状态、步骤结果和错误；token delta 等高频事件可以只流式传输；日志不得包含 API key、全文敏感数据或未裁剪 prompt | 断线重连可从 DB 重建状态；权限测试；日志 redaction 测试；冷启动后仍可查看历史 |
| P1-2 | [`paper_review.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/services/paper_review.py) | 报告 claim/citation validator，复用现有 report deep links 和 evidence bundle | A | P1 | existence、support 和 numeric provenance 分开；外部服务不可达不能直接判 fabricated；support 判定保留证据 span 和不确定性；不把描述性证据升级成因果证明 | 每个数字回放到相同 metric/paper set；unsupported/partial/review-required 分开；外部失败 fail closed |
| P1-3 | [`tools/registry.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/tools/registry.py)、[`tools/scope.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/tools/scope.py) | Attribution Skill catalog 的统一只读 registry；未来可映射 MCP | A | P1 | 工具按用户意图组织，不按 OpenAlex/Zotero/GROBID 等 provider 组织；默认 read-only；scope 与 API auth 同源；写操作不进入同一 catalog | API 与 MCP 使用同一 schema；越权 paper 返回不可见而非泄漏存在性；写入调用被硬拒绝；replay 仍受同一 API key 保护 |
| P1-4 | [`core/llm/router.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/core/llm/router.py) | PAS 统一模型边界和调用计量 | A | P1 | provider SDK 不进入业务服务；route/version 写入审计；fake provider 在生产 fail closed；模型输出永远不是事实权威 | provider contract tests；生产配置拒绝 fake；每次调用可追到 user/run/policy/model/cost |
| P2-1 | [`wiki_compile.py`](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/src/backend/app/services/wiki_compile.py) | 可选 `paper_summary` 或 evidence Wiki 的明确非权威展示区 | A | P2 | 只生成中立论文摘要；必须标注 model、prompt、source snapshot 和 freshness；摘要文本不得进入 AET、classifier、gold label 或 report metric | 修改政策不需重编中立摘要；修改原文会标 stale；摘要内容不会出现在分类输入快照 |
| P2-2 | Polaris concept backlinks | 可选概念候选层 | A | P2 | 概念必须保留 paper/chunk 来源、候选/确认状态和人工纠错；“两篇论文出现”只能作为候选门槛，不是科学真值 | 每个 concept edge 可追到 chunk；单篇专有名称不自动晋升；删除/合并论文后引用计数一致 |
| X-1 | Navigator/Helm/Sextant 的开放式自主循环 | 无 | 不采用 | — | PAS 固定 ingestion/classification/review 流程不需要 LLM 规划；可能需要开放式研究时另立项目和权限模型 | 不适用 |
| X-2 | Idea Forge、Elo reviewer debate、SSH Experiment Lab、LaTeX Paper Writer | 无 | 不采用 | — | 超出 PAS “可信数据、标签、证据和解释性报告”当前范围 | 不适用 |
| X-3 | Polaris 通用 relevance score、Wiki 文本或 concept graph | PAS classifier/AET/GNN | 不采用 | — | 不能替换 AC/SDL policy、human gold、AET evidence path 或端到端 GNN 验证 | 不适用 |

## 5. 推荐实施顺序

### 阶段 0：来源和 contract 固化

目标：在没有行为变化的情况下，为后续选择性移植建立审计边界。

- 把本文件中的 Polaris source commit 固定为审查基线。
- 若复制任何代码，先增加项目级许可证决策和 `THIRD_PARTY_NOTICES`，记录原文件、commit、采用方式和修改说明。
- 为 `PipelineRun` 定义明确的状态集合、step contract 和兼容策略；不要先引入队列框架。
- 明确哪些现有步骤具备幂等键；没有幂等保证的步骤不得自动 resume。

完成标准：contract review 通过；没有生产行为变化；没有第三方代码在登记前进入仓库。

### 阶段 1：shadow task ledger

目标：让现有 `scheduled_pipeline` 在原执行逻辑不变的情况下，同时写入权威 step/attempt 记录。

1. 扩展数据库模型和 API 读模型。
2. 现有同步执行仍拥有控制权，新 ledger 只旁路记录。
3. JSON `PipelineRun.steps` 暂时保留，由 step rows 派生，兼容现有前端与 API。
4. 为 Zotero sync、discovery、full-text、classification、review routing 写确定性 acceptance checks。

完成标准：新旧汇总逐字段一致；同一稳定语料重复执行没有新增业务数据；SQLite/PostgreSQL migration upgrade/downgrade 通过。

### 阶段 2：受限恢复、取消和 reconciliation

目标：只让已证明幂等的步骤获得恢复能力。

1. 先对 manifest inventory、只读检查和 evidence Wiki export 开启 resume。
2. 对 ingestion/classification 等写步骤增加 idempotency key 后再逐项开放。
3. worker/进程重启只接管 lease 已过期且状态允许恢复的 run。
4. cancel 是协作式终止；已发生的业务写入不伪装成回滚。

完成标准：对每个开放步骤进行 before-write、after-write、before-verdict 三个 crash-point 测试；恢复后业务行和审计行都不重复。

### 阶段 3：来源 membership 与非破坏性论文合并

目标：把当前嵌在 metadata/manifest 中的来源关系提升为可查询的一等数据，并安全处理跨源重复论文。

1. 建立 `PaperSourceMembership` 并从 Zotero/现有 provenance 回填。
2. 先只提供 duplicate candidate 和 merge preview。
3. apply 必须经显式确认，并保留 merge lineage/tombstone。
4. classifier 和报告继续读取 canonical paper；来源 membership 仅提供 provenance 和 scope。

完成标准：跨 Tier/collection 数量可审计；论文合并前后所有 evidence、review、Skill invocation 和 report paper set 可解释且守恒。

### 阶段 4：引用核验和只读工具统一

目标：复用 Polaris 的工程模式，补强 PAS 的证据消费层，而不改变归因权威。

- 将逐 claim 的 existence/support/numeric provenance 校验接到 evidence bundle 和报告 deep link。
- 将现有 intent-based Attribution Skills 注册到单一只读 registry；确认 API 与未来 MCP 共用 auth、scope 和 schema。
- 只有当运行负载和部署证据表明确有需要时，再决定是否采用 Redis/ARQ；该决定不由本矩阵预设。

完成标准：每个对外 claim 可回到 paper/chunk/metric；缺证据、服务不可达和未知状态都进入明确的 review/failure 状态。

## 6. 验证总表

每个实施阶段至少需要以下证据：

- 目标功能测试和失败路径测试。
- SQLite 与 PostgreSQL/pgvector Alembic upgrade、downgrade、re-upgrade。
- 固定语料上的幂等 replay 和 crash recovery 测试。
- API key、scope、read-only 和敏感日志 redaction 测试。
- 分类/AET 回归：生产 label 路径、policy version、supporting/contradicting evidence 和 review routing 不变。
- GNN 边界回归：不得出现“已完成 GNN classifier”的错误产品或文档表述。
- `ruff check`、相关 frontend build/type check、`git diff --check` 和适当范围的全套测试。
- 部署后证据与代码证据分开记录；worker 冷启动恢复必须在真实部署环境单独验证。

## 7. 许可证与来源记录

Polaris 使用
[Apache License 2.0](https://github.com/ZJU-REAL/Polaris/blob/bc13d8ddd1b8bbb7fdd8c01d4d9d492efd8608ed/LICENSE)。
直接复制或修改代码前，应至少：

- 在 PAS 中附带适用的 Apache-2.0 许可证文本；
- 保留适用的 copyright、patent、trademark 和 attribution notices；
- 在修改过的文件中明确标记修改；
- 若上游分发包含 `NOTICE`，同步保留适用 NOTICE 内容；
- 在 `THIRD_PARTY_NOTICES` 中记录上游仓库、固定 commit、原文件路径、PAS 落点和修改摘要；
- 单独审查图片、演示视频、论文模板和其他资产的许可证，不因为代码采用 Apache-2.0 就假设所有资产都可复用。

许可证登记解决的是来源与分发义务，不替代对科学语义、数据使用权和部署安全的审查。
