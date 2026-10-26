# 定期爬取部署说明

## 文件说明

| 文件 | 作用 |
|------|------|
| `crawler/deploy_schedule.py` | 一键部署脚本，创建 Windows 定时任务 |
| `crawler/auto_crawl.py` | 每日自动运行的爬取逻辑（由定时任务调用） |
| `crawler/auto_crawl.bat` | 部署后自动生成的启动脚本（无需手动创建） |

## 快速部署

在项目根目录执行：

```bash
python crawler\deploy_schedule.py
```

部署完成后，Windows 任务计划会在每天 10:00 自动运行。

## 每日执行流程

```
定时任务触发 (每天10:00)
    │
    ├── 1. 运行 opinion_monitor.py（舆情监测）
    │      检测三重信号：评论量异常 / 关键词突增 / 情感骤变
    │
    ├── 2. 读取监测结果，判断是否需要爬取
    │      热点期间 → 每天爬
    │      常态运行 → 3天一次
    │      冷清期间 → 7天一次
    │
    ├── 3. 如需爬取 → 运行 run_scrapers.py
    │      NGA + TapTap 爬虫，爬完直接入库
    │
    └── 4. 记录日志
           crawler/auto_crawl.log    (文本日志)
           crawler/auto_crawl_log.json (爬取记录)
```

## 管理命令

```bash
# 修改运行时间（如改为下午2点）
python crawler\deploy_schedule.py --time 14:00

# 手动触发一次（立即执行）
schtasks /Run /TN GamerPulse_AutoCrawl

# 查看任务状态
schtasks /Query /TN GamerPulse_AutoCrawl

# 卸载定时任务
python crawler\deploy_schedule.py --uninstall
```

## 首次使用前提

1. 已安装 Python 3.10+（项目 `.venv` 优先）
2. 已安装项目依赖：`pip install -r requirements.txt`
3. 已配置 `.env` 文件（含 DeepSeek API Key）
4. 已配置 `crawler/nga_cookie.json`（NGA 爬虫需要）

## 注意事项

- 部署脚本需要 Windows 管理员权限，如创建失败请以管理员身份运行命令行
- 定时任务在电脑关机时不会执行，开机后也不会自动补执行
- 日志文件会持续增长，建议定期清理 `auto_crawl.log`
- 爬取记录 `auto_crawl_log.json` 自动保留最近 30 条
