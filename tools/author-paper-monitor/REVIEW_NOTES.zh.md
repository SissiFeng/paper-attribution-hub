# author-paper-monitor 开发说明（供 review 用）

位置：`paper-attribution-system/tools/author-paper-monitor/`
这是一个独立的新目录，**没有修改** `paper-attribution-system` 里任何已有代码。

## 1. 目标

同事的需求：给一份作者名单，bot 持续监控这些人的新论文，判断哪些是新的、是否相关，去重后自动发到 Slack 频道，并且不直接抓取 Google Scholar。

交付范围：除接通 Slack（创建 webhook 并配置 `SLACK_WEBHOOK_URL`）以外的全部功能。

## 2. 架构

```
authors.csv ──resolve──▶ OpenAlex 作者 ID（ORCID 精确匹配；只有姓名的行列出候选人，由人工选）
每日 run：
  数据源（互相独立，一个挂了不影响其他）
    • OpenAlex   主源，按作者 ID 查最近 LOOKBACK_DAYS（默认 90 天）内发表的论文
    • arXiv      可选，按作者逐个开启（arxiv_query 列），比 OpenAlex 早几天拿到预印本
    • Scholar 提醒邮件  可选，IMAP 只读，作为辅助信号
  → 本次运行内合并重复（同一篇被多个作者/多个源命中）
  → 与 state.db 比对去重（DOI / arXiv ID / 规范化标题，任一命中即算重复）
  → 新论文：Crossref 校正标题和期刊名 → 可选 LLM：一句话摘要 + 判断是否相关
  → 进入 pending 队列 → Slack webhook（每次最多发 MAX_POSTS_PER_RUN 条）
```

只依赖 Python 标准库，需要 Python 3.10+。测试只依赖 pytest。

## 3. 文件清单

| 文件 | 内容 |
|---|---|
| `paper_monitor/http.py` | 所有网络请求都经过这里的 `request()`。用 urllib 实现，遇到 429/5xx 时按指数退避重试，会读 `Retry-After` 头。测试也是 mock 这一处 |
| `paper_monitor/models.py` | `Paper` 数据类；DOI 规范化、标题规范化（去重音、去 HTML 标签、去标点、转小写）；从 arXiv DOI 推出 arXiv ID 并去掉版本号；`merge()` 合并同一次运行里的重复记录 |
| `paper_monitor/authors.py` | 读写 `authors.csv`（列：name, orcid, openalex_ids, arxiv_query）；`resolve()`：有 ORCID 就自动填 OpenAlex ID，只有姓名就打印候选人，**不按姓名自动选** |
| `paper_monitor/openalex.py` | 按 ORCID 查作者、按姓名搜作者；`recent_works()`：作者 ID 每 50 个一组 OR 查询，过滤 `from_publication_date`，按 `publication_date:desc` 排序，用 cursor 翻完所有页，不走缓存。跳过 paratext/erratum/retraction/peer-review 类型、已撤稿和没有标题的条目；把倒排索引还原成摘要 |
| `paper_monitor/arxiv.py` | 解析 Atom feed；只保留 since 之后的条目，去掉版本号，合并标题里的多余空白 |
| `paper_monitor/crossref.py` | 只对即将发帖的新论文调用：用 Crossref 的标题和期刊名覆盖原值。arXiv 的 DOI（10.48550/）跳过，因为它们在 DataCite 不在 Crossref。调用失败就静默跳过，不会挡住发帖 |
| `paper_monitor/scholar_email.py` | 只有设置了 `IMAP_*` 才启用。只读打开邮箱，按 `SINCE` 日期和发件人搜索；从 `gse_alrt_title` 链接里取出真实 URL、DOI、arXiv ID，再取作者和期刊名；被跟踪作者的名字从邮件标题里取 |
| `paper_monitor/store.py` | SQLite 状态库。表 `papers`：doi / arxiv_id / title_key 三列各有索引，status 取 seeded / pending / posted / irrelevant 之一。`find()` 任一 key 命中就算重复；`add_ids()` 把后来才知道的 DOI 补进去；`mark_posted()` 每发一条就 commit 一次 |
| `paper_monitor/relevance.py` | 设置了 `ANTHROPIC_API_KEY` 才启用，直接调 Messages API，不用 SDK。有 `relevance_brief.txt` 时判断是否相关并写摘要，没有时只写摘要。**失败时放行**，即任何异常都当作相关处理 |
| `paper_monitor/slack.py` | 生成 Block Kit 消息（标题链接、作者最多显示 6 个、期刊·日期、摘要，context 行写跟踪作者和数据来源）；对 `& < >` 转义，标题里的 `|` 换成 `¦`；用 webhook 发送 |
| `paper_monitor/cli.py` | `resolve` 和 `run` 两个子命令，编排上面所有模块，策略见第 4 节 |
| `tests/test_monitor.py` + `tests/fixtures/` | 16 个测试，覆盖情况见第 5 节 |
| `deploy/github-actions-monitor.yml` | 每天 12:17 UTC 运行，带 `concurrency` 锁；运行完把 `state.db` commit 回仓库，加了 `if: always()`。（远程工具不允许写 `.github/`，所以放在这里，使用时要拷到 `.github/workflows/`） |
| `README.md` | 英文，写给同事：架构、配置步骤、接 Slack 的步骤、环境变量、已知限制 |
| `authors.example.csv`, `relevance_brief.example.txt`, `.gitignore`, `requirements-dev.txt` | 示例文件和配置 |

## 4. 关键行为与设计决策

1. **每天都重扫 90 天窗口，而不是只查昨天以来**：OpenAlex 收录论文常常晚于论文的发表日期，只查昨天会漏掉这些。哪些是新的由 state.db 判断。
2. **首次运行只建基线，不发帖**：数据库为空时，把窗口内所有论文记为 `seeded`。加 `--post-backlog` 则改为全部发出。
3. **首次运行时任何数据源失败都直接中止，不写库**：否则这个数据源的历史论文会在下一次运行被当成新论文发出去。
4. **去重规则**：DOI、arXiv ID、规范化标题，任一命中就算重复。因此预印本和之后的期刊版本（DOI 不同、标题相同）只发一次，并把新 DOI 补进旧记录。
5. **LLM 不参与"是否新"和"是否重复"的判断**，这两件事都由代码确定性地完成。LLM 只写摘要、做相关性判断，并且失败时放行。
6. **只有 Slack 返回成功才标记为 posted**。Slack 返回 HTTP 错误时停止本次发送，剩余论文保持 pending，进程退出码为 1。每发一条 commit 一次，所以中途崩溃不会导致重发。发帖间隔 1.1 秒（webhook 大约限 1 条/秒）。
7. **没配 webhook 或加了 `--dry-run` 时**：把要发的消息写到 `outbox/pending.json`，论文保持 pending，接上 Slack 后的第一次运行会把它们全部发出。
8. **退出码**：任何数据源失败或 Slack 发送失败都返回 1，方便 cron 或 Actions 报警。没有 OpenAlex ID 的作者只打印警告，不算失败。
9. **每次运行最多发 20 条**（`MAX_POSTS_PER_RUN`），防止刷屏，剩下的留到下次。

## 5. 已验证的部分

本地 `pytest` 16 个全部通过，`ruff check --select E,F,W,B` 无报错。测试内容：

- DOI 和标题规范化
- OpenAlex 解析：跳过 erratum 和无标题条目，正确映射被跟踪作者，还原摘要，从 arXiv DOI 推出 arXiv ID
- OpenAlex 查询参数：作者 ID 的 OR 过滤、日期过滤、按日期倒序、cursor 翻页且不截断
- arXiv 解析：时间窗口过滤、去版本号、合并空白
- Scholar 邮件解析：基于我自己构造的样例 HTML
- Slack 消息里的转义
- 同一次运行内跨数据源合并
- 端到端流程：首次运行建基线 → 未接 Slack 时进 pending 和 outbox → 接上 Slack 后只发一次 → 再次运行不重发
- 预印本之后出现期刊版本时不重发，并补上 DOI
- Slack 返回 404 时论文保持 pending、退出码为 1，恢复后补发成功
- 非首次运行时 arXiv 失败，其他数据源照常处理
- 首次运行时 OpenAlex 失败，不写入任何数据
- `--post-backlog`
- LLM：判为不相关的不发；摘要写进消息；LLM 宕机时放行
- `resolve`：有 ORCID 的行自动填好，只有姓名的行列出候选人且不填
- Crossref 覆盖标题和期刊名，arXiv DOI 跳过

## 6. 未验证的部分（重点请检查）

- **完全没有跑过真实 API**：开发环境访问不了 OpenAlex、Crossref、arXiv，用户电脑上的 shell 也一直调用失败。所有测试数据都是我按自己对各个 API 返回结构的了解手写的，需要用真实请求核对：
  - OpenAlex `/works` 能否同时用 `select` 选这些字段（尤其 `abstract_inverted_index`、`primary_location`），以及 `per-page=200` 加 cursor 的写法
  - `/authors/orcid:XXXX` 的返回格式，`last_known_institutions` 字段是否存在
  - OpenAlex 现在对 API key 和配额的要求（代码里 `api_key` 是可选参数）
- **Scholar 邮件解析器**：正则是按我所知的 Google 提醒邮件版式写的，**只用自己构造的样例测过**，需要拿真实邮件核对。
- **默认模型名 `claude-haiku-4-5`** 没有核实是否可用。
- **GitHub Actions workflow** 没有实际运行过。

## 7. 我自己发现、但还没处理的风险点

1. **按标题去重可能误伤**：不同论文如果有相同的泛化标题（如 "Editorial"、"Introduction"、"Reply to comment"），会被误判为重复而**漏发**。可以考虑在 DOI 都存在且不同时，不用标题匹配。
2. **`http.py` 处理 `Retry-After` 的方式**：代码直接 `float()` 这个头。如果服务端返回的是 HTTP 日期格式，会抛 `ValueError`，这个异常不在重试逻辑里，会直接冒出去。
3. **arXiv 请求频率**：arXiv 官方建议请求间隔约 3 秒，代码里多个 query 之间没有加 sleep。
4. **Scholar 邮件的作者名**来自邮件标题，可能和 `authors.csv` 里的写法不一致，只影响 Slack 里 "Tracked" 那一行的显示。
5. **`irrelevant` 是终态**：被 LLM 判为不相关的论文以后不会再评估；修改 brief 后也不会重新评估。
6. **GitHub 的 60 天规则**：公开仓库连续 60 天没有 commit，计划任务会被暂停；如果一直没有新论文，state.db 可能不变、也就没有 commit。README 里有提示，代码里没处理。
7. **标题前缀清理不全**：`[PDF]`/`[HTML]` 前缀只处理了这两种，其他前缀格式没覆盖。

## 8. 建议的检查方式

```bash
cd tools/author-paper-monitor
python -m pytest -q                                   # 应为 16 passed
cp authors.example.csv /tmp/a.csv
CONTACT_EMAIL=you@utoronto.ca python -m paper_monitor resolve /tmp/a.csv
CONTACT_EMAIL=you@utoronto.ca python -m paper_monitor run --authors /tmp/a.csv --db /tmp/s.db --dry-run
# 第一次运行应该显示 seeded、不发帖；
# 第二次加 --post-backlog 并换一个新 db，然后查看 outbox/pending.json 里的消息是否合理
```

建议 reviewer 重点看：`cli.py` 里 `cmd_run` 的状态流转、`store.find` 的去重逻辑、`openalex.recent_works` 的查询参数、`scholar_email.TITLE_RE`。
