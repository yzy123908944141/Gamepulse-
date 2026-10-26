# GamerPulse 黄白 Agent 前端快速部署包

这是 GamerPulse 当前黄白工业风前端版本，面向游戏项目的角色风险分析、角色资料检索和 Agent 情报助手演示。页面已移除社区页功能，当前保留「角色」与「助手」两个主页面。

## 版本说明

- 包名：frontend_yellow_white_fastapi_package_20260729
- 前端默认端口：5192
- FastAPI 默认联调端口：8001
- 美术风格：黄白工业风 / Endfield 风格参考 / 黑线框与高亮黄色交互
- 数据策略：优先请求 FastAPI，后端不可用时使用本地 mock 数据兜底

## 目录结构

```text
frontend_yellow_white_fastapi_package_20260729/
├─ index.html              # 页面入口
├─ app.js                  # 前端交互、页面切换、FastAPI 请求逻辑
├─ mockData.js             # 本地兜底角色、风险、关键词和演示数据
├─ styles.css              # 原基础样式
├─ yellow-white.css        # 当前黄白工业风覆盖样式
├─ server.mjs              # 本地静态文件服务器
├─ fastapi_bridge.py       # 简易 FastAPI 数据桥接服务
├─ package.json            # npm 启动脚本
└─ assets/characters/      # 角色立绘资源
```

## 快速启动前端

解压后进入目录：

```powershell
cd D:\program\two-dimensional_game\deploy\frontend_yellow_white_fastapi_package_20260729
npm run start
```

浏览器打开：

```text
http://127.0.0.1:5192/?api=http://127.0.0.1:8001
```

也可以使用：

```powershell
npm run dev
```

## 启动 FastAPI 桥接服务

如果需要读取本地数据库中的角色诊断、关键词、风险警告和相关评论，先启动桥接服务：

```powershell
cd D:\program\two-dimensional_game\deploy\frontend_yellow_white_fastapi_package_20260729
python -m uvicorn fastapi_bridge:app --host 127.0.0.1 --port 8001
```

然后打开前端：

```text
http://127.0.0.1:5192/?api=http://127.0.0.1:8001
```

如果没有启动 FastAPI，页面仍会使用 `mockData.js` 中的本地演示数据，适合纯前端展示。

## 数据库位置说明

`fastapi_bridge.py` 会优先尝试读取项目根目录附近的数据库文件：

- `raw_data.db`：原始评论、平台、链接等数据
- `agent.db`：角色分析结果，包括三项分数、风险警告和关键词

如果部署到其他电脑，需要把数据库文件放到桥接脚本可以找到的位置，或根据实际路径修改 `fastapi_bridge.py` 中的数据库定位逻辑。

## 当前已实现功能

### 角色页面

- 角色目录按大版本、小版本、具体角色分组展示。
- 支持角色名搜索，输入角色名后点击「跳转」或按 Enter 定位角色。
- 点击角色后自动回到页面顶部，方便查看角色详情。
- 展示角色立绘，并针对网页尺寸做了固定展示区域和边框适配。
- 展示三项评分：`character`、`gameplay`、`systempain`。
- 展示风险警告，格式为「风险级别 - 标题」，点击后展开具体说明。
- 展示关键词，格式为「关键词 - 权重 - 评价偏向」。
- 支持「查看相关评论」，按平台、内容和跳转链接展示评论。
- 新增个人故事栏，用于展示角色故事文本；暂无数据时显示空状态。

### 助手页面

- 顶部导航保留「角色 / 助手」。
- 助手页标题已从 Copilot 调整为 Agent。
- 使用黄白工业风 UI，包含左侧可悬浮展开的插件栏。
- 对话区域支持输入问题并显示前端演示回复。
- Agent Pipeline 会动态展示工作流程：接收问题、识别意图、调取上下文、风险推理、生成回复。
- 预留后续接入真实 FastAPI 聊天接口的位置。

### 网络与演示兜底

- FastAPI 请求失败时会显示网络友情提示。
- 后端不可用时，角色页仍可使用本地 mock 数据展示。
- 支持报告导出按钮，后端可用时可接入真实导出接口。

## 已接入或预留接口

- `GET /health`：健康检查
- `GET /api/diagnosis?character_id=角色ID`：读取角色诊断结果
- `GET /api/comments/trace?ids=评论ID列表`：读取相关评论
- `GET /api/report/export?character_id=角色ID&days=30`：导出报告

## 常见问题

### npm run start 提示找不到 package.json

请确认当前命令行目录就是解压后的包目录，并且该目录下存在 `package.json`。

### 页面能打开但没有真实数据

通常是 FastAPI 桥接服务没有启动，或数据库文件路径不正确。可以先只看前端 mock 演示，再检查 `raw_data.db` 与 `agent.db` 的位置。

### 图片导致包体积较大

正常。该前端包的主要体积来自 `assets/characters` 中的角色立绘图片。

## 建议演示流程

1. 启动 FastAPI 桥接服务。
2. 启动前端静态服务。
3. 打开角色页，搜索一个角色并查看立绘、评分、风险、关键词和个人故事。
4. 点击「查看相关评论」检查评论追溯弹窗。
5. 切换到助手页，输入问题，观察 Agent Pipeline 动态流程。

## GamePulse 接入说明

该黄白前端已接入 `D:\program\GamePulse` 的总控 Agent：

- GamePulse 后端会将本目录挂载到 `GET /frontend/`。
- 助手页调用 `POST /sessions` 创建会话。
- 助手页调用 `POST /chat/stream` 获取实时 Agent / Tool 调用链路。
- 最终回复下方显示 `called_agents` 与 `called_tools` 汇总。

推荐启动：

```powershell
cd D:\program\GamePulse
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:OPENAI_API_KEY=$env:DEEPSEEK_API_KEY
.\run_gamepulse_frontend.ps1
```

访问：

```text
http://127.0.0.1:8000/frontend/
```
