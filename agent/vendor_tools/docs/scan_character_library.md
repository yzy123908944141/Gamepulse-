# scan_character_library

`scan_character_library` 扫描角色库，把新增或原文变化的角色交给 AI 总结，生成适合上层 Agent 调用的短版角色上下文。

## 输入来源

支持 SQLite 数据库：

```bash
python -m character_tool scan \
  --library D:/program/two-dimensional_game/raw_data.db \
  --output ./outputs \
  --summarizer openai-compatible
```

数据库会自动识别 `characters` 表，并支持这些字段映射：

- ID：`character_id` 或 `id`
- 名字：`name` 或 `character_name`
- 背景故事：`background`、`background_lore` 或 `background_story`
- 个人概括：`personality`、`personality_setting` 或 `personal_profile`

也支持 JSON 文件或角色目录作为输入。

## 输出结构

单角色 JSON 使用短版 schema `1.2`：

```json
{
  "metadata": {
    "character_id": "db_char_0001",
    "name": "角色名",
    "aliases": [],
    "player_controllable": true,
    "summarized": 1,
    "source_hash": "",
    "schema_version": "1.2"
  },
  "basic_info": {
    "occupation": null,
    "identity": "",
    "faction": ""
  },
  "personality": "一句话性格概括",
  "background": "一句话背景概括",
  "motivation": "一句话目标动机",
  "relationships": [
    {
      "name": "关系对象",
      "relation": "简短关系说明"
    }
  ]
}
```

输出原则：

- 基本信息只保留职业、身份、阵营。
- 性格、背景、动机都压缩为短文本。
- 不输出依据、出处、信息缺口、能力、叙事作用或风险审查。
- 不补写原文不存在的信息。
- 关系不明确时返回空数组。

## 增量规则

- 合并 `background` 和 `personality` 原文后计算 SHA-256。
- 索引文件位于 `output_json_path/character_index.json`。
- 原文哈希变化、总结失败、JSON 缺失或 schema 版本变化时会重新总结。
- 只有 JSON 和 Markdown 都生成成功后，索引才记录 `summarized = 1`。

## 命令行

Mock 流程：

```bash
python -m character_tool scan --library ./characters --output ./outputs --summarizer mock
```

DeepSeek / OpenAI-compatible：

```bash
OPENAI_API_KEY=... \
OPENAI_BASE_URL=https://api.deepseek.com/v1 \
OPENAI_MODEL=deepseek-chat \
python -m character_tool scan \
  --library D:/program/two-dimensional_game/raw_data.db \
  --output ./outputs_deepseek_db \
  --summarizer openai-compatible \
  --force-rescan
```

小样本测试时使用 `--limit`：

```bash
python -m character_tool scan \
  --library D:/program/two-dimensional_game/raw_data.db \
  --output ./outputs_deepseek_sample \
  --summarizer openai-compatible \
  --force-rescan \
  --limit 3
```

## 职责边界

本工具只做角色资料压缩、增量扫描、JSON 校验和 Markdown 渲染；不做角色评价、剧情评价、舆情总结或总控 Agent 调度。
