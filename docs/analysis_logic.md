# TA回我了：分析逻辑说明

本文档说明当前项目从微信聊天记录到最终报告的底层分析链路。它描述的是代码实际实现，不是产品文案。

## 1. 总体流程

入口在 `server.py`，前端通过本地 HTTP API 驱动完整流程：

1. `/api/setup`：运行 `setup_check.py`，检查 Python、依赖、解密器等本地环境。
2. `/api/discover`：依次运行 `setup_check.py`、`decrypt_wechat.py`、`list_contacts.py`，自动发现微信数据并列出联系人。
3. `/api/extract`：运行 `extract_messages.py`，按联系人从解密后的微信数据库提取消息，生成 `messages.json`。
4. `/api/stats`：运行 `stats_analyzer.py`，基于 `messages.json` 生成统计结果 `stats.json`，同时导出 `chat_history.txt` 给模型分析使用。
5. `/api/analyze`：在 `server.py` 里生成分析 JSON。未启用模型时走本地启发式规则；启用模型时把统计数据和聊天片段发送给 OpenAI / Anthropic / Gemini 兼容接口。
6. `/api/report`：运行 `generate_html_report.py`，把 `stats.json` 和 `analysis.json` 渲染成 HTML 报告，并保存到 `runtime/she-love-me/reports/`。

## 2. 微信消息提取逻辑

实现文件：`runtime/she-love-me/scripts/extract_messages.py`

核心假设基于 WeChat 4.0 数据结构：

- 联系人信息来自 `contact/contact.db`。
- 消息库位于 `message/message_N.db`。
- 每个联系人对应一张消息表，表名为 `Msg_{md5(username)}`。
- `Name2Id` 表用于把 `real_sender_id` 还原为微信 username。
- `WCDB_CT_message_content == 4` 时，消息内容按 zstd 解压。
- `local_type` 被映射为消息类型：文本、图片、语音、视频、表情、链接、通话、撤回、系统消息等。

发送方识别逻辑：

- 如果 `sender_username == own_wxid`，标记为 `me`。
- 如果 `sender_username == contact_username`，标记为 `them`。
- 如果缺少 sender 信息，可能标记为 `unknown`。
- 如果无法完全确定，会根据是否等于联系人 username 做兜底判断。

输出结构：

- `contact_display`：联系人显示名。
- `own_wxid`：当前账号 wxid，无法识别时为 `unknown`。
- `messages`：按时间排序后的消息列表，每条含 `sender`、`content`、`timestamp`、`datetime`、`type` 等字段。

局限：

- 如果 `own_wxid` 或 `Name2Id` 缺失，发送方识别可能不完全准确。
- 图片、语音、视频等非文本内容只保留占位符，不做语义识别。
- 群聊格式只做简单处理，本项目主线仍以单聊分析为目标。

## 3. 统计分析逻辑

实现文件：`runtime/she-love-me/scripts/stats_analyzer.py`

统计脚本只对 `sender` 为 `me` 或 `them` 的消息做分析。文本内容分析只使用 `type == "text"` 的消息。

### 3.1 基础统计

输出在 `stats.basic`：

- 总消息数。
- 你和对方各自消息数。
- 双方消息占比。
- 日期范围。
- 覆盖天数。
- 日均消息数。

### 3.2 对话发起

规则：

- 超过 3 小时没有新消息，视为新一轮对话。
- 每轮对话的第一条消息决定发起方。

输出在 `stats.initiative`：

- `my_starts`：你发起的对话轮数。
- `their_starts`：对方发起的对话轮数。
- `my_start_ratio`：你发起对话的比例。

### 3.3 回复速度

规则：

- 只有发送方发生切换时，才计算回复时间。
- 回复间隔必须大于 10 秒，小于 24 小时。
- 你回复对方的间隔进入 `my_reply_times`。
- 对方回复你的间隔进入 `their_reply_times`。

输出在 `stats.reply_speed`：

- 双方平均回复秒数。
- 双方平均回复时间的人类可读格式。
- `speed_ratio`：对方平均回复时间 / 你的平均回复时间。

### 3.4 连续发送

规则：

- 同一方连续发送多条，直到另一方回复才结束。
- 连续 3 条及以上记为一次“轰炸”。
- 同时记录最大连续发送条数。

输出在 `stats.bombing`：

- `my_bomb_count`、`their_bomb_count`
- `my_max_consecutive`、`their_max_consecutive`

### 3.5 冷淡回复

规则：

- 内容命中 `COLD_WORDS`，如“嗯”“哦”“好”“行”“知道了”等，视为冷淡回复。
- 长度小于等于 2 的文本也视为冷淡回复。

输出在 `stats.cold_response`：

- 双方冷淡回复次数。
- 出现最多的冷淡词。

局限：

- “嗯”“好”等短回复在亲密关系中不一定冷淡，当前规则无法判断语境。

### 3.6 未回复

规则：

- 一方发出消息后，如果对方超过 2 小时才回应，记录为一次长时间未回复。

输出在 `stats.unanswered`。

### 3.7 早安晚安

规则：

- 文本中包含“晚安”“早安”“睡了”“睡觉”等表达时计数。
- 分别统计你和对方主动说早安/晚安的次数。

输出在 `stats.goodnight`。

### 3.8 语言特征

当前脚本统计：

- “我们”等共同体代词。
- “我”等自我代词。
- 模糊词。
- 条件句。
- 正向和负向词。
- 撤回消息。

输出在 `stats.linguistic`。

### 3.9 活跃时间、每日趋势、消息类型

输出包括：

- `active_hours`：按小时统计活跃度。
- `daily_trend`：最近 90 天每日消息数。
- `message_types`：文本、图片、语音等类型分布。

## 4. 三个核心指数

实现函数：`compute_scores(stats)`

### 4.1 主动指数 `simp_index`

越高表示你越主动维系。

加分来源：

- 你的消息占比更高。
- 你发起对话更多。
- 你回复更快。
- 你连续发送较多。
- 你主动说早安/晚安更多。
- 你被长时间未回复较多。

### 4.2 被爱指数 `loved_index`

越高表示对方的主动和投入更明显。

加分来源：

- 对方消息占比更高。
- 对方发起对话更多。
- 对方回复更快。
- 对方平均消息更长。
- 对方主动说早安/晚安更多。
- 对方冷淡回复更少。

### 4.3 冷淡指数 `cold_index`

越高表示对方对你的冷淡信号越强。

加分来源：

- 对方冷淡回复比例高。
- 对方回复速度显著慢于你。
- 你的消息数超过对方 2 倍以上。

## 5. 本地启发式关系判断

实现函数：`server.py -> summarize_stats(stats, contact)`

### 5.1 关系类型

当前阈值：

- `loved_index >= 70` 且对称度 `symmetry >= 7`：判为“相互喜欢”。
- `simp_index >= 72` 且 `loved_index < 45`：判为“深陷单恋”。
- `cold_index >= 65`：判为“名存实亡”。
- 其他情况：判为“暧昧拉锯”。

### 5.2 对称度

公式：

```text
symmetry = max(1, min(10, 10 - int(abs(my_ratio - their_ratio) * 12)))
```

含义：

- 双方消息占比越接近，对称度越高。
- 双方消息占比差距越大，对称度越低。

### 5.3 趋势判断

规则：

- 最近 7 天日均消息数 > 前 7 天的 1.25 倍：升温中。
- 最近 7 天日均消息数 < 前 7 天的 0.65 倍：逐渐降温。
- 其他情况：平稳维持。

### 5.4 风险提示

当前会提示：

- 单向投入风险：对称度过低，或主动指数明显高于被爱指数。
- 连续追问风险：你最大连续发送条数达到较高水平。

### 5.5 其他报告字段

本地启发式会生成：

- 关系阶段。
- 情感不对称描述。
- Sternberg 三角爱情维度的粗略分数。
- Gottman 风险等级。
- 人格画像占位结果。
- 行动建议。
- 关键发现。

这些内容主要由统计指标组合而来，不等于临床心理诊断。

## 6. LLM 深度分析逻辑

实现文件：`server.py`

当 `/api/analyze` 的 `use_llm` 为 true 时：

1. 先用 `summarize_stats()` 生成一个完整 schema 示例。
2. 读取 `chat_history.txt`。
3. 按 `SHE_LOVE_ME_MAX_CHAT_CHARS` 截断聊天记录，默认最多 200000 字符。
4. 调用 `build_llm_prompt()`，把统计数据、schema 示例和聊天记录片段放入提示词。
5. 根据设置选择接口模式：
   - OpenAI 兼容接口：`/chat/completions`
   - Anthropic：`/messages`
   - Gemini：`generateContent`
6. 模型必须返回可解析 JSON。
7. 返回内容写入 `analysis.json`。

提示词要求模型：

- 严格输出 JSON，不输出 Markdown。
- 与 schema 兼容。
- 强心理推断要谨慎，并尽量引用原话。
- 证据不足时写“证据不足”。
- 严重单向投入、痴迷或创伤绑定要进入 `danger_warnings`。

局限：

- 深度分析质量依赖模型和 API 配置。
- 模型可能不完全遵守 JSON 或证据引用要求，所以代码会先做 JSON 解析，但不会自动验证每个心理判断是否真的有原话证据。

## 7. 报告渲染逻辑

实现文件：`runtime/she-love-me/scripts/generate_html_report.py`

输入：

- `stats.json`
- `analysis.json`
- 联系人名称

输出：

- 单个 HTML 报告文件。

报告主要区域：

- 顶部关系结论。
- 三个核心指数。
- 关系成分条。
- 关键统计卡片。
- 双方互动对比。
- 每日趋势、活跃时段、消息类型图表。
- 语言模式。
- 风险提示。
- 关系阶段。
- 情感不对称。
- Sternberg / Gottman 相关卡片。
- 人格画像。
- 行动建议。
- 关键发现。
- 最终结论。

### 7.1 报告底色选择

实现函数：`classify_report_tone(analysis, stats)`

当前逻辑：

- 如果关系文本含“单向”“工具人”“凉”“降温”“危险”“消耗”“高危”“不爱”“止损”“拉扯”等词，或风险等级为高危，使用负向暗场风格。
- 如果 `cold_index >= 55`，或 `simp_index >= 70` 且 `loved_index <= 35`，使用负向暗场风格。
- 如果关系文本含“相互喜欢”“双向”“升温”“稳定”“平稳”“健康”“被爱”“正式确认”“关系维护”等词，或 `loved_index >= 60` 且 `cold_index <= 35`，使用正向风格。
- 其他情况使用中性风格。

报告页面不会再把内部风格名显示给用户。

## 8. 本次发现并修正的问题

`server.py` 的 `summarize_stats()` 里，情感不对称部分原先读取的是旧字段：

```python
initiative.get("my_initiated", 0)
initiative.get("their_initiated", 0)
```

但 `stats_analyzer.py` 实际输出的是：

```python
my_starts
their_starts
```

因此“对话发起”会错误显示为 0。本次已改为读取 `my_starts` 和 `their_starts`。

## 9. 当前结论边界

这个系统现在能稳定完成“本地聊天结构分析”和“模型辅助语义分析”，但需要注意：

- 本地启发式只看统计结构，不能理解反讽、昵称、玩笑、上下文和现实关系背景。
- 冷淡回复规则偏粗糙，短回复可能被误判。
- 非文本消息只保留类型，不分析图片、语音和视频内容。
- 关系判断是描述性和探索性的，不是心理诊断。
- 如果要提高报告质量，优先方向不是继续加 UI，而是给 LLM 分析增加证据校验和关键片段引用约束。
