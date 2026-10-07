# P1：从论文通知到小组证据阅读

入口：[PAS 主系统](https://d1ai8ldqsh81fz.cloudfront.net/)。Slack 的 **Open in PAS** 直接进入 `/papers/<论文ID>`；旧 `/reading/?paper=…` 和 DOI 链接自动定位同一文章，空 `/reading/` 回到主系统。科研工具位于 **My research**。

原有页面的设计、组件和网址继续保留，侧栏对所有身份显示完整的 Research、Analytics、Network、Team、Operations 分组，不再压缩为一个 **Admin analytics** 入口。受限入口显示锁标记；点击后在原地址完成权限检查。原论文归属表格、筛选器和审核抽屉在固定地址 `/attribution`，管理员首页也仍使用原页面。`/papers` 是供所有人浏览的公开书目入口。窄屏可点击 **Menu** 展开菜单名称。

页面保留检查：`cd frontend && npm run check:navigation`。检查 29 个原页面组件的路由连接、管理员原首页、未登录时的完整导航和 CloudFront 路由。个人功能作为补充入口，不应替换旧工作台；如后续隔离功能未通过验收，应暂停该新增功能而保留旧页面和既有权限。

Papers 复用原有 `PaperReviewPage`、`FilterBar`、`PaperTable`、`EvidencePanel` 和 `WikiPanel` 的只读模式，保留标题/摘要搜索、年份/置信度/分类筛选、排序与详情抽屉。`/papers/<id>` 同样显示原 Evidence / Wiki 标签，可继续进入 Markdown 和个人研究工具。管理员 `/attribution` 保留完整审核功能。

共享阅读使用 `/catalog/paper-view`、`/catalog/papers/<id>/view`、`/catalog/papers/<id>/wiki` 的明确字段集合。Wiki 重用原编译器的论文章节生成逻辑，但只输出共享章节；GET 不修改原 Wiki、不调用生成模型、不读取私人聊天归档。审核备注、原始检索记录和私人笔记不会返回，人工上传的未公开稿件仍不进入公共列表。机构分析、审核写入和 Wiki 重编译接口继续限制为 admin。`npm run check:paper-view` 验证只读模式和原管理操作的区别。

2026-10-06 共享页面发布验收：后端 `paper-attribution-pas-dev-backend:15` 已稳定运行。隔离 canary 验证 5 篇真实论文的共享 Wiki、三种身份的权限边界和原 P1 的 78 项研究流程检查；临时记录已回滚。正式 CloudFront 的 25 项只读接口检查通过，7 个前端文件的 HTTPS SHA-256 与构建一致，缓存失效完成。浏览器实测论文搜索、原详情抽屉、Wiki 及主系统文章链接。线上样本尚无分类，分类字段和私密内容过滤另由本地测试覆盖。首次 canary 发现旧镜像缺少 Wiki 版本常量，修复并补充回归后才晋升；失败候选未进入服务。证据：`tools/author-paper-monitor/review-evidence/shared-paper-view-verification.json`。

文章公开书目信息（标题、摘要、作者、期刊、关键词）无需登录即可浏览；内部上传稿件不自动公开。原始全文、Markdown、收藏、笔记、问答和项目仍需要本人身份。点击个人操作时在当前文章上打开登录弹窗，不丢失文章地址。机构对比、归属分析、报告和静态分析数据继续要求 admin；管理员身份也不能读取别人的私有笔记或对话。

登录弹窗中点 **Connect with AC Papers**，复制 `/papers login …` 命令到 **AC Papers 私聊**并发送，原 PAS 标签页会自动完成登录。仅打开 Slack 不会完成身份确认。可使用已登录的 Slack 桌面或手机应用。命令五分钟有效；未登录状态不运行已登录会话的轮询，避免正常的 401 取消待确认的登录。切换身份或论文时卸载旧页面，清除原来的私有内容。

部署：`deploy/unified_frontend.py` 发布主系统和科研组件，`deploy/research_aws.py` 发布经 canary 验证的后端。旧主系统快照仍在 `protected-legacy/`，不会通过放开该路径来恢复主界面。公开静态资源仅为构建后的 JS/CSS，报告 HTML/JSON 仍经管理员 API 读取。Slack 和定时监控的卡片链接模块已同步更新，不重发历史消息。

## 可以做什么

- **原文定位**：问答引用、比较表摘录可以打开具体原文并高亮引用。显示来源段落、存在时的页码；摘要来源单独标注。Markdown 查看、原文件校验和下载继续可用。
- **段落批注**：选中原文后保存高亮和笔记，默认仅本人可见；可以编辑或删除。记录来源版本和精确字符位置。原文改变后会提示版本不一致，不把旧引用强行定位到新文本。
- **证据比较表**：选择 2–6 篇论文，自定义最多 8 个比较维度。默认材料、方法、条件、基线、结果和局限。系统寻找候选摘录，逐格保留出处和单位；没有匹配证据时明确显示未知。研究者可以添加自己的解读，也可从已保存的批注补充证据。
- **项目资料夹**：围绕研究问题收集论文、比较表、批注和讨论。新项目默认私人，创建人可以明确增删成员。
- **选择分享**：私人批注、比较表、聊天消息均可单独复制到项目。复制聊天只包含勾选消息，并去掉私人页面上下文；原始记录继续私人。项目的论文列表不会带入个人收藏笔记。
- **模型状态**：页面显示生成模型是否已配置。没有凭据时返回有定位链接的原文证据；生成调用失败、回答没有引用或引用越界时回到原文模式。引用编号检查不等于科学结论得到支持。

没有新增 Scholar 抓取或改变监控频率。Slack 继续负责论文预览和进入 PAS；本轮不会向同事发送测试消息。

## 同事试用步骤

1. 从 Slack 论文卡片打开 PAS，完成自己的 Slack 登录。
2. 点 **My research & projects →**，填项目名称和研究问题，创建私人项目。
3. 从左侧打开论文，用 **Add paper to project** 收集所需论文。
4. 在论文摘要或 Source text 中打开 **Annotate abstract / Locate & annotate passage**。选中文字并写批注，点 **Save privately**。
5. 选择 2–6 篇论文，点 **Compare**。点击 **Locate passage** 回到原文；用 **Add interpretation** 记录判断。可从 **Add a saved passage** 补充手动核实过的摘录。
6. 把选定批注和比较表复制到项目。目标项目需先包含相应论文。
7. 项目创建人用 **Manage project members** 选择已登录的同事。新成员可以看到项目全部已有内容，私人空间不受影响。
8. 在私人讨论里用 **Copy selected to project** 选择消息，或者在项目里勾选论文发起新讨论。
9. 复制项目链接，自己发到 Slack 小群。同事必须登录且在项目名单中。Slack 频道成员资格和链接本身都不会授予 PAS 权限。
10. 移除一个成员后，该成员的项目、表格、批注和历史讨论接口均拒绝访问。已打开网页会在刷新、重新聚焦或下一次权限轮询时移除相关视图；已经阅读或保存的副本不能收回。

项目成员可以添加论文、创建自己的批注/表格和参与讨论；只有项目创建人能调整成员或移除资料夹中的论文。批注和比较表仅创建人可编辑。移除资料夹中的论文不会删除已经保存的证据成果。

## 权限与证据边界

共同论文语料仍向已验证的工作区成员开放。机构对比、内部 attribution 接口、导出和静态报告继续由 P0 admin 权限保护。

私人记录按用户授权，项目记录按每次请求的项目成员授权。admin 身份不绕过私人或项目权限。撤销项目成员资格后，即便该成员创建过项目讨论，也不能读取它。项目讨论没有个人所有者授权，旧 P0 代码回退后会拒绝这些讨论，而不是恢复旧创建者的访问。

比较表自动生成的是**候选原文摘录**，不是模型核验过的结构化指标或自动排行榜。人工解读会单独标注。不同电流密度、电解液、负载、温度、iR 补偿和基线可能使数值不可比。“没检索到”和“论文没有报告”不等价。没有全文的论文仅使用已有摘要；不会声称已经读完整篇。

来源文本与 HTML 作为普通文本渲染。批注使用 Unicode 字符位置及 SHA-256 版本，服务端核对引用必须与指定论文的指定段落完全一致。问答仅检索公开论文原文/摘要，排除 attribution 注解；私人内容不会进入共享检索索引。

## 生成模型

本轮 AWS 验收确认当前仍为 `evidence_only`。生成服务已经接入 Anthropic/Kimi，并具备来源编号检查、超时及原文回退；真实生成模型验收需要有效凭据。未配置时不会产生该模型的 API 费用；AWS 运行费用仍存在。

管理员在本机使用隐藏输入，或指定已有 AWS SSM SecureString：

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_reading_model.py --provider anthropic
# 或：
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_reading_model.py \
  --provider kimi --parameter /your/encrypted/parameter
```

不要将密钥发到 Slack、聊天或网页。配置脚本只更新当前后端的模型配置，保留 P1 程序包。配置后应确认 ECS 稳定，再用真实论文问答检查引用是否支持结论。供应商按调用收费；Jev key 不能代替生成模型 key。

## 开发、迁移与验收

- 新表：`research_projects`、`research_project_members`、`research_project_papers`、`research_project_discussions`、`research_annotations`、`research_comparisons`。
- 正常迁移：Alembic `0025`；云端旧库采用限定六张表的增量创建，检查部分/不兼容结构并拒绝继续。没有把无关的旧版本迁移标为完成。
- 增量部署：`deploy/research_aws.py --apply` 启动真实数据 canary，成功后 `--promote` 切换服务。基于保存的 P0 不可变包更新限定文件，校验 SHA-256，保留回退版本和全部已有数据。
- 相关回归：496 项通过；项目权限/回退保护修改后再次通过针对性套件。
- 候选版本在真实 PostgreSQL 上：20 篇论文、10 张比较表、152 段逐字引用位置核对，78 项请求检查。P0 权限及原始 Markdown 验收同时通过，临时记录已回滚。
- 浏览器：独立 HTTPS 环境，两名临时用户和明确标记的论文测试数据，覆盖完整操作流程和移动宽度；不把这些测试数据当成科研证据。
- 线上 HTTPS 最终结果见 `tools/author-paper-monitor/review-evidence/p1-verification.json`。

本轮没有安装一整套第三方科研平台，也没有把 PaperQA、Docling 等项目的论文成绩当作本系统成绩。生成式解读的科学质量、复杂 PDF 表格解析和真实同事的多人使用体验仍需分别验证。

最终线上验收：后端 `paper-attribution-pas-dev-backend:12` 已稳定运行，原机构服务仍为 `paper-attribution-dev-institution:10`。正式 CloudFront HTTPS 的 78 项流程检查与 6 项额外权限检查通过；20 篇真实论文的 152 段引用逐字匹配。三个临时身份及其研究记录已清理。前端三份发布文件的 HTTPS SHA-256 与本地构建相同，缓存失效已完成。没有提交/推送 Git，也没有向同事发出测试消息。

## 重跑浏览器验收

浏览器测试代码保存在 `frontend/scripts/reading_browser_check.cjs` 和 `backend/tests/browser/research_server.py`。运行器创建独立临时 SQLite 数据库、HTTPS 证书和两位测试用户，禁用付费生成 key，退出时清理数据库及凭据文件。需要本机已有 Playwright Node 包和浏览器，不自动下载。

```bash
cd frontend && npm run build:reading
cd ..
backend/.venv/bin/python tools/author-paper-monitor/deploy/check_research_browser.py \
  --playwright-module /path/to/node_modules/playwright \
  --browser-executable /path/to/chrome-headless-shell
```

13 项浏览器检查均通过。截图使用明确标记的论文测试数据；真实论文验收另见线上记录。生成适配器的成功/失败路径使用模拟 SDK 测试，不替代有效凭据下的真实模型调用。
