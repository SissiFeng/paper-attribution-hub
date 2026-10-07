# Author paper monitor review 与交付记录

核验日期：2026-10-05。先阅读了 `REVIEW_NOTES.zh.md`；以下记录区分真实 API、隔离测试和实际 AWS 运行。

## 当前结果

- 本地：59 项测试通过；ruff E/F/W/B（沿用原有长行风格，忽略 E501）通过；Python 编译检查通过。
- 真实 OpenAlex：修正后的 2 位验证作者 resolve 成功；90 天窗口返回 19 篇。
- 本地真实 dry-run：独立基线库 19 seeded；独立 backlog 库 19 pending，生成 19 条消息，无 Slack/PAS 外部写入。
- 真实 AWS：CloudFormation 监控栈已部署。首次 ECS dry-run exit 0，19 seeded；后续 ECS dry-run exit 0，new=0，确认从 S3 恢复状态。
- 真实 PAS/RDS：事务内插入一篇真实 OpenAlex 论文、重复导入返回同一 ID，随后回滚；记录数 535 → 536 → 535。没有以测试为由保留生产论文。
- PAS 开放语料切换：按用户选择，将运行后端的 `PAS_SDL_STAGE1_ONLY`、`PAS_ZOTERO_SOURCE_ONLY` 改为 false；新任务 revision 2 rollout COMPLETED，health 正常。镜像及既有论文保留。
- 正式名单：82 位全部在 DynamoDB 与 `config/ac_roster.json` 中；81 位已核对 OpenAlex 身份并启用；Alan Veerman 保留为 needs_review，未猜测同名身份。原始名单不覆盖。
- 真实正式入库：完整名单返回 177 条来源记录，合并为 163 篇；163/163 PAS 回执，均为 seeded，不发送历史提醒。后续独立 ECS 任务 new=0、exit 0，验证持久化与去重。
- Slack App 已在 Acceleration Consortium 安装。真实 `/papers test` 收到汇总与 3 张 thread 卡片；真实相关性按钮落库；作者 Modal 完成 ORCID 查询和已有作者确认，名单仍为 82 位。
- 投递仅限操作者本人私信 `D0C6GC4H04F`。每日收集计划和每周私信通知均已启用；最新验证记录见 `review-evidence/production-verification.json`。

## Review 发现与修复

| 优先级 | 原问题与影响 | 处理 |
| --- | --- | --- |
| P0 | 示例 Anatole 的 ORCID `0000-0001-5272-6530` 真实返回 Adam Jackson；原 resolve 自动确认错误身份 | 增加返回姓名/别名核对，不匹配时拒绝自动填 ID。示例修正为 `0000-0001-7419-0466`，真实映射 `A5088793872` |
| P0 | 示例 Alán ORCID `0000-0003-1024-3325` 返回 404 | 示例修正为真实返回匹配姓名的 `0000-0002-8277-4434` / `A5071495561` |
| P1 | `store.find` 任意相同标题即合并，不同 DOI 的 Editorial 等会漏发 | 强 ID 优先；不同期刊 DOI、不同 arXiv ID 不以标题合并；泛化标题排除；标题匹配还须共享作者 |
| P1 | `add_ids` 的 COALESCE 只保存一个 DOI，数据 JSON 也没有更新 | 保存所有 DOI 别名及 OpenAlex ID，同步 JSON，并补迁移旧状态库；后续标题变化仍能按已知 DOI 命中 |
| P1 | 首次运行仅看数据库为空，零结果基线后出现的第一篇论文被静默 seeded | 独立 initialized 标记；零结果也完成基线。未解析作者在取数前报错，防止建立部分名单基线 |
| P1 | Webhook 自动重试，或“发送成功、提交前崩溃”，可能重复通知；原说明声称不会重发过强 | 持久化 sending 后发送；禁止 POST 透明重试；超时/5xx/异常响应保留 sending，提供显式 reconcile。只能说明正常重跑幂等，不能声称网络场景 exactly-once |
| P1 | 只有本地 SQLite，无 PAS 入库路径，容器重启丢状态 | 独立 PAS 回执；新增论文先入主表再通知。S3 每次 commit 检查点、PostgreSQL advisory lock、ECS 运行时间上限、失败队列 |
| P1 | arXiv 固定取 50 篇且无分页，繁忙作者可能漏报 | 增加分页、日期停止条件及 API 错误 feed 检查 |
| P2 | HTTP Retry-After 只支持浮点数 | 支持秒数、HTTP 日期、无效值回退及等待上限 |
| P2 | API 返回结构缺失或重复 cursor 可能被当作完整空基线 | 缺少 results/meta、重复 cursor 作为失败处理 |
| P2 | LLM irrelevant 永不重评，字符串 false 等非布尔结果会被误处理 | brief/model/启用状态改变时重评 irrelevant；响应类型异常时放行；未提供 brief 不允许拒绝 |

原 `data/ac_members.csv` 同样含上述两个错误 ORCID，既有文件保持原样。随后按用户要求逐一检索 82 位成员，修正后的身份、机构、代表作和证据链接独立保存在 `config/ac_roster.json`；生产使用其中 active 的 81 位。OpenAlex 本身可能错误合并同名档案，代表作核对不能保证其整个档案完全无误，卡片提供作者匹配问题反馈。

## 真实 API 核对

- 旧 `author.id:A…|A…` OR 过滤可用，响应 `meta.x_query` 将其解释为 `authorships.author.id`。
- `from_publication_date` 与 `sort=publication_date:desc` 可组合。
- 原 select 的 `id,doi,title,publication_date,type,primary_location,authorships,ids,is_retracted,abstract_inverted_index` 均真实返回；允许字段值为空，解析不会把空摘要当作完整摘要。
- `/authors/orcid:…` 返回单个作者对象，包含 `last_known_institutions`。错误 ORCID 既可能 404，也可能返回另一个真实作者；后者更危险。
- 原 `per-page=200` 实测仍被接受；官方已标为兼容行为并弃用，代码已改 100。
- 用 `per-page=1` 连续跟随两页 cursor，实际收到不同 work ID；证据见 `review-evidence/cursor-and-fields.json`。
- 本机与 AWS 均可无 API key 完成基础查询。这不代表无限配额；较大名单应配置免费 key并监控 429。
- 82 人检索期间本地共享 IP 确实触及 429 日配额，已让长 Retry-After 直接报错而不在任务里等待数小时。AWS 全名单收集及 Slack Modal 查询均真实成功。`deploy/configure_openalex.py` 可配置独立免费 key，目前未配置。
- 正式查询增加 `to_publication_date`（UTC 当天）及 `type:article|review|preprint|book-chapter`，服务端和客户端同时排除数据集/软件等非论文记录；真实正式任务返回 177 条来源记录。
- 真实 Crossref 查询 `10.1038/s41586-023-06792-0` 成功返回标题 *Autonomous chemical research with large language models*、期刊 Nature。
- arXiv 真实请求可完成，但该作者查询在测试日期窗口返回 0 篇，因此没有宣称验证过真实正例解析。分页/限速由构造 feed 回归测试验证。

官方依据：[OpenAlex 分页](https://help.openalex.org/api/paging/)、[认证和限流](https://help.openalex.org/api/authentication/)、[Slack incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)、[arXiv API 使用规则](https://info.arxiv.org/help/api/tou.html)。

## 第 7 节逐项判定

1. 标题误去重：**需要修，已修**。保守处理可能多发不同版本，但避免无证据合并不同期刊 DOI。
2. Retry-After 日期：**需要修，已修**，测试日期/无效/负值。
3. arXiv 频率：**需要修，已修**，页与 query 间隔 3.1 秒；同时修复原固定 50 条截断。
4. Scholar 作者名：**生产暂不启用**。邮件主题只是显示线索，不足以证明论文属于作者名单，实际邮件还需核验。
5. irrelevant 终态：**需要修，已修**，策略变化重评；论文即使不通知 Slack 仍保存到 PAS。
6. GitHub 60 天：**AWS 方案不受此限制**。保留原 Actions 示例供参考，未实际运行该 workflow；生产用 EventBridge。
7. 标题前缀：**小修已做**，覆盖 PDF/HTML/BOOK/CITATION/DOC；同时支持 HTML 属性顺序与单双引号差异。仍未取得真实 Scholar 邮件，不将构造测试宣称为真实邮件验收。

`claude-haiku-4-5` 在 [Anthropic 官方模型文档](https://platform.claude.com/docs/en/models/haiku-4-5/overview) 中是有效别名。此次未用真实 Anthropic key 调模型，云端可选 LLM 未启用。

## AWS 运行与恢复

资源栈：`paper-attribution-dev-author-monitor`，账户 `247893369214`，区域 `ca-central-1`。

- 后端：`paper-attribution-pas-dev-backend:1` → `:2`，仅两个语料策略环境变量改变。
- 后端镜像 digest：`sha256:42fe12262bc8c1fedf1c5332774db301537ccfc96811077df033cc7954dd9978`。
- API：[health](https://d1ai8ldqsh81fz.cloudfront.net/api/health)。
- 日志：`/ecs/paper-attribution-dev-author-monitor`。
- 验证状态：`s3://paper-attribution-artifacts-dev-247893369214/author-monitor/validation-20261005/state.db`，已开启桶版本控制。
- 正式状态：`author-monitor/production/state.db`；生产作者来自 DynamoDB active 名单，S3 CSV 保留初始配置。
- 每日时间：12:17 UTC，已启用。周报为周一 12:17 UTC，只发送已入库的新论文；初始 163 篇基线不进入周报。
- 已通过 AWS `TestEventPattern` 核对：exit 0 不触发失败队列；exit 1、TaskFailedToStart 会匹配。
- CloudWatch 失败队列告警已创建，默认未配置 SNS/email 订阅，不宣称邮件告警已接通。

测试任务 ID：

- `7961d901d2564f4abb01ef590dc7021b`：首轮真实取数/基线，exit 0。
- `6d9b8c3df7ac47b997cc200d1902ba43`：跨任务读回状态，new=0，exit 0。
- `403b86435cb24360ad5061e5d8d50cb8`：真实 RDS 插入/去重/回滚，exit 0。
- `c7ba5b4569054c6aa12eb4e6368cd2fd`：最终监控 revision 4 再次 dry-run，new=0，exit 0。
- `b6fe1171885641b39ce141bde2c8bedf`：全名单隔离 dry-run，exit 0；此前未排除数据集/软件，200 条基线。
- `aa570e9157904c12bb663b889d864666`：revision 6 正式基线，163 seeded、163 PAS 回执，exit 0。
- `97fb1ec38a794f7bbe5842b0a8aff51b`：revision 7 正式重跑，new=0、163 seeded，exit 0；bundle SHA256 `3fe1d9e9c0341000d0b103759b5d9bf2427763855acefd8cfd67a94d5ead9b97`。

## Slack 实测与边界

- App：AC Papers `A0C6VPXEQ5C`；工作区 `T012M3T3U01`；操作者 `U07K96PT5CL`；收件目标为本人私信。只请求 `chat:write`、`commands`、`im:write`；无聊天历史读取权限。
- 栈：`paper-attribution-dev-slack`。API Gateway → Lambda 签名验证/快速确认 → SQS → worker；DynamoDB 保存名单、反馈和投递任务；SSM SecureString 保存 bot token/signing secret。
- 真实预览根消息 `1791238436.903819`，3 条 thread 回复均已被 Slack 接受并在浏览器可见，DynamoDB preview=posted；生产 seeded 状态未被改动。
- 真实反馈已保存，验收产生的反馈标记 `test_interaction=true`，不冒充科研判断。
- `/papers add` 对 ORCID `0000-0002-8277-4434` 返回 Alán Aspuru-Guzik `A5071495561`，确认已有作者未重复创建；Modal/后台 home 任务均 complete。
- 实测发现并修复：Home 同一个 actions block 的 Previous/Next 共用 action_id，Slack 拒绝；增加唯一 ID 的回归测试，并以真实 views.publish 验证成功。
- 实测发现并修复：初次 Lambda 请求超过 Slack 的 3 秒确认期限。复用 SDK client 并提升 ingress memory 后，真实 `/papers test` 冷启动总计约 0.926 秒（执行 767.63 ms、初始化 158.09 ms），Slack 未报超时。
- 原 welcome 已成功、随后 Home 被拒的连接任务经核对后单独 reconcile；没有重发 welcome。正常重试有去重，网络结果不明时保留人工核对状态，不声称 exactly-once。
- 目前没有启用真实 LLM 摘要/自动科学相关性判断、Scholar 邮箱或图像抓取。后台存的是论文元数据，全文获取和科学归因属于既有 PAS 后续流程。
- 用户尚未启用系统桌面通知（浏览器显示 Slack 的通知提示）；这不影响消息进入本人 Slack 私信。

部署脚本会生成 `deploy/build/stack.json`，检查后用 `--apply` 执行；不要并发部署同一个栈。代码包按 SHA256 存储且启动时校验。首次隔离验证记录在 `review-evidence/aws-validation.json`；完整名单与 Slack 最终状态在 `review-evidence/production-verification.json`。

已有大范围脏工作区未整体构建或发布。本次修改限于监控目录及必要 Terraform 策略配置；没有提交、推送或宣称 CI 通过。
