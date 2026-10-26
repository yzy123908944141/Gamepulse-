# query_story_context

`query_story_context` 是剧情资料检索与结构化概括 Tool。它先扫描剧情资料目录并建立增量索引，再根据查询检索相关片段，最后把命中片段交给模型生成结构化 JSON。

本工具不会把整个剧情库发送给模型。

## 输入

```json
{
  "query": "漂泊者在云陵谷经历了什么？",
  "story_library_path": "./story_library",
  "top_k": 8,
  "force_reindex": false
}
```

## 输出

输出包含：

- `characters`：相关人物、性格、动机和故事作用
- `story`：故事概要、关键事件、主要冲突和结果
- `background_setting`：地点、组织、世界规则和历史背景
- `source_refs`：实际检索命中的片段来源
- `information_gaps`：无法确认的信息或片段冲突
- `confidence`：`low`、`medium` 或 `high`

## 索引方式

- 支持 `.md` 和 `.txt` 文件。
- 优先按 Markdown `#`、`##`、`###` 标题切分。
- 没有标题时按长度切分，并保留重叠内容。
- 每个片段生成稳定 `chunk_id`。
- 索引文件保存在剧情库目录下的 `.story_index/story_index.json`。
- 文件 SHA-256 未变化时复用旧片段索引。
- 删除源文件后，对应索引会在下一次完整扫描时清理。

## 模型替换

模型层在 `src/story_retrieval_tool/summarizer.py`：

- `StorySummarizer`：抽象接口
- `MockStorySummarizer`：本地 Mock
- `OpenAICompatibleStorySummarizer`：OpenAI-compatible API 入口

DeepSeek 示例：

```bash
OPENAI_API_KEY=... \
OPENAI_BASE_URL=https://api.deepseek.com/v1 \
OPENAI_MODEL=deepseek-chat \
python -m story_retrieval_tool query \
  --library ./story_library \
  --query "漂泊者在云陵谷经历了什么？" \
  --top-k 8 \
  --summarizer openai-compatible
```

## 命令行

```bash
python -m story_retrieval_tool query \
  --library ./story_library \
  --query "漂泊者在云陵谷经历了什么？" \
  --top-k 8
```

## 接入已有 Chroma RAG

如果已有只读 `rag_query.py`，可作为检索后端接入：

```bash
python -m story_retrieval_tool query \
  --retriever chroma-rag \
  --rag-script D:/program/GamePulse/rag/rag_query.py \
  --chroma-dir D:/program/GamePulse/rag/chroma_db/chroma_db \
  --query "秧秧和漂泊者初次相遇发生了什么？" \
  --top-k 5
```

可选过滤：

```bash
--character-id 1
--chapter 1.0
```

如果 embedding 模型不在 `rag_query.py` 默认位置，也可以指定：

```bash
--embedding-model D:/program/models/bge-m3
```

注意：该模式要求 `rag_query.py` 自身依赖可用，包括 `chromadb`、`sentence-transformers` 和本地 embedding 模型。

## 边界

- 不做角色评分或剧情评分。
- 不做舆情分析。
- 不允许模型编造 `chunk_id` 或来源文件。
- 单个文件解析失败不会中断整个索引流程。
- 模型调用失败会返回明确错误，不伪造正常结果。

