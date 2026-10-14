# 新论文提醒与 Scholar 邮箱接入

> **2026-10-14 切换更新：** 根据用户要求，OpenAlex 定时监控已停止，改为
> Google Scholar 作者邮件方案。共享邮箱与首个订阅已确认；Microsoft Graph
> 后台授权和真实论文邮件验收仍待完成，采集尚未重新开启。当前配置、IT
> 请求和验收步骤以 [Microsoft 365 接入说明](SCHOLAR_MICROSOFT365.zh.md) 为准。
> **以下是此前 OpenAlex/IMAP 方案的历史记录，不代表当前启用状态；不要照旧命令重新开启采集。**

这轮补齐四件事：OpenAlex 主监控与 Scholar 邮件补充入口、每 4 小时检查并及时私信、每周扩大范围补查、独立故障提醒。现已扩展为同一工作区的多人独立私聊订阅，首次打开 AC Papers 即订阅，详见 [同事试用步骤](MULTIUSER.zh.md)。

## 旧版行为（历史记录）

| 环节 | 行为 | 边界 |
| --- | --- | --- |
| 主监控 | 82 位 AC 成员在名单中，81 位已确认身份并启用；Alan Veerman 待身份确认 | 姓名相同不代表同一位作者 |
| 检查频率 | UTC 00:17、04:17、08:17、12:17、16:17、20:17 | 检查时刻之后还需要任务执行时间 |
| 论文入库和私信 | 发现新记录后先存入 PAS 主论文表，拿到存储回执再分别发送论文卡片 | 每人每轮最多 20 张、全体每轮最多 200 张新卡片，轮换起点；积压会提醒管理员 |
| 周报 | 周一 12:17 UTC 起的首个成功任务，汇总上一个周一 12:00 至本周一 12:00 已发过的论文，明细放在 thread | 周报是回顾，新的论文不必等到周一 |
| 延迟收录补查 | 平时回查 90 天；每隔 7 天至少一次回查 365 天，以成功完成的补查为准 | 首次扩大范围，早于 90 天的旧论文只入库、不刷屏；以后补查新发现的旧日期论文会通知 |
| 故障提醒 | 独立 watchdog 每 15 分钟检查；同时接收 ECS 失败与 CloudWatch 告警事件 | 超过 4 小时 45 分钟没有完整成功记录、发送积压、入库失败或回执不明会私信；同一故障只提醒一次，恢复再提醒一次 |
| Scholar | 只读邮箱连接器和加密配置入口已实现 | 尚未取得邮箱，未完成真实邮件端到端验收，不声称已经订阅了 82 位作者的 Scholar 提醒 |

这里的“及时”指数据源出现记录之后，通常在下一轮检查和处理时通知。OpenAlex、Google Scholar 和出版社都有自己的收录延迟，无法保证论文上网后四小时内一定收到，也不能保证覆盖所有论文。365 天之外才补录的论文不在自动补查范围内。

暂停 Slack 更新仍会继续收集和入库，且不影响他人；运维故障提醒仍发给管理员。若 Slack 本身不可用，发送状态和 CloudWatch 错误会保留，但同一个 Slack 通道不能充当自己的备用通道。目前未配置邮件告警。

## 明天需要同事提供什么

1. 一个用于接收 **Google Scholar 作者的新论文提醒** 的专用邮箱，以及邮箱服务商。只有地址还不能读取邮件，需要邮箱管理员允许连接。
2. 一封真实作者提醒邮件，最好导出为 `.eml`，用于核对正文格式和作者姓名。不要提供普通“引用增加”或关键词提醒作为作者新论文测试。
3. 若尚未订阅作者，提供对应 Scholar 个人主页或在 Scholar 上完成作者提醒订阅。OpenAlex 名单不会自动变成 Scholar 订阅。

当前连接方式为 TLS IMAP（993 端口）与应用专用密码。密码只在终端隐藏输入，加密保存到 AWS SSM；不发到聊天或 Slack。如果学校邮箱仅支持 OAuth，需要按实际服务商增加 OAuth 接入，或使用获准的专用提醒邮箱。转发规则应保留原始 Scholar 邮件格式和发送者；普通人工转发可能无法识别，必须先验证实际邮件。

专用文件夹只放已启用监控作者的提醒。系统会核对 Scholar 发送者、邮件主题及作者名单；未知作者或无法识别的正文会显式报错，不会悄悄吞掉邮件。其他数据源仍可正常收集。

从仓库根目录运行：

```bash
# 先验证导出的真实邮件；不会连接邮箱或启用监控
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_scholar.py \
  --validate-eml /absolute/path/author-alert.eml

# 交互输入主机、邮箱、文件夹；应用专用密码隐藏输入
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_scholar.py

# 无密钥输出的状态查询、已保存配置的只读连接检查
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_scholar.py --status
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_scholar.py --check
```

配置工具必须从邮箱读取并成功解析一封属于监控作者的真实提醒，才保存 `/paper-attribution-dev-author-monitor/scholar-mailbox`。启用时跳过已经存在的邮件，从之后到达的提醒开始收集，避免历史提醒刷屏；保存配置后下一轮任务自动加载。

Scholar 显示名与名单不一致时，可显式传入 `--author-map /path/aliases.json`，内容例如 `{"Scholar display name": "Exact active watchlist name"}`。不采用模糊同名猜测。UID 游标与解析所得论文一起持久化；邮件只读、不标为已读、不删除。每轮最多处理 100 封新提醒。邮箱 UIDVALIDITY 变化时停止推进游标并报警，需要核对邮箱迁移。

启用后的最后一项验收是：让一封**新的真实作者提醒**到达，确认它在 PAS 中有记录或与已有论文合并，再确认私聊卡片及再次运行不重复。这一步必须等邮箱和真实邮件到位。

## 部署与故障恢复

生产监控需要 OpenAlex 免费 API key：匿名请求可以读取第一页，但后续游标
分页会返回 401。不能以作者查询或第一页成功代替完整采集验证。请在
<https://openalex.org/settings/api> 获取密钥，在完成 AWS SSO 登录的机器上运行：

```bash
python3 tools/author-paper-monitor/deploy/configure_openalex.py
```

工具隐藏输入密钥，验证两个不同的游标页面，再加密保存到 AWS SSM。下一轮
任务自动加载，无需重建镜像。不要把密钥粘贴到聊天、Git 或 Codespaces。
修复认证后应补跑完整采集，确认 `last_success_at` 更新、入库与投递没有积压，
再归档并确认移除对应的失败队列消息，最后核对 watchdog 的恢复回执。

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/aws.py --apply \
  --authors tools/author-paper-monitor/config/ac_authors.csv \
  --slack-app paper-attribution-dev-slack --enable-schedule --jev-shadow --run baseline
backend/.venv/bin/python tools/author-paper-monitor/deploy/slack_aws.py --apply
backend/.venv/bin/python tools/author-paper-monitor/deploy/health_aws.py --apply
```

论文、周报、告警发送前先保存 `sending`；Slack 成功返回后才保存时间戳。网络中断等不确定结果不自动重发。先检查私聊，再通过操作入口认领已有消息，或确认消息不存在后允许重试。

以下 SQLite 命令用于本地副本；生产环境必须通过已有 ECS bootstrap 的参数覆盖执行，使用同一生产前缀并持有数据库锁，不要上传手工编辑的 SQLite 覆盖生产状态。

```bash
python -m paper_monitor reconcile --db state.db --id 42 --recipient U0123456789 --delivered
# 仅确认没有收到时，改用 --retry

python -m paper_monitor reconcile-recap --db state.db --recipient U0123456789 --thread-ts 1720000000.000001
# 周报 thread 第 1 页的独立回执；页码从 0 开始
python -m paper_monitor reconcile-recap --db state.db --recipient U0123456789 --page 0 --thread-ts 1720000000.000002
# 仅确认对应消息没有收到时，将 --thread-ts ... 改为 --retry
```

ECS 的对应参数为 `--reconcile-id 42 --delivered`、`--reconcile-recap --thread-ts ...`、`--reconcile-recap --page 0 --thread-ts ...`，均须加 `--recipient U0123456789` 指定实际接收成员。旧版周报仍用 `--reconcile-digest`。恢复操作不会把“最近成功收集”的时间刷新成当前时间。

告警自己的不确定回执可通过以下工具恢复，不会主动发送消息；之后 watchdog 继续工作：

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/reconcile_health.py \
  --receipt-ts 1720000000.000001
# 仅确认告警未收到时使用 --retry
```

部署和实际测试证据见 `review-evidence/freshness-verification.json`。Jev 仍处于无密钥的 advisory 配置状态，四项功能不依赖付费模型。

本轮验收通过 159 项自动测试；实际一年补查新增 587 篇历史论文，750 条监控记录均在 PAS 主表中查到对应记录。再次收集没有新增记录，主表数量保持 1,285。私聊论文卡片、周报父消息与 thread、测试故障和恢复通知都取得了真实 Slack 回执；重新载入保存的测试状态未重复发送。Scholar 真实邮件验收仍待邮箱。

若失败队列保留的是已经人工核对并恢复成功的旧任务，先保存其任务状态和处理证据，再只确认移除对应队列消息；不要整队列清空或盲目重放。本轮发现并归档了一条此前已完成恢复的 `connect_dm` 残留消息。

## 可发给同事的解释

We have built a bot that watches our author list, saves new papers in our paper system, and sends updates to Slack. It checks every four hours and also provides a weekly recap. It uses OpenAlex as the main source, so it does not need to scrape Google Scholar or deal with its CAPTCHAs.

Your Google Scholar email-alert idea is useful as a second source. We have prepared that connection, but it still needs a dedicated mailbox and a real alert email to finish testing. Papers found through both sources will be matched so they are not announced twice. The bot also looks back regularly for papers added late and alerts us if monitoring stops working. We cannot promise instant notice of every publication, because both services can take time to index a paper; combining the two sources should improve coverage, which we will verify after connecting the mailbox.
