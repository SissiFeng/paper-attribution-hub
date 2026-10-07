# AC Papers 私信试运行

验收日期：2026-10-05。当前已安装、连接、测试并启用；只给 Sissi Feng 本人私信。

## 直接使用

[打开 AC Papers 私信](https://app.slack.com/client/T012M3T3U01/D0C6GC4H04F)。已存在一条标为 Connection test 的汇总，打开其 3 replies 可查看真实论文卡片。

在 AC Papers 的 Home 页可以查看作者、添加作者、暂停某位作者、发测试消息和暂停/恢复周报。也可以输入：

| 操作 | 命令 | 效果 |
| --- | --- | --- |
| 预览 | `/papers test` | 再发一条明确标为测试的汇总和三篇真实论文，不改变正式通知历史 |
| 状态 | `/papers status` | 查看启用人数、通知状态、最近成功收集时间 |
| 作者名单 | `/papers authors` | 更新 Home 页 |
| 添加作者 | `/papers add` | 输入姓名或 ORCID，检索并确认身份；已有档案不会重复添加 |
| 暂停通知 | `/papers pause` | 停止 Slack 周报，仍每日收集和入库 |
| 恢复通知 | `/papers start` | 只允许已连接操作者，且必须先通过私信预览 |

## 当前运行方式

- 82 位 AC 成员全部在名单中；81 位监控中。Alan Veerman 未找到可靠的 OpenAlex 档案，保留为待确认；提供其 ORCID 或代表作后可继续核对。
- AWS 每天 12:17 UTC 查最近 90 天，先去重、保存到 PAS 主论文表，再处理 Slack 通知。初始 163 篇已入库，不当作新消息发送。
- 每周一 12:17 UTC，有新论文才发一条汇总，明细放在线程里。10 月 5 日启用时本周时点已过，下一次计划周报为 10 月 12 日。超过 20 张卡片的汇总会在后续每日任务继续补齐线程。
- 相关/不相关/作者匹配问题均记录到 DynamoDB。它们目前供人工复核，不自动删除论文或改变科学归因。
- 当前未启用 LLM 摘要、Scholar 邮箱、论文图片或合作关系推断；不会用生成内容假充原始论文事实。
- 元数据入库不等于全文已下载或论文已完成科学分类。

## 已核验

59 项本地测试；ruff、Python 编译检查通过。真实 OpenAlex resolve、dry-run、全名单查询、分页及字段核对已完成。两次正式 ECS 运行均 exit 0；163 篇都有 PAS 回执，第二次 new=0。PAS 在线 API 可读回导入论文。

真实 Slack `/papers test`、三张 thread 卡片、反馈落库、ORCID Modal 查询和已有作者确认均通过。初次请求超时和 Home 按钮 ID 冲突已修复；修复后实测冷启动约 0.93 秒。周报通过后台相同的操作者/预览校验启用；未来定时触发的新论文周报尚未发生。

Mac 在最后界面核对时锁屏；私信与按钮的上述实测已先完成，后台启用与 Home 更新不受影响。截图保存在 `deploy/build/slack-private-preview.png`（不纳入 Git）。

## 维护边界

- OpenAlex 可能延迟收录、遗漏或错误合并同名作者。当前 90 天窗口不能发现更晚才收录的旧论文。
- AWS 匿名 API 实测可用；本机共享 IP 曾耗尽日配额。推荐通过 `deploy/configure_openalex.py` 配置独立免费 key，凭据仍保存到 SSM。
- S3 状态检查点、数据库运行锁、失败队列和 CloudWatch 告警已部署。尚未配置告警的 SNS/email 订阅；日常可用 `/papers status` 看最近成功运行时间。
- 发送结果不明时暂停自动重发，避免重复刷屏；人工核对后使用 README 中的 reconcile 流程。
- 没有提交或推送代码，也未整体发布工作区中的其他变更。

细节：[Review 与风险处理](REVIEW_RESULT.zh.md)、[实际部署证据](review-evidence/production-verification.json)、[给同事的英文说明](COLLEAGUE_REPLY.en.md)。
