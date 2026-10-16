# Scholar 邮件监控：可靠性与运维

这份手册对应 2026-10-16 的修复。真实 Microsoft 365 接入仍需要 IT 的应用授权、
凭据及真实论文邮件验收。测试和代码部署不能代替这个验收，采集规则在此前保持关闭。

## 本轮发布验收

- 验证代码提交：`ac288486e6d695e0a197d892e2046a7d1a9f1543`。
  [GitHub CI](https://github.com/SissiFeng/paper-attribution-hub/actions/runs/38897972329)
  通过 218 项监控测试、49 项后端测试、两个前端构建，以及 29 个原有页面保留检查。
- AWS 监控任务更新至 revision 21；监控、Slack、看门狗三个 CloudFormation
  stack 均为 UPDATE_COMPLETE，运行代码包 SHA-256 已逐项核对一致。
- 真实 AWS 合成 canary 验证 S3 原件与检查点恢复、邮件隔离/重放、RDS 稳定 ID。
  数据库事务已回滚。它不代表真实 Microsoft 邮件已经接通。
- 只向已验证的运维本人私聊发送两条 TEST 告警/恢复消息，均有 Slack 回执；
  各自重复调用未再次发送。生产监控状态仍为 awaiting_mailbox，没有虚报恢复。
- 旧 OpenAlex 401 失败事件已核对后续成功记录，存入私有 S3 后逐条确认处理；
  失败队列为空，原告警恢复 OK。没有清空队列或改写成功时间。
- S3 保留策略已回读核对，当前检查点已另存备份。清理由生命周期异步执行，
  不声称所有旧版本已经立即回收。验证前缀下测试产物保留 7 天。
- 独立 SNS 告警主题已部署；收件地址仍待用户选择，尚无邮件订阅。
  Microsoft 应用凭据仍待 IT，真实论文邮件端到端验收未完成，15 分钟规则保持 DISABLED。

机器可读证据：[部署与验收记录](review-evidence/scholar-reliability-verification.json)。
作者覆盖表：[82 位成员 CSV](review-evidence/scholar-alert-coverage.csv)。

## 数据流和恢复边界

1. 固定共享邮箱、固定文件夹的 Graph delta 查询，只读，不改邮件。
2. 按邮箱身份及 ImmutableId 登记每封提醒，原始 MIME 用 SHA-256 命名并加密保存
   到私有 S3；记录保存成功后才能推进该页的游标。
3. 每封邮件独立解析。所有候选论文标题必须有有效元数据；格式不完整、作者无法
   匹配、原件暂时不可读时，记录错误并留待重试，其他邮件继续。
4. 解析结果与论文入监控库的完成标记一起提交。进程重启会重放尚未完成的邮件，
   用已保存的标识符去重；无需依赖 Graph 再返回旧邮件。
5. PAS 写入使用永久 ID。后补 DOI 更新原论文；多个冲突记录进入人工核对，
   不合并 Wiki、笔记或用户数据。一个论文入库失败不阻塞其他论文。
6. 每位 Slack 用户独立维护待发队列和回执。发送前保存 `sending`，收到回执后保存
   `posted`；429 按 Retry-After 等待，超时或 5xx 保留待核对状态，不盲目重发。

邮件状态：`captured` → `ready` → `processed`；异常为 `fetch_retry` 或
`quarantined`，非论文提醒为 `ignored`。原始邮件不公开、不放进 PAS 的普通论文接口。
不读取共享邮箱其他文件夹；学校授权边界仍为整个共享邮箱的只读权限。

当前继续使用既有 SQLite + S3 检查点和 PostgreSQL 锁，不做整库迁移。
发送每篇卡片的检查点由四次减为必要的发送前、发送后两次。将来需要大量并发
接收者时，再将状态/待发队列迁入已有 PostgreSQL，拆分投递任务。

## 首次启用与历史邮件

配置工具输出标题、作者、链接、到达时间和通知范围的预览。
`notify_after` 默认是验证时间；比它更早的邮件仍进入 PAS，但不补发 Slack。
边界依赖 Graph 的真实邮件到达时间，缺失时间的论文提醒会隔离，不猜测。

```bash
python3 tools/author-paper-monitor/deploy/configure_scholar_graph.py \
  --client-id '<IT 提供>' --folder-id '<IT 提供>' \
  --secret-expires-at '<ISO 时间，例如 2027-04-01T00:00:00Z>'
```

读原邮件核对预览后，使用同一个 `--notify-after`，加上
`--accept-publication-sample --expected-paper-count N --save` 保存验收结果。
空文件夹、确认邮件、部分解析、作者隔离或未完成分页不能通过论文样本验收。
轮换凭据必须保留原来的通知边界和作者映射；凭据提前 30 天进入运维提醒。

启用前还须在独立前缀进行 dry-run，再对明确的测试范围检查真实 PAS ID、页面链接、
Slack 回执和重跑去重，最后才开启定时规则。不得用合成 canary 代替真实邮件验收。

## 异常邮件与作者覆盖

查看状态（不发送消息）：

```bash
python -m paper_monitor mail --db state.db
python -m paper_monitor mail --db state.db --retry-id '<报告中的 ID>'
```

AWS 任务入口支持 `--mail-report` 和 `--retry-mail ID`；这两个操作不触发采集或发送，
也不更新“最后成功采集”时间。先修正作者映射或解析器，再请求重试；不能把异常
邮件直接标为已处理。未知作者和布局每小时重试一次；Graph 取件失败下轮按等待时间重试。
delta 失效会重扫，已经处理的 ImmutableId 仍跳过。

作者覆盖表可交给实习生填写：

```bash
python3 tools/author-paper-monitor/deploy/scholar_coverage.py --export /tmp/scholar-coverage.csv
python3 tools/author-paper-monitor/deploy/scholar_coverage.py --import-csv /tmp/scholar-coverage.csv
# 核对验证结果后加 --apply。
```

`profile_url` 必须是 Scholar 作者主页；`alert_created`、`subscription_confirmed`
填写 true/false。姓名和 person_id 必须匹配既有名单；导入不创建 Google 订阅，
不改变个人 Slack 订阅，也不自动解除作者身份待核对状态。
`last_received_at` 和 `publication_messages` 来自实际处理记录，不能由 CSV 伪造。
App Home 显示“未核实建立 / 已建立待确认 / 已确认 / 已收到论文邮件”。

## 状态、告警和保留期限

- `/papers status` 分别显示成功检查邮箱、PAS 同步、Slack 投递检查时间。
  空邮箱检查成功不算故障。45 分钟没有成功邮箱检查才触发采集过期告警。
- 邮件隔离、入库积压、发送不确定、凭据将到期分别报告；隔离本身不使 ECS 崩溃，
  避免每轮重复写失败任务队列。Slack 故障通过独立 SNS 主题告警到运维邮箱。
- SNS 邮件订阅需要收件人点确认链接；`PendingConfirmation` 不代表告警已经可达。
  不在群发频道中测试故障告警。
- 当前 S3 状态不设置删除或冷归档；旧状态版本超过 7 天且超出最近 10 个旧版本
  后才由 S3 清理。运行代码包始终可直接下载。相关 Terraform 与部署脚本保持一致。
- 已处理/已忽略原始邮件保留 90 天；只有所有引用均处理超过 90 天才删除原件。
  S3 的旧原件版本再保留 7 天。尚未处理、隔离和抓取失败记录不自动删除。
- 失败队列不得直接清空。先检查具体任务和日志、保存事件证据，再逐条确认已解决项。
  不人为改写成功时间或以“等待邮箱接入”冒充系统恢复。

## 云端验证与发布

构建、测试在现有 Codespace；AWS 操作在已通过 SSO 验证的本地运维环境。

```bash
backend/.venv/bin/python -m pytest tools/author-paper-monitor/tests -q
```

部署监控器时使用 `--source scholar --slack-app paper-attribution-dev-slack`，
保留已有 Jev shadow 设置，不加 `--enable-schedule`。Slack 更新使用
`deploy/slack_aws.py --code-only --apply`，保留现场访问控制和权限配置。
`deploy/health_aws.py --alert-email '<运维邮箱>' --apply` 创建独立 SNS 告警；
省略地址会保留已配置订阅，新部署时不创建邮件订阅。
`deploy/storage_policy.py` 先输出保留规则，审阅后 `--apply`，不会立即清空旧版本。

AWS 入口 `--verify-reliability` 必须使用 `author-monitor/verification/<唯一 ID>` 前缀。
它检查真实 S3 原件/检查点回读、隔离/重放、RDS 稳定 ID，以及 Slack `auth.test`；
SQL 事务回滚，不写主库测试论文，不发送 Slack 消息。
结果明确标记 `synthetic: true`、`graph_live_test: false`、`slack_messages_sent: 0`。

官方参考：[Graph delta](https://learn.microsoft.com/en-us/graph/delta-query-messages)、
[Slack 限流](https://docs.slack.dev/apis/web-api/rate-limits/)、
[S3 生命周期](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html)。
