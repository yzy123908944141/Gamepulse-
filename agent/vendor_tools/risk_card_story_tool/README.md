# 剧情强相关风险筛选与摘要工具

脚本：`tools/compress_risk_titles.py`

> 文件名沿用旧版，但当前功能已经不是“去重”，而是“从风险项中筛选剧情强相关风险，并根据 description 总结为需注意的风险”。

## 数据来源

读取：

`D:\program\two-dimensional_game\agent.db`

表：

`analysis_results`

字段：

`risk_warnings`

该字段是 JSON 文本，每条风险一般包含：

- `risk_level`
- `title`
- `description`

## 当前 AI 调用逻辑

1. 读取每条 `risk_warnings`。
2. 先让大模型只根据 `title` 判断是否与剧情强相关。
3. 与剧情强相关的 title 包括：剧情、角色塑造、角色关系、文案、叙事节奏、主线/支线、设定冲突、角色崩坏、玩家代入等。
4. 不强相关的 title 会被忽略，例如抽卡、性能优化、设备适配、资源获取、系统养成、活动奖励等。
5. 对被选中的风险，再读取对应 `description`。
6. 大模型输出“需注意的风险”摘要。

## 无 API 检查

```powershell
cd D:\program\two-dimensional_game
python .\tools\compress_risk_titles.py
```

输出目录：

`D:\program\two-dimensional_game\record\story_risk_summary`

会生成：

- `story_risk_items_*.json/csv`：抽取出的原始风险项
- `story_risk_report_*.json`：数量、乱码检测、样例标题

## 使用 DeepSeek API

```powershell
cd D:\program\two-dimensional_game

$env:LLM_API_KEY="你的 DeepSeek API Key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"

python .\tools\compress_risk_titles.py --run-api
```

生成重点文件：

- `story_risk_summary_*.json`
- `story_risk_summary_*.csv`

## 写入数据库新表

默认不会修改原表。如果确认摘要质量可用，再执行：

```powershell
python .\tools\compress_risk_titles.py --run-api --write-db
```

会创建/刷新新表：

`story_risk_summary`

字段：

- `analysis_id`
- `character_id`
- `title`
- `story_relevance`
- `risk_summary`
- `evidence`
- `created_at`

不会覆盖 `analysis_results` 原始数据。

## 测试小样本

为了省 token，可以先只跑前 20 条：

```powershell
python .\tools\compress_risk_titles.py --run-api --max-items 20
```
