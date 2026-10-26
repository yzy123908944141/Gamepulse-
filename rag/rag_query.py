"""
GamerPulse RAG 检索工具（只读查询版）

用途：加载已构建好的 chroma_db 向量库，提供语义检索功能。
      不含任何写入/重建逻辑，安全发给别人使用。

依赖：
    pip install chromadb sentence-transformers

还需要：
    BGE-M3 模型（HuggingFace 搜索 BAAI/bge-m3 下载到本地）

使用方式：
    from rag_query import search_lore, collection_stats

    # 全局检索
    results = search_lore("秧秧和漂泊者初次相遇")

    # 按角色ID过滤（秧秧=1）
    results = search_lore("角斗场战斗", character_id=1, top_k=5)

    # 按版本过滤
    results = search_lore("黑海岸危机", chapter="1.0")

    # 查看统计
    print(collection_stats())

命令行测试：
    python rag_query.py "你的查询文本"
    python rag_query.py --stats
"""

import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from pathlib import Path
from typing import List, Dict, Optional

# ============================================================
# 配置区 —— 改成你自己的路径
# ============================================================
# chroma_db 目录路径（从项目里拷过来的那个文件夹）
CHROMA_DIR = Path(__file__).resolve().parent / "chroma_db" / "chroma_db"

# BGE-M3 模型路径（下载后改到这里）
EMBEDDING_MODEL_PATH = str(Path(__file__).resolve().parent / "models" / "bge-m3")

COLLECTION_NAME = "story_lore"

# 懒加载单例
_client = None
_collection = None
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # Lazy Import
        if not Path(EMBEDDING_MODEL_PATH).exists():
            raise FileNotFoundError(
                f"找不到 embedding 模型: {EMBEDDING_MODEL_PATH}\n"
                f"请下载 BGE-M3 (HuggingFace: BAAI/bge-m3) 并修改 EMBEDDING_MODEL_PATH"
            )
        print(f"[RAG] 加载模型: {EMBEDDING_MODEL_PATH} ...")
        _model = SentenceTransformer(
            model_name_or_path=EMBEDDING_MODEL_PATH,
            device="cpu",
        )
        print(f"[RAG] 模型就绪（维度={_model.get_embedding_dimension()}）")
    return _model


def _encode(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                        show_progress_bar=len(texts) > 1)
    return vecs.tolist()


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    import chromadb  # Lazy Import
    from chromadb.config import Settings  # Lazy Import
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"找不到 chroma_db 目录: {CHROMA_DIR}\n"
            f"请确认已将 chroma_db 文件夹放在本脚本同级目录下"
        )
    _client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def search_lore(
    query: str,
    character_id: Optional[int] = None,
    chapter: Optional[str] = None,
    top_k: int = 3,
) -> List[Dict]:
    """
    语义检索剧情切片。

    Args:
        query: 检索文本
        character_id: 指定角色ID过滤（None=全局检索）
        chapter: 指定版本过滤，如 "1.0"
        top_k: 返回条数

    Returns:
        [{"text", "character_ids", "pov", "pov_type", "chapter", "event", "source", "impact", "distance"}]
        distance 越小越相关
    """
    collection = _get_collection()

    where = {"chapter": chapter} if chapter is not None else None
    fetch_k = top_k * 5 if character_id is not None else top_k

    query_vec = _encode([query])[0]

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=fetch_k,
        where=where,
    )

    docs_out: List[Dict] = []
    if not results["ids"] or not results["ids"][0]:
        return docs_out

    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        char_ids = [
            int(x) for x in meta.get("character_ids", "").strip(",").split(",") if x
        ]
        if character_id is not None and character_id not in char_ids:
            continue
        docs_out.append({
            "text": results["documents"][0][i],
            "character_ids": char_ids,
            "pov": meta.get("pov", ""),
            "pov_type": meta.get("pov_type", ""),
            "chapter": meta.get("chapter", ""),
            "event": meta.get("event", ""),
            "source": meta.get("source", ""),
            "impact": meta.get("impact", ""),
            "distance": results["distances"][0][i],
        })
        if len(docs_out) >= top_k:
            break
    return docs_out


def collection_stats() -> Dict:
    """返回 collection 统计信息"""
    collection = _get_collection()
    data = collection.get()
    chapters = {}
    for m in data["metadatas"]:
        ch = m.get("chapter", "?")
        chapters[ch] = chapters.get(ch, 0) + 1
    return {
        "total": collection.count(),
        "by_chapter": chapters,
    }


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]

    if "--stats" in args:
        print(collection_stats())
    elif args:
        query = " ".join(args)
        print(f"查询: {query}\n{'='*60}")
        results = search_lore(query, top_k=3)
        if not results:
            print("未找到相关结果")
        for i, r in enumerate(results, 1):
            print(f"\n--- 结果 {i} (distance={r['distance']:.4f}) ---")
            print(f"角色: {r['character_ids']} | 版本: {r['chapter']} | 事件: {r['event']}")
            print(f"视角: {r['pov']}({r['pov_type']}) | 来源: {r['source']}")
            print(f"内容:\n{r['text'][:200]}...")
    else:
        print("用法: python rag_query.py \"查询文本\"  或  python rag_query.py --stats")


