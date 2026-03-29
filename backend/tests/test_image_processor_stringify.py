"""Tests for Gemini multimodal text normalization in ImageProcessorService."""

import unittest

from app.services.image_processor_service import _stringify_ai_message_content


class TestStringifyAiMessageContent(unittest.TestCase):
    def test_plain_str(self) -> None:
        self.assertEqual(_stringify_ai_message_content("  hello  "), "hello")

    def test_none(self) -> None:
        self.assertEqual(_stringify_ai_message_content(None), "")

    def test_list_text_blocks(self) -> None:
        raw = [
            {"type": "text", "text": "Part one. "},
            {"type": "text", "text": "Part two."},
        ]
        self.assertEqual(_stringify_ai_message_content(raw), "Part one. Part two.")

    def test_list_mixed_skips_non_text(self) -> None:
        raw = [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "Visible answer."},
        ]
        self.assertEqual(_stringify_ai_message_content(raw), "Visible answer.")

    def test_list_of_strings(self) -> None:
        self.assertEqual(_stringify_ai_message_content(["a", "b"]), "ab")


if __name__ == "__main__":
    unittest.main()
