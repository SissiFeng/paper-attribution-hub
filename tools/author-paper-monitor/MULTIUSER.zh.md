# AC Papers 多人试用

AC Papers 已安装在 **Acceleration Consortium** 工作区。Slack App 按工作区安装；同事不必重新申请密钥、连接 AWS 或取得管理员连接码。每位同事第一次打开应用后建立自己的私聊订阅。本版本支持这个已安装的工作区，尚未实现面向其他工作区的公开 OAuth 安装服务。

## 同事的操作

1. 在 Acceleration Consortium 的 Slack 中找到 **AC Papers**，打开 **Home**。首次打开后自动开启自己的订阅，欢迎消息在 **Messages** 中。
2. 点击 **Send me a test**，或输入 `/papers test`，查看真实论文的预览和 thread。预览不消耗正式新论文队列。
3. 输入 `/papers status` 查看最近一次成功采集、作者数量及自己的订阅状态。也可直接运行 `/papers start` 完成订阅。
4. 之后无需手动检查。系统每 4 小时检查作者列表，新论文存入 PAS 主论文表后私信给每位订阅者，周一另发个人周报。
5. `/papers pause` 只暂停自己的推送；`/papers start` 恢复。打开 Home 不会擅自恢复已暂停的订阅。恢复时会处理暂停期间的积压。

名单包括 82 位 AC 成员，其中 81 位身份已确认、正在监控；Alan Veerman 仍等待身份信息。列表由管理员维护，同事可查看、反馈相关性和报告作者匹配错误。首次订阅不会补发订阅之前的历史论文。新的发现取决于数据源收录时间，并非保证论文上线后 4 小时内必达。大量新论文会分轮处理。

Google Scholar 邮件补充入口仍待真实邮箱和邮件验收；目前主监控依赖 OpenAlex。Jev 仍待 API key，不影响普通采集、入库或提醒。

## 可直接发给同事

AC Papers is ready to try in the Acceleration Consortium Slack workspace. Search for **AC Papers** and open its **Home** tab. That automatically turns on your personal subscription. You can click **Send me a test** or run `/papers test` to see a preview with real papers.

The bot checks our shared AC author list every four hours, saves newly discovered papers in our paper system, and sends them to you privately. You also get a weekly recap. `/papers status` shows the latest successful check; `/papers pause` pauses only your own messages and `/papers start` resumes them. You do not need an API key or an AWS account. We currently monitor 81 confirmed authors out of the 82-person list; one still needs identity confirmation.

For testing, please check that you receive the welcome message and paper preview in your own conversation with AC Papers, and that pausing and resuming changes your own status. New-paper notifications depend on when the source indexes each publication. The Google Scholar email connection still needs the dedicated mailbox before we can finish testing it.

## 实现与恢复

Slack 的 `app_home_opened` 事件自动登记成员，签名及工作区检查保留。回调已指向现有 AWS `/slack` 地址，无需增加现有 `chat:write`、`commands`、`im:write` 之外的权限。官方说明：[App Home opened event](https://docs.slack.dev/reference/events/app_home_opened/)。

每个成员有独立的 DynamoDB 订阅、Slack 私聊和 SQLite `(paper_id, user_id)` 发送记录。暂停和发送失败不会修改其他成员的记录。论文在 PAS 只存一次，卡片和周报则分别保存每个人的回执。单人每轮最多 20 张新卡片，全体每轮最多 200 张，轮换发送起点；周报有独立回执，计数不包含在 200 张内。运维故障仍只提醒管理员。

回执不确定时，先核对对应成员的私聊，再使用生产 ECS 的既有 bootstrap、同一生产前缀和数据库锁执行：

```text
--reconcile-id 42 --recipient U0123456789 --delivered
--reconcile-recap --recipient U0123456789 --thread-ts 1720000000.000001
--reconcile-recap --recipient U0123456789 --page 0 --thread-ts 1720000000.000002
```

只有确认消息没有收到时才用 `--retry`。不要上传手工修改的本地 SQLite 覆盖生产状态。

本轮 173 项自动测试与 Ruff 检查通过，三个 AWS 栈更新完成，真实采集任务退出码为 0；750 条已有论文和入库回执保留，没有发送历史论文。实际 Slack Home 回调、个人暂停/恢复、真实论文预览已验证。

验收证据见 `review-evidence/subscribers-verification.json`。云端双订阅路由测试使用两个隔离的模拟身份，两条标注 TEST 的消息均只发给原管理员；重载 S3 状态后重复发送数为 0，不将模拟身份或测试论文加入生产系统。真实第二位同事的首次打开和欢迎消息，需要其本人试用确认。
