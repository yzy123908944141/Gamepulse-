# 本地数据与美术资源接入指南

公开仓库只提供代码、配置模板和文档，**不包含**评论数据库、原始评论 CSV、Chroma 索引、角色立绘、模型文件、API Key 或爬虫 Cookie。取得有权使用的数据与图片后，请在本机按下列步骤接入。不要把这些文件重新提交到公开仓库。

以下路径均相对于项目根目录，即 `main.py` 和 `启动GamePulse.bat` 所在目录。

## 1. 两份 SQLite 数据库

将有效的数据库放在：

```text
data/raw_data.db
data/agent.db
```

- `raw_data.db`：至少需要 `characters`、`raw_comments` 等表。角色接口读取 `characters.id/name/version/background_lore/personality_setting/combat_style`；评论追溯接口读取 `raw_comments.id/source/content/publish_date/url`。
- `agent.db`：角色诊断接口读取 `analysis_results`，包括 `character_id`、三项分数、`risk_warnings`、`word_cloud_data`、`associated_comment_ids` 和 `analysis_date`。
- `agent.db.analysis_results.character_id` 对应 `raw_data.db.characters.id`。关联评论 ID 必须能在 `raw_data.db.raw_comments.id` 中找到，否则“查看相关评论”会为空。

使用其他存放位置时，在根目录 `.env` 指定**两份文件的完整路径**：

```dotenv
GAMERPULSE_RAW_DATA_DB=D:/private/gamepulse/raw_data.db
GAMERPULSE_AGENT_DB_PATH=D:/private/gamepulse/agent.db
GAMEPULSE_RISK_DB=D:/private/gamepulse/agent.db
```

`GAMEPULSE_RISK_DB` 是独立风险卡工具的路径；主角色诊断接口使用 `GAMERPULSE_AGENT_DB_PATH`。不要把密钥或私有数据放进 `.env.example`。

复制数据库前先停止服务，备份原文件。若源数据库正被程序使用，应先用 SQLite 的备份功能生成一致性副本，再复制副本；不要从正在写入的数据库中只拷贝 `.db`、丢下对应的 WAL 状态。

### 验证数据库

启动后依次打开：

```text
http://127.0.0.1:8000/api/db/summary
http://127.0.0.1:8000/api/characters
http://127.0.0.1:8000/api/diagnosis?character_id=1
```

第一项应显示两库 `exists: true` 及表摘要；第二项应有角色；第三项的 `analysis_id` 不应为 `null`。若角色列表有数据、诊断却为空，先核对跨库的 `character_id` 和 `analysis_results` 内容。

## 2. 评论数据

网页的“查看相关评论”**读取数据库** `raw_comments`，不会直接读取 CSV。要显示评论，需要同时满足：

1. `raw_data.db.raw_comments` 已有评论记录，并尽可能填写 `source`、`content`、`url`。
2. `agent.db.analysis_results.associated_comment_ids` 引用了这些评论的 `id`。
3. 两库属于同一批数据，评论 ID 未在迁移后重新编号。

爬虫导出的原始 CSV 可由数据处理流程导入，但仅把 CSV 放到 `data/crawler/data/` 不会使页面自动出现评论。导入和预处理方法见 `data/README_SENTIMENT_PREPROCESS.md`。执行清理或覆盖操作前请先备份数据库；不要在公开仓库提交未经审核的评论原文与来源链接。

可用 `http://127.0.0.1:8000/api/comments/trace?ids=1,2` 测试评论追溯，实际测试时替换为数据库里存在的 ID。

## 3. 角色立绘

把已获授权使用的图片放在：

```text
frontend_assistant_yellow_white/
  frontend_yellow_white_fastapi_package_20260729/
    assets/characters/
```

当前页面使用 `mockData.js` 中各角色的 `portrait` 路径，例如：

```js
portrait: './assets/characters/秧秧.jpg'
```

图片文件名、扩展名和 `portrait` 值必须一致。要新增或改名角色图片，请同步修改 `mockData.js` 中相应角色的 `portrait` 字段。角色目录本身目前也来自 `mockData.js`；数据库中的新角色**不会仅凭入库自动出现在目录中**，还需要在前端目录数据中加入对应角色并保持 ID 与数据库一致。

`assets/characters/characters_manifest.json` 可作为素材来源记录，但当前 `app.js` 不从它生成图片路径。不要只改 manifest 而忘记改 `mockData.js`。未接入图片时，页面仍可显示角色数据，但立绘区域会缺图或留白。

在浏览器开发者工具的 Network 面板中检查图片请求是否返回 `200`；若返回 `404`，优先检查文件名、扩展名与路径。请确认图片有发布或使用授权，再用于公开部署。

## 4. 剧情库、Chroma 索引与模型

不接入索引时，可先用关键词检索：

```dotenv
GAMEPULSE_STORY_RETRIEVER=keyword
```

如需使用原有 Chroma 语义检索，准备以下内容：

```text
rag/rag_query.py                   代码仓库已提供
rag/chroma_db/chroma_db/           自行放入完整 Chroma 数据目录
rag/models/bge-m3/                 自行放入与索引匹配的本地 embedding 模型
```

Chroma 目录需包括 `chroma.sqlite3` 和相应的索引子目录；只复制 SQLite 文件或只复制 `.bin` 文件都可能使索引不可用。`bge-m3` 不包含在代码仓库中。启用前还需安装模型运行依赖，例如 `sentence-transformers` 及其所需的 PyTorch；这些大体积依赖并非默认后端清单的一部分。

默认路径就绪时工具可尝试启用 Chroma；自定义路径可在 `.env` 中指定：

```dotenv
GAMEPULSE_STORY_RETRIEVER=chroma-rag
GAMEPULSE_RAG_SCRIPT=D:/private/gamepulse/rag/rag_query.py
GAMEPULSE_CHROMA_DIR=D:/private/gamepulse/rag/chroma_db/chroma_db
GAMEPULSE_EMBEDDING_MODEL=D:/private/gamepulse/models/bge-m3
```

不要在缺少索引或模型时强制设置 `chroma-rag`。先以 `keyword` 模式启动并完成其他功能验证，再单独测试语义检索。索引与模型必须与本地剧情资料版本匹配，否则检索质量和来源可能不一致。

## 5. 最后检查

1. 复制 `.env.example` 为 `.env`，填写本机 API Key 和必要路径；不要把 `.env` 提交到仓库。
2. 按 `README.md` 启动服务，确认 `/health` 返回 `ok`。
3. 用 `/api/db/summary`、`/api/characters`、`/api/diagnosis` 验证两份数据库。
4. 用 `/api/comments/trace` 验证评论 ID、平台、正文和来源链接。
5. 打开 `/frontend/` 检查立绘请求；最后再测试需要联网 API 的助手聊天。

公开代码仓库默认忽略数据库、CSV、索引、图片、虚拟环境、运行时文件和凭据。打包给合作方时也应先确认评论、剧情资料和美术资源的授权范围。
