# Paper Attribution System 技术总览

这份文档按当前代码实现写，目的是把系统里已经做过的增强串成一条完整链路。旧文档仍然有价值，尤其是 `docs/rag_design.md`、`docs/graph_rag_design.md`、`docs/discovery_design.md` 和 `docs/research_intelligence_design.md`，但它们更像分阶段设计记录。这里讲的是现在这个项目整体怎么工作。

## 1. 系统解决什么问题

这个项目不是一个普通论文管理器，也不是一个泛用聊天机器人。它的核心任务是判断一篇论文和 Acceleration Consortium 及 self-driving lab 方向的关系，并把判断依据落到可追踪的证据上。

系统要回答几类问题：

- 这篇论文是不是 AC 相关，应该标成 `CORE_RELEVANT`、`RELATED_RELEVANT`、`ADJACENT`、`UNCERTAIN` 还是 `EXCLUDE`。
- 判断依据是什么，是作者、机构、主题、全文证据、funding acknowledgement、引用 AC core paper，还是二度合作网络。
- 如果已有论文库不完整，哪些论文应该被主动发现并放进 review queue。
- 如果用户问一个 RAG 问题，系统能否从 chunk、proposition、graph、SQL 里给出带证据的回答。
- 如果要做 dashboard 或年度报告，数字是否来自结构化查询，而不是 LLM 临场编出来。

系统有一个很明确的边界：LLM 只负责把已有证据写成自然语言，不能发明 paper、edge、数字或 citation。真正的事实来源是数据库、全文 chunk、结构化 proposition、graph signals 和 SQL aggregation。

## 2. 技术栈

后端是 FastAPI + SQLAlchemy。默认数据库是 SQLite，配置里已经准备好 PostgreSQL 和 pgvector 依赖。服务层主要用 Python 实现，核心依赖包括 `networkx`、`numpy`、`scipy`、`rapidfuzz`、`pandas`、`markitdown`、`pymupdf`、`anthropic`、`openai` 和可选 `langgraph`。

前端是 React + Vite + TypeScript，图表主要用 ECharts，也有 `react-globe.gl` 用于地理视图。路由集中在 `frontend/src/main.tsx`，API 调用集中在 `frontend/src/lib/api.ts`。

主要入口：

- 后端：`backend/app/main.py`
- 配置：`backend/app/config.py`
- ORM：`backend/app/models/`
- API：`backend/app/api/`
- 服务层：`backend/app/services/`
- 前端页面：`frontend/src/pages/`
- 数据文件：`data/`

## 3. 数据从哪里来

系统目前有三类数据来源。

第一类是内部 CSV/YAML：

- `data/ac_members.csv`：AC 成员、别名、机构、ORCID。
- `data/institution_aliases.csv`：机构规范名、别名、国家、城市、partner 标记。
- `data/topic_taxonomy.yaml`：主题 taxonomy，区分 core topics 和 adjacent topics。
- `data/ac_core_papers.csv`：AC core paper 种子，用于 citation graph。
- `data/domain_vocabulary.yaml` 和 `data/retrieval_operationalization_terms.yaml`：检索、主题和证据抽取时用到的领域词表。

第二类是论文元数据。早期是 sample CSV，现在也支持通过 OpenAlex、Semantic Scholar、Crossref discovery 把外部候选论文纳入系统。

第三类是全文文件。现在不只支持 PDF，还支持 docx、pptx、xlsx、html、md、txt、xml、json、epub、csv 等 MarkItDown 能处理的格式。上传入口是：

```text
POST /papers/{paper_id}/fulltext
```

支持的后缀来自 `backend/app/services/pdf_parser.py` 里的 `SUPPORTED_FULLTEXT_SUFFIXES`。

## 4. 数据库核心表

系统的表可以分成几组理解。

论文与实体：

- `papers`：论文主表，保存 title、abstract、doi、year、venue、keywords、provenance、full_text_available 等。
- `authors`：作者规范实体，含 aliases、ORCID、机构、是否 AC member。
- `institutions`：机构规范实体。
- `paper_authors`：论文和作者的多对多关系，含 author_order、affiliation_text、match_confidence。
- `topics`：主题 taxonomy 入库后的实体。

分类与人工审核：

- `paper_classifications`：每篇论文当前分类结果，含 label、confidence、author_score、institution_score、topic_score、network_score、citation_score、fulltext_evidence_score、matched_*、reasons、graph_signals 等。
- `human_reviews`：人工修正标签、 reviewer、notes、纠错原因。
- `rag_feedback`：用户对 RAG 答案的评分和失败类型，用于 memory 模块和评估。

全文与 RAG：

- `paper_sections`：全文解析后的 section。
- `paper_chunks`：语义 chunk，存展示文本、indexed_text、embedding、section metadata、parent-child metadata。
- `paper_evidence`：从全文里抽取出的 funding、methodology、acknowledgement、figure caption 等证据。
- `paper_propositions`：结构化命题，例如 `uses_method`、`funded_by`、`belongs_to_topic`。
- `paper_references`：参考文献解析结果，尽量对齐到 corpus paper 或 AC core paper。
- `ac_core_papers`：AC core seed papers。

发现与运维：

- `discovery_candidates`：外部发现到但尚未完全接纳的论文候选。
- `external_cache`：OpenAlex、Semantic Scholar、Crossref 请求缓存。
- `pipeline_runs`：自动 pipeline 的运行日志。
- `author_dedup_decisions`：作者去重决策。
- `wiki_pages`：单篇论文 wiki 编译结果。

## 5. 入库和分类主链路

一个典型的 pipeline 是：

```text
CSV / external candidate / manual paper
  -> normalize entities
  -> match authors, institutions, topics
  -> parse full text if available
  -> chunk, evidence, references, propositions
  -> compute graph signals
  -> classify
  -> review queue or analytics
```

分类逻辑在 `backend/app/services/relevance_classifier.py`。它不是单一模型，而是多信号规则系统：

- 作者信号：`AuthorMatcher` 做名字、别名、上下文和 AC publication confirmed boost。
- 机构信号：`InstitutionMatcher` 处理机构别名和 partner institution。
- 主题信号：`TopicClassifier` 做 boundary-aware 和 density-aware 主题匹配。
- 全文信号：`PaperEvidence` 聚合 funding acknowledgement、SDL methodology、figure caption 等。
- 图信号：`compute_graph_signals()` 计算 direct AC、second-degree collaborator、citation to AC core、bridge score 等。
- 可选增强：borderline rerank、LLM judge、learned classifier post-hoc override。

标签大致含义：

| Label | 含义 |
|---|---|
| `CORE_RELEVANT` | 强 AC 关系，通常有 AC author、AC funding 或强主题/方法证据 |
| `RELATED_RELEVANT` | 明确相关，但不一定是核心产出 |
| `SDL_FIELD_RELEVANT` | SDL 领域相关，但 AC attribution 不强 |
| `ADJACENT` | 邻近领域或弱相关 |
| `UNCERTAIN` | 需要人工判断 |
| `EXCLUDE` | 没有足够相关信号 |

重要的是，分类结果会保留 `reasons` 和证据引用。系统不是只给一个 label，而是要让 reviewer 能看到为什么。

## 6. 全文解析：MarkItDown 是第一步

全文入库入口在 `backend/app/services/fulltext_service.py`，解析入口在 `backend/app/services/pdf_parser.py`。

当前策略是：

1. 对 PDF 和常见文档格式，优先用 Microsoft MarkItDown 转成 Markdown 风格文本。
2. PDF 如果 MarkItDown 不可用或失败，可以回退到 GROBID 或 PyMuPDF。
3. 解析后的文本会按标题、section heading、figure caption 等规则切成 `ParsedSection`。
4. 如果 GROBID 给了结构化 author/reference，系统优先用；否则用内部 reference parser 兜底。

这样做的原因很直接：RAG 后续所有步骤都依赖干净文本。先把 PDF、docx、pptx 等文件统一成 Markdown 或近似 Markdown，后面的 section split、chunking、proposition extraction、embedding 才能稳定。

解析结果不是直接给 LLM，而是落库成：

- `PaperSection`
- `PaperChunk`
- `PaperEvidence`
- `PaperReference`

## 7. Chunking：semantic、adaptive、parent-child

chunking 在 `backend/app/services/chunking_service.py`。现在不是固定窗口硬切，而是 section-aware semantic chunking。

策略分几层：

短 section 不切：

- abstract
- acknowledgements
- figure_caption
- references

长 section 做 semantic adaptive 切分：

- methods
- introduction
- results
- discussion
- supplementary
- unknown

具体做法：

1. 先按段落和句子切成 segment。
2. 计算相邻 segment 的词集合相似度。
3. 如果 token 超过当前 section 的 adaptive 上限，或者语义相似度明显下降，就开新 parent window。
4. parent window 太长时，再用 sliding fallback 切成 child chunk。
5. 数据库只存 child chunk 作为检索单元，但每个 child 的 metadata 里保留 parent 信息。

每个 chunk 现在有两类文本：

- `chunk_text`：展示给用户的精准片段。
- `indexed_text`：用于 BM25 和 embedding 的文本，包含 contextual prefix 和 parent context。

这个设计解决了一个常见问题：展示时需要短而准，检索时需要更多上下文。比如 methods 里一句话只写了 `the platform was optimized in closed loop`，单看这句话很难召回；加上论文标题、年份、section 和 parent context 后，检索会稳定很多。

## 8. Evidence 与 Proposition

全文入库后，`evidence_extractor.py` 会从 section 和 chunk 中抽取证据。典型证据包括：

- AC funding acknowledgement
- partner institution acknowledgement
- self-driving lab methodology
- robotic synthesis
- Bayesian optimization
- closed-loop experimentation
- figure caption 里的 SDL 证据
- disqualifying 或 negated evidence

这些证据用于分类，也用于 reviewer 解释。

`proposition_extractor.py` 会把部分证据和结构化事实转成 `paper_propositions`。它把长文本里的事实拆成更容易检索的命题，比如：

```text
(paper_id=P001, predicate=uses_method, object_value=Bayesian optimization)
(paper_id=P003, predicate=funded_by, object_value=Acceleration Consortium)
(paper_id=P010, predicate=belongs_to_topic, object_value=self-driving labs)
```

这对 RAG 很重要。问“哪些论文用了 Bayesian optimization”时，直接搜 proposition 往往比只搜 chunk 更准。

## 9. Reference 和 Graph signals

reference 解析在 `reference_parser.py` 和 `fulltext_service.py` 里完成。系统会从 References section 中抽 DOI、title、authors、year，然后尝试解析到：

- corpus 内的 `Paper`
- curated `AcCorePaper`

解析结果写入 `paper_references`。

图谱信号由 `graph_service.py` 计算，主要包括：

- direct AC author
- second-degree collaborator path
- citation to AC core paper
- cites corpus paper
- bridge score
- cross SDL diversity

这些信号同时服务三件事：

1. 分类时提高或降低相关性判断。
2. Graph-RAG 解释某篇论文为什么和 AC 相关。
3. RAG 检索时作为 graph context 或 graph score 参与排序和回答。

Graph-RAG 的原则是，图上的 edge 必须来自数据库或 NetworkX 计算，LLM 只能读这些 edge，不能生成新 edge。

## 10. 检索：HybridIndex

基础检索在 `backend/app/services/retrieval_service.py`。

检索流程：

```text
query
  -> metadata pre-filter
  -> BM25 score
  -> embedding cosine score
  -> Reciprocal Rank Fusion
  -> optional graph boost
  -> RetrievedChunk
```

metadata pre-filter 支持：

- `paper_ids`
- `section_types`
- `year_range`

BM25 用 domain tokenizer，适合精确术语、机构名、funding 名称和 grant 名称。embedding 默认是 TF-IDF embedder，可选 SBERT。当前 `HybridIndex.from_session()` 会在查询时对当前 corpus 重新 fit embedder，保证 query vector 和 chunk vector 维度一致。

排序默认用 RRF，也就是 Reciprocal Rank Fusion。相比直接把 BM25 和 cosine 分数加权，RRF 更稳定，因为它看排名，不强依赖两种分数的尺度。

返回结果会包含：

- `score`
- `bm25_score`
- `cosine_score`
- `graph_score`
- `graph_context`

## 11. Modular RAG

增强后的 answer endpoint 不是线性 RAG 管道，而是模块化图结构。实现文件是 `backend/app/services/modular_rag_service.py`，入口是：

```text
POST /retrieve/answer
```

模块顺序：

```text
Routing
  -> Memory
  -> Search
  -> Agentic Search
  -> Fusion
  -> Predict
  -> Demonstrate
```

每个模块的职责：

| Module | 作用 |
|---|---|
| Routing | 判断 query type，并选择 `iterative`、`recursive` 或 `adaptive` 模式 |
| Memory | 读取近期 RAG feedback，给 retry 或 failure-aware search 提供信号 |
| Search | 用 HybridIndex 检索初始候选 |
| Agentic Search | 沿 proposition、citation、graph signals 做受控多跳探索 |
| Fusion | 去重、rerank、附加 graph context、proposition hints、SQL hints |
| Predict | 评估当前证据质量，决定是否继续一轮 adaptive retry |
| Demonstrate | 构造 grounded context，调用 Kimi、Claude 或返回 retrieval-only passages |

`mode` 的含义：

- `iterative`：普通事实查询，一轮检索为主。
- `recursive`：比较、gap、跨论文综合问题，会生成多个子查询。
- `adaptive`：先根据 query type 选择工作模式，如果证据不足可再检索一轮。

系统已经有 LangGraph adapter，但后端默认用本地 runner。这样测试和部署不强依赖 LangGraph，同时保留将来切换到 LangGraph runtime/checkpointing 的路径。

## 12. Agentic Search

agentic search 是新加的探索模块，目标是处理需要关联发现和推理的科研问题。它不是开放式 agent，也不会让 LLM 自由调用工具。它只在本地已知结构上做受控探索。

触发条件：

- 请求没有关闭 `agentic_search`
- mode 是 `recursive` 或 `adaptive`
- query type 是 comparison、citation、gap、structured 等探索型问题

探索输入来自初始 Search 的候选论文。系统会取前几个 seed paper，然后沿三类结构走：

1. `PaperProposition`：从命题里生成 follow-up query，比如 method、funding、claim。
2. `PaperReference`：从引用关系里生成 citation query。
3. `PaperClassification.graph_signals`：从 second-degree path、citation signal 中生成 network/citation query。

生成的 query 会再进一次 `HybridIndex.search()`，扩展候选 chunk。每条探索关系会保存在 `agentic_links` 中，最终出现在 source 里，方便解释为什么某篇论文被探索到。

API 请求里可以关闭：

```json
{
  "query": "Compare robotic synthesis and Bayesian optimization papers",
  "top_k": 5,
  "mode": "adaptive",
  "agentic_search": false
}
```

关闭后 trace 里仍会出现 `agentic_search`，但会标记为 skipped。这样适合做 A/B 对比。

## 13. Fusion：把四类证据合在一起

Fusion 不是简单排序，它会把不同证据通道合成 answer context。

最终回答上下文由几类东西组成：

- source chunks：文本证据。
- graph context：second-degree path、citation to AC core 等。
- proposition hints：结构化命题。
- SQL hints：结构化查询结果。
- agentic links：探索模块发现的关系。

结构化查询来自 `nl_to_sql_service.py`。它完全不调用 LLM：确定性 grammar 生成受限 plan，再编译成参数绑定的白名单只读 SQLAlchemy 查询。支持 intent 包括：

- `count_papers`
- `list_papers`
- `top_authors`
- `top_institutions`
- `top_propositions`
- `review_queue`

`/retrieve/sql-chat` 专门回答结构化取数问题，并返回 SQL、绑定参数、rows、filter/paper-set/statement hashes；不支持的问题 fail closed。全局 Tier 1 chat 先调用该端点；如果问题不属于受限 SQL grammar，或结构化查询没有返回行，则改用 `/retrieve/answer` 的有界 iterative 模式检索已索引全文。更慢的 adaptive/agentic 分析保留在独立 evidence workspace。`paper_count = 0` 仍被视为有效的结构化答案，不会触发全文降级。原始 SQL 和写操作不会进入全文降级路径。

## 14. Answer generation

回答生成在 `backend/app/api/retrieval.py` 的 `_llm_answer()`。

支持三种模式：

- `PAS_LLM_PROVIDER=kimi`：走 Kimi，OpenAI-compatible API。
- `PAS_LLM_PROVIDER=anthropic`：走 Claude。
- `PAS_LLM_PROVIDER=auto`：有 Kimi key 就用 Kimi，否则有 Anthropic key 就用 Claude，否则 retrieval-only。

系统 prompt 的核心约束是：只能基于提供的 passages 回答，并用 `[N]` 引用。证据不足时要明确说不足。

没有 LLM key 时，接口不会失败，而是返回 `retrieval-only`，把检索到的 passages 直接给用户。这对本地开发和测试很有用。

## 15. RAG 评估体系

RAG 评估在 `backend/app/services/rag_evaluator.py`，现在分三层。

第一层是 retrieval quality，回答“数据库匹配出来的结果质量怎么样”。自动指标包括：

- `source_count`
- `unique_papers`
- `section_diversity`
- `proposition_coverage`
- `graph_context_count`
- `source_precision_proxy`
- `recall_proxy`
- `score`

这里要注意，真正的 recall@k 和 nDCG 需要人工标注 gold evidence chunks。没有 gold evidence 时，系统只能算 proxy，不能假装知道完整召回率。

第二层是 answer grounding，回答“生成答案有没有被 source 支撑”。自动指标包括：

- citation coverage，也就是答案里有没有引用 `[1]`、`[2]` 这类 source。
- supported_by_sources，粗略判断答案是否和 source 绑定。
- requires_judge，明确标记仍需要 LLM judge 或人工判断 faithfulness、completeness、unsupported claims。

第三层是 human feedback，回答“用户或 reviewer 怎么评价这次回答”。字段包括：

- rating
- failure_type
- note_present
- score
- requires_human

如果没有人工评分，这一层不会伪造分数，会返回 `requires_human=true`。

另外还有 module metrics，用来评价 Modular RAG 每个模块有没有产出合理状态：

- routing：query_type 是否一致、选了什么 mode。
- memory：是否加载 feedback、low rating 数。
- search：query 数、候选数。
- agentic_search：是否启用、生成 query 数、探索 link 数、扩展候选数。
- fusion：source 数、proposition 数、SQL hints、agentic links、dedupe ratio。
- predict：evidence_score、should_retry、continue_graph。
- demonstrate：model、context chars。

这套评估的定位很清楚：自动指标可以发现很多工程问题，但最终答案好不好，仍需要 gold set、LLM judge 或人工反馈来校准。

## 16. Discovery：主动找漏掉的论文

发现模块在 `backend/app/services/discovery_service.py` 和 `backend/app/api/discovery.py`。

它解决的是另一个问题：系统不能只等人上传论文。已有 AC members、AC core papers 和 CORE_RELEVANT papers 后，可以主动去外部数据源找可能漏掉的论文。

外部数据源：

- OpenAlex
- Semantic Scholar
- Crossref

策略包括：

- cite_of_core：找引用 AC core paper 的论文。
- ac_coauthor：找 AC author 或其网络相关论文。
- s2_recommend：用 Semantic Scholar 推荐相似论文。

候选论文会进入两条路：

- 高置信自动入库，`provenance=discovered_auto`。
- 低置信进入 `discovery_candidates`，等待 reviewer approve/reject。

API：

```text
POST /discovery/run
GET  /discovery/queue
POST /discovery/queue/{candidate_id}/approve
POST /discovery/queue/{candidate_id}/reject
```

前端页面是 `/discovery`。

## 17. Review queue 和 active learning

review queue 的 API 在 `backend/app/api/review_queue.py`。

典型入口：

```text
GET  /reviews/queue
GET  /reviews/queue/next
GET  /reviews/queue/size
POST /reviews/{paper_id}/confirm
POST /reviews/{paper_id}/skip
POST /reviews/{paper_id}
```

哪些论文会进 queue：

- borderline 分类结果。
- 自动发现但置信不够的论文。
- 有冲突证据的论文。
- LLM judge 或 learned classifier 认为需要人工确认的论文。

人工 review 不只是改 UI 状态。它会影响：

- `human_reviews`
- 完整且显式的 classifier label 会形成不可变 training feedback event
- future classifier tuning
- RAG feedback memory
- pipeline audit

每累计 20 篇不同论文的合格 feedback，系统从全部允许的训练数据重新训练
候选模型。候选必须通过 trigger batch 的 out-of-fold 对比，并且独立固定
validation 至少达到默认 20 条、覆盖两个标签后才允许 promotion；accuracy、macro-F1 和有支持度
标签的 recall 不得退化，而且至少一个受保护指标必须严格提升。失败或退化
的候选保留审计记录但不替换 production model。冻结 holdout 不参与这一循环。

状态入口：

```text
GET /model-evolution/status
GET /model-evolution/runs
```

完整契约见 `docs/model_evolution.md`。

## 18. Analytics 和 Research Intelligence

analytics API 在 `backend/app/api/analytics.py`，前端对应多个 dashboard 页面。

主要能力：

- `/analytics/overview`：总体统计。
- `/analytics/scope`：重放当前 filter 的指纹、论文集合 hash、覆盖率和来源分布。
- `/analytics/filter-options`：返回数据库中真实存在的国家、机构、主题、领域和来源选项。
- `/analytics/sankey`：机构、主题、label 的 Sankey。
- `/analytics/timeline`：按年份看 topic、label、institution 或 country。
- `/analytics/institution-network`：机构合作网络。
- `/analytics/multi-graph`：可配置多类型节点和边。
- `/analytics/geographic`：地理合作与中心增长。可选择任意已入库国家或机构，
  返回按年 distinct center papers、collaboration papers、active/cumulative
  partners；前端在 U of T 存在时默认以其为中心，也可切换 China 等中心。
- `/analytics/people-grid`：人员视图。
- `/analytics/evidence-gaps`：证据缺口。
- `/analytics/lint-report`：知识库 lint。
- `/analytics/duplicate-candidates`：重复作者/实体候选。
- `/analytics/impact`：研究影响力报告。
- `/analytics/drift`：topic drift。
- `/analytics/missed-papers`：按原因聚合 missed paper。
- `/analytics/report`：生成 research intelligence report。

reporting assistant 的原则是，数字来自 SQL aggregation。LLM 可选用于改写文字，但每个数字必须能追溯到 metric key 和 source link。validator 会检查 `[src:<key>]`，避免 LLM 编新数字。

## 19. Multi-Graph

Multi-Graph 在 `backend/app/services/multi_graph/`。

它允许按用户选择动态构图：

- node types：paper、author、institution、country、topic、method、funder、ac_core 等。
- edge types：authored、published_by、affiliated_with、coauthored、institution_collaboration、country_collaboration、cites、cites_ac_core、belongs_to_topic、uses_method、funded_by、topic_cooccurrence、similarity 等。

构图流程：

1. 先按 filter 选论文。
2. 运行 node providers。
3. 只生成两端节点都存在的 edge。
4. 用 `min_edge_weight` 过滤。
5. 按 `min_papers`、迭代 `min_degree` 和每类 top-N 做确定性裁剪。
6. 可选按 center_id 和 hop_limit 做 ego graph。
7. 可按 institution、country、topic 等分组。

前端预设把“只选作者/机构/国家”解释为各自的合作投影，把
“作者/机构/主题 + 论文”解释为对应的二部图，不再要求画面必须含 paper 节点。
所有 edge 权重都在 audit metric contract 中定义；合作次数不被描述成影响力。

前端页面：

- `/multi-graph`
- `/multi-graph/embed`
- `/network`
- `/network-v1`

## 20. Wiki 和单篇论文解释

系统也有单篇论文 wiki：

```text
GET  /wiki/paper/{paper_id}
POST /wiki/paper/{paper_id}/compile
```

对应 `backend/app/api/wiki.py` 和 `wiki_compiler.py`。它会把分类、证据、图谱、命题等信息整理成单篇论文页面，方便 reviewer 或报告作者快速理解一篇论文。

Graph explanation 入口：

```text
GET /papers/{paper_id}/graph-explanation
```

它返回 direct AC authors、second-degree paths、citation signals、cites corpus、cited by corpus 等结构化解释，不调用 LLM。

## 21. 前端页面地图

当前前端主要页面：

| Route | 用途 |
|---|---|
| `/` | Paper review 主表 |
| `/queue` | Review queue |
| `/insights` | 综合洞察 |
| `/pipeline` | Pipeline 运行状态 |
| `/evidence-gaps` | 证据缺口 |
| `/lint` | 知识库 lint |
| `/duplicates` | 重复候选 |
| `/discovery` | 外部发现队列 |
| `/report` | Research intelligence report |
| `/eval` | 评估指标 |
| `/sankey` | Sankey 分析 |
| `/timeline` | 时间线 |
| `/network` | 合作者网络 |
| `/network-v1` | 旧网络页 |
| `/impact` | 影响力 dashboard |
| `/drift` | topic drift |
| `/people` | 人员视图 |
| `/multi-graph` | 多图谱探索 |
| `/multi-graph/embed` | 可嵌入图谱视图 |
| `/geographic` | 地理分布 |
| `/growth` | 网络增长 |
| `/retrieval` | RAG 检索和回答 |

## 22. 重要 API 总表

论文与 review：

```text
GET  /papers
GET  /papers/stats
GET  /papers/export.csv
GET  /papers/{paper_id}
POST /reviews/{paper_id}
```

全文与 RAG：

```text
POST /papers/{paper_id}/fulltext
GET  /papers/{paper_id}/chunks
POST /retrieve
GET  /retrieval/propositions
GET  /retrieval/nl-sql
POST /retrieve/sql-chat
POST /retrieve/answer
POST /retrieve/feedback
```

Graph 与 proposition：

```text
GET /papers/{paper_id}/graph-explanation
GET /papers/{paper_id}/propositions
GET /propositions
GET /network/coauthors
```

评估与管理：

```text
GET  /eval/metrics
GET  /eval/rag-feedback
GET  /admin/parse-backend
POST /admin/seed-chunks
GET  /admin/accuracy
GET  /admin/vocabulary-suggestions
POST /admin/reclassify
POST /admin/apply-ac-members
GET  /admin/dedup-candidates
POST /admin/dedup-merge
POST /admin/dedup-separate
POST /admin/dedup-authors
```

Discovery、pipeline、analytics：

```text
POST /discovery/run
GET  /discovery/queue
POST /discovery/queue/{candidate_id}/approve
POST /discovery/queue/{candidate_id}/reject
GET  /reviews/queue
GET  /reviews/queue/next
POST /pipeline/run
GET  /pipeline/runs
GET  /pipeline/runs/latest
GET  /analytics/*
```

## 23. 运行方式

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.scripts.run_classification --reset
uvicorn app.main:app --reload --port 8000
```

带全文的路径：

```bash
python -m app.scripts.run_classification --reset --with-fulltext
python -m app.scripts.run_eval
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认前端访问 `http://localhost:8000`。可以用 `VITE_API_BASE` 覆盖。

重要环境变量：

| 变量 | 用途 |
|---|---|
| `PAS_DATABASE_URL` | 数据库连接 |
| `PAS_CONTEXTUAL_CHUNKING` | 是否开启 contextual chunking |
| `PAS_EMBEDDING_BACKEND` | embedding backend |
| `PAS_RERANKER_BACKEND` | reranker backend |
| `PAS_GROBID_URL` | GROBID 服务 |
| `PAS_KIMI_API_KEY` | Kimi answer generation |
| `PAS_ANTHROPIC_API_KEY` | Claude answer generation |
| `PAS_LLM_PROVIDER` | `kimi`、`anthropic` 或 `auto` |
| `PAS_PIPELINE_DISCOVERY` | daily pipeline 是否跑 discovery |
| `PAS_PIPELINE_FULLTEXT` | daily pipeline 是否处理全文 |
| `PAS_LEARNED_CLASSIFIER` | 是否启用 learned classifier |
| `PAS_LLM_JUDGE` | 是否启用 LLM judge |

## 24. 怎么理解当前增强的价值

可以把系统分成三条互相支撑的链路。

第一条是 attribution 链路。它从作者、机构、主题、全文证据、citation graph 和 reviewer feedback 出发，给论文一个可解释 label。

第二条是 RAG 链路。它先把全文通过 MarkItDown 标准化，再做 semantic adaptive parent-child chunking，然后用 BM25、embedding、RRF、graph context、proposition、SQL 和 agentic search 共同回答问题。

第三条是 research intelligence 链路。它把结构化分类和图谱分析转成 dashboard、drift、impact、missed-paper 和 report，面向年度报告、fundraising、战略复盘这类场景。

这三条链路的共同点是 traceability。每个 label、source、edge、metric、answer 都尽量能追到数据库里的具体行或 chunk，而不是只相信模型的自然语言解释。

## 25. 当前限制

几个限制需要明确：

- RAG 的真正 recall@k 和 nDCG 需要 gold evidence chunks，目前自动评估主要是 proxy。
- LLM answer grounding 只能自动检查 citation coverage 和基础 source support，faithfulness 仍需要 judge 或人工抽检。
- MarkItDown 能提升文档归一化质量，但复杂 PDF 的 section、table、reference 仍可能需要 GROBID 或专门 parser。
- 默认 TF-IDF embedding 适合本地和小中型 corpus，语义改写能力有限；更强语义召回需要 SBERT 或 pgvector 方案。
- agentic search 目前是受控多跳探索，优点是可解释，缺点是探索空间还依赖已有 proposition、reference 和 graph signals 的质量。
- external discovery 受 OpenAlex、Semantic Scholar、Crossref 数据覆盖和缓存新鲜度影响。

## 26. 后续最值得做的事

优先级比较高的改进：

- 建一个 gold evidence set，给 RAG 做真实 recall@k、nDCG、MRR。
- 给 agentic search 加探索预算和 profile，比如 attribution、literature_review、gap_analysis。
- 把 source-level `agentic_links` 在前端 `/retrieval` 页面可视化出来。
- 给 MarkItDown 解析结果加 table/image/caption 的质量检查。
- 把 learned classifier、LLM judge、human review 的结果合成一张 calibration dashboard。
- 如果 corpus 变大，把检索从当前内存索引迁到 PostgreSQL + pgvector 或专门向量库，同时保留 BM25/RRF。
