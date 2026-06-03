"""本地 Markdown 笔记（替代 HelloAgents NoteTool）。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_INDEX = "notes_index.json"


class NotesStore:
    def __init__(self, workspace: str) -> None:
        self.root = Path(workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / _INDEX
        if not self.index_path.exists():
            self.index_path.write_text("[]", encoding="utf-8")

    def _load_index(self) -> List[dict]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save_index(self, items: List[dict]) -> None:
        self.index_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(
        self,
        title: str,
        content: str,
        *,
        note_type: str = "task",
        tags: Optional[List[str]] = None,
    ) -> str:
        note_id = datetime.now().strftime("note_%Y%m%d_%H%M%S_%f")
        path = self.root / f"{note_id}.md"
        body = f"# {title}\n\n{content.strip()}\n"
        path.write_text(body, encoding="utf-8")
        items = self._load_index()
        items.append(
            {
                "id": note_id,
                "title": title,
                "note_type": note_type,
                "tags": tags or [],
                "path": str(path),
            }
        )
        self._save_index(items)
        return note_id

    def read(self, note_id: str) -> str:
        path = self.root / f"{note_id}.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def update(self, note_id: str, content: str, title: Optional[str] = None) -> bool:
        path = self.root / f"{note_id}.md"
        if not path.exists():
            return False
        t = title or note_id
        path.write_text(f"# {t}\n\n{content.strip()}\n", encoding="utf-8")
        return True

    def find_report_note_id(self, topic: str) -> Optional[str]:
        for item in reversed(self._load_index()):
            if item.get("note_type") == "conclusion":
                return item.get("id")
            title = item.get("title") or ""
            if isinstance(title, str) and title.startswith("研究报告"):
                return item.get("id")
        return None


def extract_note_id_from_response(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"note_\d{8}_\d{6}_\d+", text)
    return m.group(0) if m else None
