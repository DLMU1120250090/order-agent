"""Skill 文本加载器（Commit 11）。

skills/<name>/SKILL.md 静态文件按需读取（带缓存）：改技能文本不需要改代码。
retriever 为 RAG 预留位：未来在 SKILL.md 的 retriever 节声明查询接口即可接入。
"""
import functools
import pathlib

_SKILLS_DIR = pathlib.Path(__file__).resolve().parents[2] / "skills"


def list_skills() -> list:
    if not _SKILLS_DIR.exists():
        return []
    return sorted(p.name for p in _SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())


@functools.lru_cache(maxsize=32)
def load_skill(name: str) -> str:
    """读取技能文本；技能不存在时返回空串（调用方自行忽略）。"""
    path = _SKILLS_DIR / f"{name}" / "SKILL.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()
