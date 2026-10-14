# Microsoft 365 共享邮箱 → PAS → Slack

## 2026-10-14 的真实状态

- 用户要求停用原来的 OpenAlex 定时采集，改用 Google Scholar 作者邮件。
- 已在 AWS 停止旧定时规则；生产论文、订阅者及投递回执保留。
- 已通过 `sissi.feng@utoronto.ca` 在 Outlook 网页访问
  `comms.acceleration@utoronto.ca`，确认存在 `Google Scholar Alerts` 文件夹。
- 文件夹当时仅有一封 **Confirm your Scholar alert**，主题中的订阅对象为
  **Alan Aspuru-Guzik - new articles**。确认链接已打开，Google 显示
  **Alert confirmed**。这不是包含论文的邮件，不能作为解析/入库验收。
- 该账号访问 Entra 应用注册页面返回 401 / You do not have access。
  网页邮箱委派权限并不等于 AWS 后台应用权限，仍需要学校 IT 配置。
- 代码已提供 Graph 只读连接、delta 分页、断点、配置工具和自动测试。
  在 Microsoft 授权与真实论文邮件验收前，定时采集保持关闭，状态为
  `awaiting_mailbox`。不能把“待接入”报告成“恢复正常”。

## 工作方式

```text
Scholar 作者主页 / New articles 订阅
  → comms.acceleration@utoronto.ca
  → Outlook 规则归入 Google Scholar Alerts 文件夹
  → AWS 每 15 分钟只读该文件夹
  → 作者核对 + 论文去重 → PAS 主论文表 → 各用户 Slack 私信
```

邮箱可以继续用于其他工作。规则应移动原邮件到专用文件夹，不要人工转发、
修改发件人或正文。仅使用 Google Scholar **作者的新论文**提醒，不能用
普通 Google Alerts 关键词搜索、引用增加通知替代。不要将无关邮件移入该
文件夹。确认邮件会忽略；不认识的作者、主题或论文正文会报错并保留游标。

名单中的 82 位成员不等于 82 个已确认的 Scholar 订阅。目前只确认了 Alán
的订阅。先等第一封真实论文邮件通过验收，再让实习生逐个核对作者主页，
订阅 New articles，使用共享邮箱并完成每封确认邮件。记录姓名、主页 URL、
确认日期；姓名不一致时使用明确的 `author_aliases`，不进行同名猜测。
作者订阅与名单变更由管理员一起维护；个人 `/papers pause` 仍只影响本人。

通知时效为“邮件到达后下一轮检查 + 处理时间”，不是论文发表后 15 分钟。
Google 的收录延迟、邮件发送频率和作者档案遗漏都不受 PAS 控制。停用
OpenAlex 后没有该源的补查覆盖；无邮件不能直接判定为没有新论文。

## 请学校 IT 配置

创建单租户后台应用 **PAS Scholar Mail Reader**，租户：
`78aac226-2f03-4b4d-9037-b46d56c55210`。使用 Microsoft Graph client credentials
应用身份。无需 Sissi 的密码、个人 refresh token、Mail.Send 或 Mail.ReadWrite。

推荐由 Exchange 管理员通过 **Application RBAC** 仅授予共享邮箱的
`Application Mail.Read`。示意命令如下，管理员须替换占位符并核对组织策略：

```powershell
Connect-ExchangeOnline
New-ServicePrincipal -AppId <client-id> -ObjectId <enterprise-service-principal-object-id> -DisplayName "PAS Scholar Mail Reader"
New-ManagementScope -Name "PAS-Scholar-Mailbox" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'comms.acceleration@utoronto.ca'"
New-ManagementRoleAssignment -App <enterprise-service-principal-object-id> -Role "Application Mail.Read" -CustomResourceScope "PAS-Scholar-Mailbox"
Test-ServicePrincipalAuthorization -Identity <enterprise-service-principal-object-id> -Resource comms.acceleration@utoronto.ca
Test-ServicePrincipalAuthorization -Identity <enterprise-service-principal-object-id> -Resource sissi.feng@utoronto.ca
```

第一项 InScope 应为 True，第二项为 False；再选一个其他邮箱做否定验证。
ObjectId 是 Enterprise Application 的 service principal ID，不是应用注册
对象 ID。**不要同时添加租户级、无范围限制的 Graph Mail.Read 应用授权**：
这类权限会叠加，可能绕过上述范围；测试命令也不代替检查 Entra 授权。
权限传播可能延迟，首次 403 应先核对管理员配置。

权限范围是整个共享邮箱，不能声称 Microsoft 在这里授予了“仅文件夹权限”。
程序通过固定 mailbox/folder 路径仅读取专用文件夹，不访问个人邮箱，不列出
其他邮件正文，不标为已读，不移动、删除或发送邮件。

IT 交付：client ID、该文件夹的 Graph folder ID、只读范围验证结果，以及通过
组织批准的安全渠道提供的应用凭据。设置凭据有效期与轮换负责人；凭据过期
会导致明确的采集失败告警。不要把 secret 发在聊天、邮件正文或 Git。

官方依据：[Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)、
[应用身份 OAuth](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)、
[邮件增量查询](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0)。

## 配置与启用验收

本地只运行 stdlib + AWS CLI 的配置工具；构建和测试仍在 Codespaces。
先完成 AWS SSO 登录，然后运行（secret 隐藏输入）：

```bash
python3 tools/author-paper-monitor/deploy/configure_scholar_graph.py \
  --client-id '<IT 提供的 client ID>' \
  --folder-id '<IT 提供的 Graph folder ID>'
# 核对只读检查报告后加 --save，把配置保存为 AWS SSM SecureString。
```

工具核对文件夹名、读取增量分页并解析真实邮件，但不写论文、不发 Slack、
不启用定时任务、不保存测试 delta 游标。只有确认邮件时会明确报告
`publication_sample_verified: false`。这仍可保存连接配置，但启用部署检查
要求有真实论文样本。已有游标保存在生产检查点，轮换 secret 不会重置它。

最后由运维完成：

1. 对一封真实新论文邮件完成只读解析；核对作者、论文标题、链接及去重结果。
2. 使用复制的检查点和独立 S3 前缀运行 ECS `--dry-run`；禁止对生产前缀 dry-run。
   验证日志中无 OpenAlex/arXiv 采集调用，且没有 PAS/Slack 写入。
3. 保留当前生产检查点，手动执行一次 Scholar 生产任务。确认 PAS 存储回执、
   用户 Slack 投递回执、无解析错误；已有论文应合并且不重复通知。
4. 重跑同一批邮件，确认无重复论文或投递。核对首轮历史文件夹范围：本连接器
   会导入文件夹快照，已存在的论文去重，尚未见过的旧邮件论文也会进入通知队列。
   启用前整理该专用文件夹，避免把多年历史邮件一次性加入。
5. 更新现有 CloudFormation 的 Scholar 任务与 15 分钟规则为 ENABLED，并将
   DynamoDB settings.monitoring.state 改为 active。部署工具 `deploy/aws.py`
   的 `--source scholar --enable-schedule --apply` 会校验样本并同步状态；现有
   生产部署优先审阅 live template 的窄范围变更，不改后台镜像或数据库。
6. 核对下一轮自动执行和 watchdog。旧失败队列先留证、逐条核对后确认删除；
   不清空队列，不伪造 last_success_at。未收到论文但成功检查空邮箱是正常运行。

## 可靠性边界

- Graph deltaLink 和论文记录一起提交到现有 S3 检查点。任何分页或解析失败，
  整批不推进游标；下次可重复读取，论文和每人投递记录继续去重。
- MIME 只针对 Scholar 新论文主题获取；分页链接限制在固定 Graph 主机、
  共享邮箱和文件夹，拒绝重定向；错误不打印 secret、token、正文或 cursor。
- 超时/429/临时故障留待下一轮重试。delta 过期需核对后重扫，不能悄悄跳过。
- 每次最多 50 页、每页请求 100 条，单响应最多 2 MB。超限会报错而不是截断。
- 已有 DOI/arXiv/标题加作者去重、先入库后通知和不确定发送人工核对继续生效。
  标题变化且没有共同标识符、作者缩写等仍可能产生重复，不能保证绝对零重复。
- Scholar 模式不执行 OpenAlex、arXiv 定时扫描，也不要求 OpenAlex ID 或 API key。
  新论文可调用 Crossref 补充元数据；这不是另一个周期性监控源。
- 正式启用后 45 分钟无完整成功任务告警。等待授权期间不把旧采集失败当作
  新故障，也不发送虚假的恢复通知；Slack 不确定投递、入库积压等仍保留。

## 可转发给同事

Thanks — I can access the shared mailbox, and I have confirmed the Alán
Aspuru-Guzik “new articles” subscription. The folder currently contains the
confirmation email; we still need the first actual paper alert to complete the test.

The shared address can continue to be used for other purposes. Please keep the
Scholar alerts in the “Google Scholar Alerts” folder using an Outlook rule.
The bot will read that folder, match papers against the existing library, save
new papers in PAS, and send Slack updates. We have paused the previous OpenAlex
polling while switching to this workflow.

There is one IT step: access in Outlook lets me view the mailbox, but the AWS
service needs its own read-only application access, restricted to this shared
mailbox. It will not use my personal password. Once IT grants that access and
we validate the first paper alert, we can enable the 15-minute checks and then
expand to the other AC authors. These should be Google Scholar author-page
“new articles” alerts, rather than general Google keyword alerts.
