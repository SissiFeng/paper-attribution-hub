# PAS 云端开发

选择 GitHub Codespaces 作为日常开发环境：同一台远程机器运行 Python、
React、测试数据库和终端，适合前后端联调。Codex 的 VS Code 扩展已列入
开发容器配置；首次使用需登录自己的 Codex 账号。

GitHub 保存代码和已纳入版本控制的研究产物。AWS 继续承载线上 PAS、论文
监控、Slack 通信和生产数据。停止 Codespace 不会停止生产推送。

## 开始开发

1. 从迁移分支创建 Codespace，使用仓库内 `.devcontainer/devcontainer.json`。
   初始化自动安装 Python 3.12、Node 22 和依赖，构建两个前端，并运行监控及
   科研权限相关测试。终端出现 `PAS setup complete` 才算初始化成功。
2. 运行 `bash scripts/cloud/preview.sh`，从 Ports 打开 8877 端口的 `/fixture`。
   保持端口 **Private**。选择示例成员或管理员，可验证论文、Wiki、个人科研
   和管理页面；该预览使用独立 SQLite 和两篇明确标注的合成论文。
3. 编辑后运行 `bash scripts/cloud/check.sh`，再提交并推送代码。预览读取
   构建文件，前端改动后需重新构建并刷新。
4. 用完在 GitHub 中 Stop Codespace。初始实例设置 15 分钟闲置停止；停止后
   仍有存储占用及可能的存储费用，实际额度以 GitHub Billing 为准。

## 数据、凭据和发布边界

- 不提交 `.env`、数据库、临时会话、虚拟环境或 `node_modules`。预览状态在
  `.local/cloud-preview`，可重复生成，不包含线上用户笔记。
- 生产 Slack/API 凭据继续保留在 AWS SSM。默认开发容器不注入生产凭据。
  AWS 运维按需使用本人的 SSO 登录；不能把本地 SSO 缓存复制进镜像或 Git。
- `cloud/**` 分支运行独立验收工作流，不会触发现有 `main` 的 AWS 部署。
  当前迁移只是开发环境迁移，不应覆盖正在运行的生产任务定义或数据库。
- Codex Cloud 也可复用 `scripts/cloud/setup.sh`，但本轮主要交付为 Codespaces。
- 未提交的工作和数据库不是 Codespace 的可靠备份。重要代码及时推送；
  删除本地数据前须核对单独的备份清单和远端校验结果。

验证范围：云端验收覆盖两个前端构建、导航/论文视图契约、作者监控测试、
公开论文目录和个人科研权限测试，不代替所有科研算法的完整回归。

## 2026-10-07 迁移记录

- 私有仓库：`SissiFeng/paper-attribution-hub`；迁移分支：
  `cloud/pas-workspace-2026-10-07`。原有开发状态保存在 `21d6276`，
  Codespaces 远程终端支持补丁为 `2c5b1c8`。没有合并到会自动部署的 `main`。
- GitHub 云端验收：`37644889130`、`37645456851` 均成功，监控测试 165 项、
  论文与科研权限测试 45 项，另有两个前端构建和导航契约检查。
- 独立文件备份（包含本地论文和数据库，不含凭据/依赖/缓存）：
  `s3://paper-attribution-artifacts-dev-247893369214/workspace-backups/20261007T153551Z/workspace.tar.gz`。
  共 3,387 个文件，659,201,259 字节。逐文件清单位于同一路径加
  `.manifest.json`。下载验证的 SHA-256：
  `e4cf353e7cc30331ac9d973120a5be486a5bfc51f6f4774d5e295506e6cab5f0`。

恢复备份时，先以获准的 AWS SSO 身份下载到一个独立目录，验证 SHA-256，
再解压。不要直接覆盖正在开发的 checkout，也不要把其中的本地数据库
替换到生产环境。未来依赖可由 `setup.sh` 重装，Remotion 另运行
`npm ci --prefix remotion`。

云端首次访问 AWS 时运行 `aws configure sso --profile pas-sdl0-dev`，按组织
要求登录既有账号。SSO 起始地址为 `https://d-9d67418437.awsapps.com/start`，
区域为 `ca-central-1`。不要从本机复制凭据缓存。

## 接续开发的上下文

先读 `tools/author-paper-monitor/REVIEW_RESULT.zh.md`、`FRESHNESS.zh.md`、
`MULTIUSER.zh.md` 和 `docs/p0-access-control.zh.md`、
`docs/p1-research-workspace.zh.md`、`docs/p2-research-exploration.zh.md`。
所有原始 PAS 分析页面应保留；公开论文页面复用旧版论文与 Wiki UI；
机构分析仍仅对管理员开放，管理员身份不赋予读取他人私人笔记的权限。

尚待接入的服务：Microsoft 365 共享邮箱需要新增 OAuth/Graph 支持，现有
Scholar 连接器只有只读 IMAP 密码认证，不可直接用于 Exchange Online。
Jev 配置入口已存在，但未配置模型 API key。不要把这两项写成已经启用。

迁移前诊断：多伦多时间 10 月 7 日 00:18、04:18、08:18 的三次监控均新增
0 篇；最后一轮无错误、无入库积压、无待发送或失败回执，用户订阅开启。
这是当时的运行快照，后续问题必须重新查询线上记录。
