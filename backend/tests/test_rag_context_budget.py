"""Tests for RAG context budget packing."""

from app.utils.rag_context_budget import format_rag_context_with_budget


def test_budget_truncates():
    results = [
        {"title": "A", "content": "x" * 500, "score": 0.9},
        {"title": "B", "content": "y" * 500, "score": 0.8},
    ]
    s, used = format_rag_context_with_budget(results, 400)
    assert used <= 400
    assert "[truncated]" in s or len(s) <= 400


def test_empty_results():
    s, used = format_rag_context_with_budget([], 1000)
    assert s == ""
    assert used == 0
