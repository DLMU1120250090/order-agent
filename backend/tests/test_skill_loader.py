"""Commit 11：Prompt/Skill 边界 单元测试。

运行：cd order-agent && python -m pytest tests/test_skill_loader.py -q
"""
import pathlib

from app.services.skill_loader import list_skills, load_skill

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_four_skills_exist_with_required_sections():
    expected = {"travel-checklist", "ticket-change", "refund", "price-monitor"}
    assert set(list_skills()) == expected
    for name in expected:
        text = load_skill(name)
        assert text
        assert "## capability" in text
        assert "## retriever" in text  # RAG 预留位


def test_load_skill_unknown_returns_empty():
    assert load_skill("not-exist") == ""


def test_prompt_boundary_lines_present():
    checklist = (ROOT / "prompts" / "checklist.txt").read_text(encoding="utf-8")
    summary = (ROOT / "prompts" / "summary.txt").read_text(encoding="utf-8")
    assert "技能规则" in checklist
    assert "不编造" in checklist
    assert "不编造" in summary
