# GamePulse 舆情预处理组件

本目录集成自 `D:/program/data`，用于在舆情报告和角色风险展示之前完成评论预处理。

## 目录

- `crawler/`：评论采集与 CSV 清洗入库组件。
- `analysis/`：评论 AI 情绪分析、角色关联识别、角色舆情聚合组件。
- `raw_data.db`：GamePulse 当前原始评论与角色库。
- `agent.db`：GamePulse 当前分析结果库。

## 已完成的集成适配

- 数据库路径统一改为项目内部：
  - `D:/program/GamePulse/data/raw_data.db`
  - `D:/program/GamePulse/data/agent.db`
- 兼容当前已有表结构：
  - `raw_comments` 没有 `is_analysis` 时，自动通过 `analysis_comments.raw_comment_id` 判断是否已处理。
  - `analysis_comments` 缺少 `reason`、`decision_source` 时会自动补充可选列。
  - `analysis_results` 使用当前前端需要的 `associated_comment_ids` 字段。
- 新增统一 Tool：`tools.sentiment_preprocess_tool.run_sentiment_preprocess`。
- 新增后端接口：`POST /api/sentiment/preprocess`。

## Python 调用

```python
from tools.sentiment_preprocess_tool import run_sentiment_preprocess

print(run_sentiment_preprocess.invoke({
    "run_csv_import": False,
    "run_comment_analysis": True,
    "run_aggregation": True,
    "limit": 20,
    "clear_existing": False,
    "character_id": None,
}))
```

## 后端接口调用

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sentiment/preprocess" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"run_comment_analysis":false,"run_aggregation":false,"limit":1}'
```

## 参数说明

- `run_csv_import`：是否从 `crawler/data/*.csv` 清洗并导入 `raw_comments`。
- `run_comment_analysis`：是否调用 AI 分析未处理评论，写入 `analysis_comments` 和 `analysis_characters`。
- `run_aggregation`：是否对角色相关评论做聚合诊断，写入 `analysis_results`。
- `limit`：单次评论 AI 分析数量，建议测试时设置较小值。
- `clear_existing`：是否清空已有分析表后重跑，谨慎使用。
- `character_id`：聚合指定角色；为空时聚合所有已识别到的角色。

## 注意

评论 AI 分析和角色聚合会调用模型 API。测试时建议先用小 `limit`，确认结果后再扩大处理数量。
