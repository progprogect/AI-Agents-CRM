"""Run from backend: ``PYTHONPATH=. python -m unittest tests.test_inbound_media_pipeline -v``."""

import unittest

from app.services.inbound_media_pipeline import compose_user_message_for_agent


class TestComposeUserMessageForAgent(unittest.TestCase):
    def test_caption_and_summary(self) -> None:
        out = compose_user_message_for_agent("Hello", "A red car.")
        self.assertIn("Hello", out)
        self.assertIn("[User sent an image. Description: A red car.]", out)
        self.assertTrue(out.startswith("Hello"))

    def test_empty_caption_summary_only(self) -> None:
        out = compose_user_message_for_agent("", "Sky and clouds.")
        self.assertEqual(out, "[User sent an image. Description: Sky and clouds.]")

    def test_whitespace_caption_stripped(self) -> None:
        out = compose_user_message_for_agent("   \n  ", "Trees.")
        self.assertEqual(out, "[User sent an image. Description: Trees.]")

    def test_caption_with_whitespace_trimmed(self) -> None:
        out = compose_user_message_for_agent("  Hi  ", "x")
        self.assertEqual(out, "Hi\n\n[User sent an image. Description: x]")


if __name__ == "__main__":
    unittest.main()
