"""Run from repo backend dir: ``PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -v``."""

import unittest

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.models.escalation import EscalationDecision
from app.utils.langchain_prompt import escape_braces_for_chat_template


class TestEscalationPromptTemplate(unittest.TestCase):
    def test_format_instructions_in_system_only_expects_message_and_context(self) -> None:
        parser = PydanticOutputParser(pydantic_object=EscalationDecision)
        schema_block = parser.get_format_instructions()
        system_prompt = escape_braces_for_chat_template(
            "Static rules header.\n" + schema_block
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "User message: {message}\n\nConversation context: {context}"),
            ]
        )
        self.assertEqual(set(prompt.input_variables), {"message", "context"})
        msgs = prompt.format_messages(message="hi", context="none")
        self.assertEqual(len(msgs), 2)
        system_content = msgs[0].content or ""
        self.assertIn('"properties"', system_content)
        human_content = msgs[1].content or ""
        self.assertIn("hi", human_content)
        self.assertIn("none", human_content)


class TestEscapeBracesForChatTemplate(unittest.TestCase):
    def test_doubles_braces(self) -> None:
        self.assertEqual(escape_braces_for_chat_template("{a}"), "{{a}}")
