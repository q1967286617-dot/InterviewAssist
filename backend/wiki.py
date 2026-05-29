"""个人 Wiki 的读写。

目录结构:
  wiki/experiences/main.md
  wiki/competencies/main.md
  wiki/blind_spots/main.md
  wiki/growth_log/main.md
  wiki/narrative.md
  wiki/.meta.json   (记录面试次数)
"""
import json
from pathlib import Path

from . import config

SECTION_FILE = "main.md"
META_FILE = ".meta.json"


def ensure_dirs() -> None:
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    for section in config.WIKI_SECTIONS:
        (config.WIKI_DIR / section).mkdir(parents=True, exist_ok=True)


def _section_path(section: str) -> Path:
    return config.WIKI_DIR / section / SECTION_FILE


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_current_wiki() -> dict:
    """返回各分区当前 markdown 文本。"""
    data = {s: _read(_section_path(s)) for s in config.WIKI_SECTIONS}
    data["narrative"] = _read(config.WIKI_DIR / config.NARRATIVE_FILE)
    return data


def wiki_summary(max_chars: int = 1200) -> str:
    """给复盘教练用的精简摘要。"""
    wiki = read_current_wiki()
    parts = []
    for key in ["narrative", "growth_log", "blind_spots", "competencies"]:
        text = (wiki.get(key) or "").strip()
        if text:
            parts.append(f"### {key}\n{text}")
    summary = "\n\n".join(parts)
    return summary[:max_chars]


def _meta() -> dict:
    path = config.WIKI_DIR / META_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def interview_count() -> int:
    return int(_meta().get("interviews", 0))


def next_interview_number() -> int:
    return interview_count() + 1


def write_wiki(synth: dict) -> str:
    """把合成结果写入文件,返回 commit 摘要。"""
    ensure_dirs()
    mapping = {
        "experiences": _section_path("experiences"),
        "competencies": _section_path("competencies"),
        "blind_spots": _section_path("blind_spots"),
        "growth_log": _section_path("growth_log"),
        "narrative": config.WIKI_DIR / config.NARRATIVE_FILE,
    }
    for key, path in mapping.items():
        content = synth.get(key)
        if content:
            path.write_text(content, encoding="utf-8")

    # 更新面试计数
    meta = _meta()
    meta["interviews"] = int(meta.get("interviews", 0)) + 1
    (config.WIKI_DIR / META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    return synth.get("commit_summary", "已更新个人 Wiki")


def get_tree() -> list[dict]:
    """返回前端展示用的文件树。"""
    ensure_dirs()
    tree = []
    for section in config.WIKI_SECTIONS:
        path = _section_path(section)
        if path.exists() and path.read_text(encoding="utf-8").strip():
            tree.append(
                {"label": section, "path": f"{section}/{SECTION_FILE}", "type": "file"}
            )
        else:
            tree.append({"label": section, "path": None, "type": "empty"})
    narrative = config.WIKI_DIR / config.NARRATIVE_FILE
    tree.append(
        {
            "label": config.NARRATIVE_FILE,
            "path": config.NARRATIVE_FILE,
            "type": "file" if narrative.exists() else "empty",
        }
    )
    return tree


def read_relative(relpath: str) -> str:
    """安全读取 wiki 内相对路径文件。"""
    target = (config.WIKI_DIR / relpath).resolve()
    if not target.is_relative_to(config.WIKI_DIR.resolve()):
        return ""
    return target.read_text(encoding="utf-8") if target.exists() else ""
