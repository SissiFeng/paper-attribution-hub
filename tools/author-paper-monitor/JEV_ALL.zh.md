# Jev 八项功能：使用、费用与验收

八项功能均已接入业务入口，延续已同意的 **shadow（建议与对照）模式**。正常采集、入库、去重、问答和 Slack 投递继续由原有流程处理。Jev 的输出独立保存，供操作者查看、标注和评估；不会因模型建议自动删除论文、合并作者、修改人工结论或批准图谱关系。

用户目前没有 TypeSafe API key。全部入口都支持缺少 key 的回退，不生成假评分，不发起付费推理。后续接入 key 后才能检验真实响应、时延、费用和 AC 语料上的判断质量。

## 八项功能及入口

| 功能 | 已接入的实际入口 | 结果与约束 |
| --- | --- | --- |
| 作者身份核对 | `resolve`、Slack `/papers add` 候选选择 | 比较姓名、机构、ORCID、代表作；保留所有原候选及顺序，展示建议，操作者最终确认。冲突 ORCID 不交给模型覆盖。每次最多评估 5 个候选。 |
| 论文版本关联 | 每日监控，及 PAS 操作者接口 | 从最近 200 条记录中按共同作者与相似标题找最多 20 对候选，再判断是否为同一研究；只记录关联建议，不合并记录或改变通知状态。此候选筛选不是全库查重。 |
| 周报阅读优先级 | 每日监控、`/papers review` 私信预览 | 0–4 分、完整概率分布和下一步阅读建议；预览展示已评分子集前三篇，正式周报与未评分论文保留原有行为。 |
| 全文、补充材料与强模型分流 | 每日监控、PAS 单篇论文分析接口 | 区分元数据足够、需要全文、补充材料、强模型或人工复核；仅建议，不自动发起下载或额外付费模型。 |
| 问答检索路径 | PAS modular RAG 的 routing 步骤 | 对数据库统计、全文、图谱、混合检索和澄清给出选择；在 trace 中保留建议与原路由，实际路由不变。 |
| 回答证据检查 | PAS modular RAG 生成回答后 | 至多检查 3 个带引用的主张与原文配对，区分支持、矛盾、不足；绑定论文和片段 ID，不改写答案，不宣称检查了未引用内容或整篇回答。 |
| 人工复核优先级 | PAS 审核队列和单篇操作者接口 | 为队列前三项提供独立优先级建议，原排序不变；已确认、训练与保留评估记录受保护。标签边界文件缺失/无效时返回 `protected_record`，不给未知记录评分。 |
| 知识图谱关系证据 | PAS 实体提取完成后、操作者接口 | 核对最多两个方法/仪器/软件候选的来源片段，区分实际关系、仅提及、矛盾和不足。原文必须属于同一篇论文；建议存入独立元数据字段，不批准或删除图谱关系。 |

这些入口也统一提供 `POST /api/jev/evaluate`，方便在申请 key 后逐项实测。身份与检索使用显式输入；论文、版本、回答证据和图谱证据使用系统已有论文/片段，不能用请求中的伪造来源替换数据库原文。

## Slack 测试

打开 AC Papers 与你的私信，运行：

- `/papers decisions`：查看八项功能最近的建议；没有实际推理时显示尚未评估，不显示示例概率。
- `/papers review`：查看已有阅读排序实验，缺少 key 时说明等待配置。
- `/papers authors`：打开 Home。新增 **Eight Jev workflows** 按钮；作者名单、测试消息、启动/暂停周报入口仍在。
- 建议成功生成后，点击 **Review suggestion**，用弹窗记录人工标签。标签不会自动用于训练或改变分类。

八项功能概览、阅读建议和反馈仅供已绑定操作者使用，消息发到本人 DM。即使在频道输入命令，也不会将概览发给频道。无需增加 Slack OAuth 权限。

私信入口：<https://app.slack.com/client/T012M3T3U01/D0C6GC4H04F>。

## 隐藏输入配置

在项目根目录运行：

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py
```

输入来自 TypeSafe 的 key，终端不回显。工具以现有监控库的一篇公开论文做一次真实接口检查；验证成功才加密存入 AWS SSM `/paper-attribution-dev-author-monitor/jev`。此单次检查会调用模型，但不属于准确率评估。配置入口不接受聊天中粘贴的密钥，不把 key 放进 shell 参数。当前直接接入 TypeSafe，尚未接 OpenRouter。

```bash
# 仅检查配置，不调用模型
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --status
# 用已有 key 做一次真实接口检查
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --check
# 查看线上八项功能、配置状态及共享限额
backend/.venv/bin/python tools/author-paper-monitor/deploy/jev_admin.py status
# 获取最近的决定和原始概率
backend/.venv/bin/python tools/author-paper-monitor/deploy/jev_admin.py decisions
```

AWS 的监控器、PAS 后端和 Slack 作者查询任务只被授权读取这一确切的 Jev 参数。后端与 Slack 进程最多缓存配置 60 秒；监控器每次运行读取。操作者 API 另有独立密钥，保存在 `/paper-attribution-dev-author-monitor/jev-admin-key`；`jev_admin.py` 自动读取并发送，不显示其内容。该管理凭据不是 TypeSafe 计费 key。

逐项测试可将请求写到本地 JSON，例如：

```json
{"task":"retrieval_route","context":{"query":"How many papers did the monitored authors publish this month?"}}
```

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/jev_admin.py evaluate \
  --input /absolute/path/request.json
```

其他任务字段见 `backend/app/api/jev.py` 的 `EvaluationIn`：单篇使用 `paper_id`；版本另加 `other_paper_id`；证据任务另加 `chunk_id` 与 `context.quote`，其中 quote 必须是该片段的真实子串。所有调用仍受每日共享限额与保护规则约束。

## 成本与限额

2026-10-05 核对的 [TypeSafe 官方价格](https://docs.typesafe.ai/models)：固定版本 `jev-1.13.0` 按输入 token 计费，每百万输入 token **US$0.042**，输出免费。API key 是账户凭据；实际消耗的是账户的额度/余额。没有确认新账户免费额度，不能保证调用永远免费。

例如每月 10,000 次、每次总输入 3,000 token，模型费用约 **US$1.26/月**。这是示例，不是本系统实际账单；AWS、其他模型或未来费率变化另计。

当前 AWS 的全部 Jev 流程共用 DynamoDB 原子计数器，**每 UTC 日最多 20 次尝试**。错误/中断也占用一次尝试，不因重试绕过额度；每日额度不是美元上限，输入长度会影响费用。原阅读评分每轮最多 8 次/45 秒，新版本与分析建议合计每轮最多 8 次/30 秒。新流程 HTTP 超时 4 秒，原评分器 8 秒；均不自动重试，不跟随重定向。独立配置检查不计入后台额度。

成功结果按完整输入、问题版本、研究方向和模型版本缓存；相同输入不重复付费。错误/中断对同一输入至少冷却 24 小时，额度耗尽等到下一个 UTC 日。费用报告只估算有 usage 的成功响应；未返回用量保留未知，失败和配置检查费用未合计，不能替代供应商账单。

没有 key 时所有八项流程都不调用模型，因此本轮 **Jev 推理调用 0 次**；AWS 运行仍有基础费用。

## 人工评估闭环

每个成功决定保存输入、任务/模型版本、指纹、完整概率、API confidence、token 用量、延迟及估算输入费用。没有经独立测量，不能把 API confidence 当作 AC 论文上的准确率或校准证明。

除 Slack 弹窗外，可导出不显示预测的 CSV，先独立标注，再计算各任务准确率/MAE 与多类别 Brier：

```bash
cd tools/author-paper-monitor
# 云端读取：需要有效 AWS SSO；省略 SLACK_TABLE 则读取本地 JEV_STATE_DB
AWS_PROFILE=pas-sdl0-dev AWS_DEFAULT_REGION=ca-central-1 \
SLACK_TABLE=paper-attribution-dev-slack \
../../backend/.venv/bin/python -m paper_monitor.jev_evaluation --out /absolute/path/jev-review

# 填完 human_label 后导入，先校验完整 CSV，再保存人工标签
AWS_PROFILE=pas-sdl0-dev AWS_DEFAULT_REGION=ca-central-1 \
SLACK_TABLE=paper-attribution-dev-slack \
../../backend/.venv/bin/python -m paper_monitor.jev_evaluation --out /absolute/path/jev-review \
  --labels /absolute/path/jev-review/jev-workflow-labels.csv --reviewer YOUR_NAME
```

仅导出最近 50 个决定；报告的样本范围明确注明，不能作为全库统计或独立留出集研究。已有 CSV 不覆盖，新一轮使用新目录。未标注时报告只给样本数，不制造准确率。原阅读排序还有 NDCG 等专用指标，见 [第一轮指南](JEV_PHASE1.zh.md)。

## 部署与验收边界

本轮不需要数据库迁移。部署使用 AWS 正在运行的后端不可变镜像，叠加经过检查的 Jev 新文件及五处小范围业务钩子；未打包本地其他未发布的后端改动。覆盖包按 SHA-256 命名并在启动前验证，独立 Fargate 任务通过后才更新服务。`deploy/jev_backend.py` 保留前一任务版本用于回滚。

- 本地监控器与新增 Jev 测试 **132 项通过**；相关问答、实体提取、审核、检索、聊天、全文回归 **43 项通过**；ruff 检查通过。
- 云端以真实 PAS 论文和索引片段调用全部八项接口，验证无 key 回退及原 RAG 路由不变。审核优先级额外验证了缺少评估名单时的保护路径；补齐镜像漏打包的三份仓库既有边界 CSV，并核对其内容与 Git 版本相同。开放语料库后，数据库原有训练、验证和冻结测试分配仍被保护。
- 合成响应仅用于本地契约测试，未写入生产决策库。真实 Jev 推理、质量收益、概率校准与账单尚未验证，等待用户申请 key。
- 后端任务版本 `paper-attribution-pas-dev-backend:6` 已稳定运行，采集任务 `paper-attribution-dev-author-monitor:9` 退出码 0。公网八项接口全部返回 200；未授权请求返回 401，伪造原文返回 422。两个 CloudFormation 栈更新完成，每日定时任务保持开启。
- 本次采集 OpenAlex 返回 177 条，去重后保持 163 篇和 163 条 PAS 入库回执，新增 0；Slack 已接受本人 DM 的八项概览和 Home 更新。82 位名单保留，81 位已启用，1 位继续等待身份核对。
- AWS 任务版本、采集结果、Slack 回执和最终部署状态见 [机器可读验收记录](review-evidence/jev-eight-workflows-verification.json)。
