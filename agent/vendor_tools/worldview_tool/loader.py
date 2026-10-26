from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_WORLD_PATH = Path(__file__).resolve().parents[2] / "data" / "world.txt"


@dataclass(frozen=True)
class LoadResult:
    content: str
    source: Path
    warnings: list[str]


class WorldLoreLoader:
    def __init__(self, path: str | Path = DEFAULT_WORLD_PATH) -> None:
        self.path = Path(path)
        self._cached_content: str | None = None
        self.read_count = 0

    def load(self) -> LoadResult:
        if self._cached_content is not None:
            return LoadResult(self._cached_content, self.path, [])

        if not self.path.exists():
            return LoadResult("", self.path, [f"世界观文档不存在：{self.path}"])

        try:
            content = self.path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            return LoadResult("", self.path, [f"读取世界观文档失败：{exc}"])

        self.read_count += 1
        if not content.strip():
            return LoadResult("", self.path, ["世界观文档内容为空"])

        self._cached_content = content
        return LoadResult(content, self.path, [])

    def clear_cache(self) -> None:
        self._cached_content = None
