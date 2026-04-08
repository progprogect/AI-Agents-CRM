"""Tests for RAG text chunking."""

from app.utils.text_chunking import split_text_into_chunks


def test_split_empty():
    assert split_text_into_chunks("", 1000, 50) == []


def test_short_text_single_chunk():
    t = "Hello world " * 10
    chunks = split_text_into_chunks(t, 500, 50)
    assert len(chunks) == 1
    assert chunks[0] == t.strip()


def test_long_text_multiple_chunks():
    t = "word " * 500
    chunks = split_text_into_chunks(t, 200, 30)
    assert len(chunks) >= 2
    assert all(len(c) <= 250 for c in chunks)
