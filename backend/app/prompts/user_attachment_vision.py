"""Vision prompt for inbound user images in chat (not RAG indexing)."""

CHAT_USER_IMAGE_PROMPT = """Briefly describe what the user showed in this image for a support/chat assistant.
Focus on objects, scene, text visible in the image, and anything relevant to understanding their message.
Reply in 1–3 short sentences, English only. Do not add a preamble."""
