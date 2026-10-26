# get_world_lore

`get_world_lore` 是一个本地世界观检索 Tool，用于从 `data/world.txt` 查询《鸣潮》的基础世界观资料。它只返回与问题最相关的文档片段，不会每次返回整个文件。

## 工具用途

- 查询世界总览、世界运行规则、灾害体系、索诺拉、共鸣者、文明级存在、地区组织和漂泊者相关设定。
- 为剧情舆情策略 Agent 提供世界观事实依据。
- 保留 `world.txt` 中明确存在的信息和原文术语。

## 职责边界

1. 本工具只提供世界观背景资料。
2. 不负责角色评价、剧情质量评价或舆情总结。
3. 不应根据文档之外的信息补充设定。
4. 找不到答案时，应返回未找到，而不是自行编造。
5. 索诺拉中的内容不一定等同于客观事实。
6. 岁主不能简单等同于全知神明。
7. 鸣式与普通残象不是同一层级。
8. 漂泊者真实身份属于主线谜团，不能擅自下定论。
9. 回答中应尽可能保留原文术语。
10. 返回内容必须注明来自 `world.txt`。

## 输入格式

```json
{
  "query": "什么是悲鸣？",
  "section": null,
  "max_chars": 3000
}
```

- `query`：必填。Agent 想查询的世界观问题或主题。
- `section`：可选。限定检索范围。
- `max_chars`：可选。返回 `content` 的最大字符数，默认 `3000`。

## 支持的 Section

```text
world_overview
world_rules
disaster_system
echo_and_sonoro
resonators
civilization_entities
regions_and_factions
rover
```

## 输出格式

```json
{
  "success": true,
  "query": "什么是悲鸣？",
  "matched_sections": ["灾害体系/悲鸣"],
  "content": "灾害体系/悲鸣\n索拉里斯所有重大灾变和异常趋势的统称……",
  "source": "data/world.txt",
  "truncated": false,
  "warnings": []
}
```

失败时：

```json
{
  "success": false,
  "query": "查询内容",
  "matched_sections": [],
  "content": "",
  "source": "data/world.txt",
  "truncated": false,
  "warnings": ["未找到相关世界观内容"]
}
```

## 调用示例

```python
from worldview_tool import get_world_lore

result = get_world_lore(
    query="解释悲鸣、海蚀和残象之间的关系",
    section="disaster_system",
    max_chars=3000,
)
```

## 错误处理

- `query` 为空：返回 `success=false` 与 `query 不能为空`。
- `section` 不受支持：返回 `success=false` 与不支持的 section。
- `world.txt` 不存在：返回 `success=false` 与清晰文件错误。
- `world.txt` 内容为空：返回 `success=false` 与清晰空文档错误。
- 未检索到相关内容：返回 `success=false`，不生成文档外设定。

## 与其他 Tool 的关系

- 角色 Tool：负责角色设定、动机、行为逻辑、人物弧光和代入感评价。
- 剧情 Tool：负责主线结构、叙事节奏、剧情因果、伏笔回收和主题表达评价。
- 舆情 Tool：负责玩家观点、情绪倾向、高频争议和潜在风险总结。
- `get_world_lore`：只提供世界观事实背景，供上述工具或总控 Agent 引用。
