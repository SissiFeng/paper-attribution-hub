# Jev 第一轮：后台建议与人工对照

八项扩展已接入，最新运行边界和入口见 [JEV_ALL.zh.md](JEV_ALL.zh.md)。下方第一轮验收是历史记录。

范围：周报优先级评分、判断是否需要阅读全文。当前模式只有 off/shadow；不调整正式 Slack 顺序、不漏存论文、不自动下载全文，也不修改科学分类。

1. 接入官方固定版本 API，验证完整概率分布、选项、用量；验证：契约、超时、错误响应和缺失凭据测试。
2. 为每份论文元数据与问题版本保存独立记录，导出建议顺序、原始顺序、人工标注表和对照报告；验证：缓存、输入变更、标签校验、排序/全文判断指标。
3. AWS 加密凭据入口与每日限量后台评估；Slack 增加本人可用的评估预览；验证：正常监控不受失败影响、真实 AWS 运行、未配置时明确提示。

用户尚未申请 API key。因此当前能验收开发、模拟契约、真实论文离线导出和 AWS 配置路径；真实 Jev 输出、费用及领域校准必须等配置凭据后实测，不以模拟结果代替。

## 连接方式

从 [TypeSafe 官方平台](https://typesafe.ai/) 申请 API key 后，在项目根目录的终端运行：

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py
```

程序隐藏输入，不把 key 放进命令参数、聊天或文件。它先读取现有监测库中的一篇公开论文，用标题和摘要做一次真实接口检查，只有结构校验成功才写入 AWS SSM SecureString：`/paper-attribution-dev-author-monitor/jev`。这次调用只能证明接口可用，不能证明判断正确。AWS SSO 需要有效登录；连接或权限失败不会保存未经验证的新 key。

已部署的 shadow 任务下一次每天 12:17 UTC 运行时自动读取配置，无需重新部署。只查询配置状态（不请求 Jev）与复测已保存 key（请求一次 Jev）：

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --status
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --check
```

暂未配置时，正常作者监测、PAS 入库、每周私信继续；`/papers status` 和 `/papers review` 显示等待 key。也可在 AC Papers 的 Home 页点击 **Review Jev suggestions**。预览只给绑定的操作者发送私信，即使命令在频道中输入。无需重新申请 Slack scope。

## 本轮实现

- 固定 `jev-1.13.0` 与 `ac-triage-v1` 问题版本，直接调用 TypeSafe `/v1/systemone`；核对类型、模型名、概率分布、分数与选项一致性。用量缺失明确保留未知，不记成零成本。
- 两个问题共享公开研究方向、标题和摘要；摘要最多 12,000 字符，保留截断标记。不发送 Slack 用户信息、作者身份、私密笔记或数据库凭据。没有向模型提供全文。
- 0–4 分阅读优先级；后续动作仅有 `metadata_sufficient`、`fulltext_needed`、`manual_review`。这些是阅读建议，不直接触发下载、分类或删除。
- 扩展后 AWS 的全部八项流程共享每 UTC 日 20 次尝试额度；本评分器每轮最多 8 次调用、45 秒时间预算，单次 HTTP 超时最多 8 秒。本地独立状态库保持自己的限额。配置工具的单次检查不计入采集任务额度。DNS/操作系统调度和 S3 检查点会有额外耗时，ECS 整个任务仍有 25 分钟硬上限。
- API 不自动重试；第一次错误结束本轮评估，错误或中断至少 24 小时后才能重试同一输入。版本、方向或论文元数据变化会形成新记录；相同输入成功后复用缓存。
- 决策先写入独立 `jev_decisions` 表并随状态库检查点保存至 S3。Jev 在正式发送流程之后运行，不改变论文投递状态。失败不会把已完成的入库、发送操作重做。
- 私信预览取已评分子集的前 3 篇，并注明已评分/总数、快照日期及实验性质；不会把未评分论文当成不相关。正式周报保持原有行为。
- 每篇保存完整问题、输入指纹、模型、概率、token 用量、延迟及成功请求的估算成本。估算按开发时官方输入价格计算，失败调用和配置检查不在累计值内，不能替代账单。

## 人工对照与评估

每轮在私有 S3 的 `author-monitor/production/outbox/` 输出 `jev-shadow.json` 和空白标注模板 `jev-labels.csv`。下载副本到本地再标注；云端 CSV 是每日重新生成的空白模板，不能当成人工工作文件。不要把本地编辑的状态库上传回生产。

单独取一份状态库快照，也可离线导出：

```bash
cd tools/author-paper-monitor
JEV_MODE=shadow ../../backend/.venv/bin/python -m paper_monitor.jev_report \
  --db /absolute/path/state-copy.db --out /absolute/path/jev-review
```

如果配置了自定义 `JEV_FOCUS`，离线导出须使用相同方向，否则旧决策不会被当作当前结果。导出程序不覆盖已有的本地 `jev-labels.csv`；新增论文或方向变化时，请选新的输出目录，保留旧标注。

`jev-labels.csv` 故意不展示模型预测，避免人工评分被锚定。先以相同研究方向独立标注：

| 字段 | 人工标签 |
| --- | --- |
| priority | 0 无关；1 周边背景；2 有用的相邻方法/背景；3 本周值得阅读的直接相关研究；4 可具体采用的方法或结果 |
| next_step | `metadata_sufficient`：元数据足以初筛；`fulltext_needed`：有关联但需看全文中的细节；`manual_review`：连主题或文献性质都不确定 |

留空表示未标注。不要修改 `paper_id` 或 `input_hash`。运行：

```bash
JEV_MODE=shadow ../../backend/.venv/bin/python -m paper_monitor.jev_report \
  --db /absolute/path/state-copy.db --out /absolute/path/jev-review \
  --labels /absolute/path/jev-review/jev-labels.csv
```

生成 `jev-evaluation.json`：优先级 MAE、按发布日期倒序基准与建议排序的 NDCG@10、相关论文 recall@10、后续动作准确率和多类别 Brier、误判“不需全文”的比例、人工复核比例、延迟与估算成本。排序指标只在**已有人工标签且模型成功输出**的子集上比较；样本数和范围同时输出。空标签或无预测时，不会生成虚假的准确率。

旧输入的标签、重复 ID、越界标签会报错。概率只是待验证预测；即使接口的 `confidence` 很高，也不能称为 AC 语料上的准确率。需要有代表性的独立标注与留出集，再决定是否进入下一轮；本轮没有自动启用正式排序或过滤的开关。

## 接口依据

2026-10-05 核对了官方 [HTTP API](https://docs.typesafe.ai/api)、[SDK 响应结构](https://docs.typesafe.ai/sdk/python/api/types/responses)、[模型说明](https://docs.typesafe.ai/models) 和 [confidence 定义](https://docs.typesafe.ai/confidence)。本地 API 响应测试为按这些文档构造的合成样例，明确不属于真实推理或质量评测。

## 本轮验收记录（2026-10-05）

- 本地 88 项测试通过，ruff E/F/W/B 检查通过。包括配置前不调用、失败后监控正常、缓存、每日额度、输入变化重新评估、概率异常、标注指标、仅本人私信、IAM 凭据隔离。
- 两个 CloudFormation 栈均为 `UPDATE_COMPLETE`；采集任务修订版 `paper-attribution-dev-author-monitor:8`，真实执行退出码 0，每日计划保持开启。
- OpenAlex 返回 177 条记录，去重后仍为 163 篇历史基线，新增 0 篇；163 条 PAS 入库回执完整。Jev 状态 `needs_configuration`，尝试数 0，评分数 0。
- 已导出真实 163 篇论文的空白标注模板和待评估报告；没有生成示例评分混入生产。
- 对线上签名 HTTP 入口发起 `review` 与 `home` 验收请求，SQS/Lambda 工作均完成，Slack API 接受了本人 DM 的待配置提示与 Home 更新。没有发到组频道。
- 尚未验证：真实 Jev 响应、真实用量和时延、排序收益及领域校准。用户尚未申请 key，本轮按此边界验收。

机器可读证据：[jev-phase1-verification.json](review-evidence/jev-phase1-verification.json)。
