# TA回我了

本地运行的微信聊天恋爱分析工具。它会在你的电脑上读取微信聊天记录，生成互动统计、潜台词分析、角色档案和结果分析报告。

项目默认只在本机运行，不依赖 Codex、Claude Code、Cursor 或任何 Agent 运行时。

> 当前仓库地址：<https://github.com/Exekiel179/she-love-me-web>

## 项目截图

![首页](docs/screenshots/hero.png)

![分析主线](docs/screenshots/analysis-flow.png)

![恋爱人格](docs/screenshots/personality.png)

![设置](docs/screenshots/settings.png)

## 功能

- 分析主线：读取微信聊天、选择分析对象、生成结果分析报告。
- 角色档案：保存每次分析记录，后续可以回看或删除。
- 恋爱人格：通过问答生成自己的恋爱沟通倾向。
- 设置：配置模型接口、查看最终请求地址、测试连通性、切换 UI 风格。

## 快速开始

```powershell
python server.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

首次使用建议先进入「设置」：

1. 选择接口模式。
2. 填写 BaseURL、模型和 API Key。
3. 点击「测试连通性」。
4. 连通成功后回到「分析主线」读取联系人并生成报告。

## 模型接口

设置页支持三种接口模式：

- OpenAI：请求 `/chat/completions`，适合 OpenAI 兼容中转。
- Anthropic：请求 `/messages`，适合 Anthropic 原生接口。
- Gemini：请求 `/models/{model}:generateContent`。

页面会显示“最终请求地址”，用于确认 BaseURL 拼接是否正确。

如果你的中转服务是 OpenAI 兼容接口，即使模型名称是 Claude，也通常应该选择 `OpenAI` 模式。

### 连通性测试 ≠ 完整分析报告

设置页的「测试连通性」只验证 **最小请求**（例如一句 “Reply with OK only.”），能确认 BaseURL、API Key、网络与接口可达性。

生成报告时，程序会向同一接口发送 **长文本聊天记录 + 统计摘要**，并要求模型输出 **可被解析的单一 JSON**。这一步仍可能失败，常见原因包括：

- **内容安全 / 风控**：完整聊天更容易触发「high risk」等拦截（短测试通常不会）。
- **超时或上下文过长**：默认会截断到环境变量 `SHE_LOVE_ME_MAX_CHAT_CHARS`（默认 60000），必要时自行改小，例如 `24000` 或 `12000`。
- **返回格式**：默认关闭 `response_format: json_object`（环境变量 `SHE_LOVE_ME_OPENAI_JSON_OBJECT=0`），避免部分国内兼容接口报错；若模型仍输出 Markdown 或夹杂解释文字，会导致 JSON 解析失败。

因此：**连通成功只能说明「能连上」，不能保证「长文分析一定成功」。** 若报告顶部出现「模型调用说明」，请看报告中的「接口返回摘要」或后台日志里的具体错误。

### 小米 MiMo（OpenAI 兼容）

官方快速入门见：[首次调用 API](https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call)。MiMo 提供与 OpenAI Chat Completions 兼容的调用方式（如 `POST …/v1/chat/completions`、Bearer 鉴权），与本项目的 **OpenAI 接口模式**一致。

若使用官方文档中的 BaseURL（例如 `https://api.xiaomimimo.com/v1`）或各线路提供的兼容地址，请确保设置页 **最终请求地址** 指向 `…/v1/chat/completions`。国内线路仍可能对 **大批量聊天正文** 做风控，与连通性测试结果不一致属于正常现象；可先减小 `SHE_LOVE_ME_MAX_CHAT_CHARS` 再生成报告。

部分 MiMo 线路（例如 `token-plan-cn.xiaomimimo.com`）在非流式响应里会把模型输出放在 **`reasoning_content`**，而 **`content` 为空**。本项目已在服务端解析时兼容该字段；若仍报错，请到开放平台核对当前模型是否要求开启流式或其它参数。

## 本地配置持久化

模型配置会保存到本机用户目录：

```text
%LOCALAPPDATA%\TAHuiwole\config.json
```

保存内容包括接口模式、BaseURL、模型、API Key，以及分析参数（聊天文本最大字符数、重试聊天字符数、模型回复最大 Token）。这个文件不在项目目录里，也不会提交到 GitHub。

也可以用环境变量覆盖配置：

```powershell
$env:SHE_LOVE_ME_LLM_PROVIDER="openai"
$env:SHE_LOVE_ME_LLM_BASE_URL="https://api.openai.com/v1"
$env:SHE_LOVE_ME_LLM_MODEL="gpt-4.1"
$env:SHE_LOVE_ME_LLM_API_KEY="你的 API Key"
$env:SHE_LOVE_ME_MAX_CHAT_CHARS="60000"
$env:SHE_LOVE_ME_RETRY_CHAT_CHARS="24000"
$env:SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS="12288"
python server.py
```

环境变量优先级高于设置页保存值：如果你在系统里显式设置了同名变量，程序会优先使用环境变量。

## 分析主线时间范围

在「分析主线」选中联系人后，会自动显示该联系人的按日聊天条数，并提供开始/结束日期选择。你可以先看每日分布，再决定分析区间。

- 页面会实时显示「所选范围消息总数」。
- 生成报告时，`/api/stats` 会按所选日期区间计算统计，并据此重新导出 `chat_history.txt` 给大模型分析。
- 若区间内没有消息，会提示调整时间范围。

排查「模型返回不是可解析 JSON」时，可临时打开调试（**终端**会输出 `[LLM-DEBUG]` 摘要，**完整**请求与响应写入 `runtime/she-love-me/data/last_llm_*.txt|json`）：

```powershell
$env:SHE_LOVE_ME_LLM_DEBUG="1"
python server.py
```

若日志里出现 **`finish_reason=length`**，且 `message.content` 为空、只有 **`reasoning_content` 里大段「首先…」说明**，说明 **输出 token 额度在「推理」阶段用尽**，后面的 JSON 没写出来。小米 MiMo 等模型常见此行为。请增大 **`SHE_LOVE_ME_LLM_MAX_OUTPUT_TOKENS`**（程序默认已提高到 12288；若仍被截断可继续加大），或换用非长推理链路的模型。

## 数据位置

运行中产生的数据默认保存在本机：

```text
runtime/she-love-me/data/       聊天记录、统计结果、分析 JSON
runtime/she-love-me/reports/    生成的报告
runtime/she-love-me/archives/   角色档案
```

这些目录已加入 `.gitignore`，不会提交到仓库。

## 注意事项

- Windows 解密微信数据库通常需要管理员权限启动终端和微信。
- 微信需要处于已登录状态。
- 如果启用远程模型分析，聊天片段会发送到你配置的模型服务。
- 大聊天记录可能导致中转服务超时。当前已做输入截断和 504 自动精简重试，后续会继续改成分段摘要流程。见 Issue：<https://github.com/Exekiel179/she-love-me-web/issues/1>

## 开发结构

```text
server.py                       本地 Web/API 服务
web/                            前端界面
web/assets/cursors/             动态鼠标资源
docs/screenshots/               README 截图
runtime/she-love-me/scripts/    微信读取、统计和报告脚本
```
