# 风险卡剧情风险筛选与摘要工具运行示例
# 先把 agent.db 放到项目根目录，或用 --db 指定数据库路径。

$env:LLM_API_KEY="填写你的 DeepSeek API Key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"

python .\compress_risk_titles.py --db .\agent.db --run-api

# 确认结果可用后，如需写入数据库新表：
# python .\compress_risk_titles.py --db .\agent.db --run-api --write-db
