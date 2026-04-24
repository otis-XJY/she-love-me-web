# 她爱你吗 Web

这是 `she-love-me` skill 的独立本地 Web 包装版，不依赖 Codex、Claude Code、Cursor 或任何 Agent 运行时。

## 运行

```powershell
cd F:\Projects\she-love-me-web
python server.py
```

打开：

```text
http://127.0.0.1:8765
```

点击页面里的「一键识别微信」会自动执行：

```text
检查 Python / 微信进程
  -> 自动准备 wechat-decrypt
  -> 从正在登录的微信识别并解密数据库
  -> 扫描联系人和消息数量
  -> 进入联系人选择
```

## 可选：启用 OpenAI 兼容模型分析

不配置模型时，Web 项目会使用本地统计数据生成一份启发式 `analysis.json`，可以直接生成 HTML 报告。

如果你想让“大模型深度分析”也在 Web 里完成，设置这些环境变量：

```powershell
$env:SHE_LOVE_ME_LLM_BASE_URL="https://api.openai.com/v1"
$env:SHE_LOVE_ME_LLM_API_KEY="你的 API Key"
$env:SHE_LOVE_ME_LLM_MODEL="gpt-4.1"
python server.py
```

任何兼容 `/chat/completions` 的服务都可以使用。这个项目不会调用 Codex 或 Claude Code。

## 目录

```text
server.py                     本地 Web/API 服务
web/                          前端界面
runtime/she-love-me/scripts/   从 skill 复制出的原始处理脚本
runtime/she-love-me/vendor/    wechat-decrypt 会被自动 clone 到这里
runtime/she-love-me/data/      messages / stats / analysis / chat_history
runtime/she-love-me/reports/   生成的 HTML 报告
```

## 注意

- Windows 解密微信数据库通常需要管理员权限启动终端和微信。
- 数据默认只在本机 `runtime/she-love-me/data` 和 `runtime/she-love-me/reports` 下流转。
- 如果启用远程 LLM，聊天记录片段会按你的配置发送给对应模型服务。
