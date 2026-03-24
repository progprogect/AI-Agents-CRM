"""Run from backend: ``PYTHONPATH=. python -m unittest tests.test_whatsapp_text_formatting -v``."""

import unittest

from app.utils.text_formatting import format_agent_text_for_whatsapp, remove_markdown


class TestFormatAgentTextForWhatsapp(unittest.TestCase):
    def test_image_bracket_line_to_bare_url(self) -> None:
        raw = "Intro line.\n[Image: https://cdn.example.com/a.webp.webp]\n\nFooter."
        out = format_agent_text_for_whatsapp(raw)
        self.assertNotIn("[Image:", out)
        self.assertIn("https://cdn.example.com/a.webp.webp", out)

    def test_image_bracket_case_insensitive(self) -> None:
        raw = "[image: https://x.com/p.png]"
        out = format_agent_text_for_whatsapp(raw)
        self.assertEqual(out.strip(), "https://x.com/p.png")

    def test_markdown_image_to_url(self) -> None:
        raw = "See ![stairs](https://img.com/1.jpg) here."
        out = format_agent_text_for_whatsapp(raw)
        self.assertNotIn("![", out)
        self.assertIn("https://img.com/1.jpg", out)

    def test_bold_stripped_after_image_normalize(self) -> None:
        raw = "**Bold** and [Image: https://z.com/i.png]"
        out = format_agent_text_for_whatsapp(raw)
        self.assertNotIn("**", out)
        self.assertIn("Bold", out)
        self.assertIn("https://z.com/i.png", out)

    def test_empty_string(self) -> None:
        self.assertEqual(format_agent_text_for_whatsapp(""), "")

    def test_remove_markdown_does_not_corrupt_markdown_image(self) -> None:
        """Regression: link strip must not turn ![alt](url) into '!alt' (web_chat path)."""
        raw = "See ![stairs](https://img.com/1.jpg) here."
        out = remove_markdown(raw)
        self.assertIn("https://img.com/1.jpg", out)
        self.assertNotIn("![", out)
        self.assertNotIn("!stairs", out)


if __name__ == "__main__":
    unittest.main()
