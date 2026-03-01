"""Prompts for GPT-4V image description (RAG semantic search)."""

INITIAL_DESCRIPTION_PROMPT = """Describe this image in detail for semantic search. Output in English only.
Include: main subject, scale/size (small/medium/large), materials, colors, setting, 
distinguishing features. Be specific about proportions and relative size.
Keep the description concise but comprehensive (2-4 sentences)."""


def get_comparative_prompt(image_descriptions: list[dict]) -> str:
    """
    Build prompt for comparative description of similar images.

    image_descriptions: list of {"id": str, "description": str}
    """
    n = len(image_descriptions)
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"][:n]
    parts = []
    for label, item in zip(labels, image_descriptions):
        desc = item.get("description", "")
        parts.append(f"{label}: {desc}")
    initial_block = "\n".join(parts)
    return f"""You have {n} similar images ({', '.join(labels)}). Each was initially described:

{initial_block}

Add distinguishing details for each image so they can be told apart in search.
Focus on: relative size, unique elements, differences in composition.
Output JSON only: {{"{labels[0]}": "distinguishing details", "{labels[1] if len(labels) > 1 else ''}": "...", ...}}"""
