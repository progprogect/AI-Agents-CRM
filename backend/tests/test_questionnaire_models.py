"""Validation tests for the questionnaire Pydantic models."""

from __future__ import annotations

import pytest

from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireTemplate,
)


def test_field_key_accepts_valid_identifiers() -> None:
    QuestionnaireField(key="name", label="Имя", question="Как вас зовут?")
    QuestionnaireField(key="user_phone_1", label="Телефон", question="Номер?")


@pytest.mark.parametrize(
    "bad_key",
    ["Name", "1phone", "phone-number", "phone.num", " space", "", "x" * 31],
)
def test_field_key_rejects_invalid(bad_key: str) -> None:
    with pytest.raises(Exception):
        QuestionnaireField(key=bad_key, label="l", question="q")


def test_quick_replies_trim_and_limit() -> None:
    field = QuestionnaireField(
        key="k", label="l", question="q", quick_replies=[" yes ", "", "no"]
    )
    assert field.quick_replies == ["yes", "no"]


def test_quick_replies_reject_too_many() -> None:
    with pytest.raises(Exception):
        QuestionnaireField(
            key="k",
            label="l",
            question="q",
            quick_replies=[f"o{i}" for i in range(9)],
        )


def test_template_sorts_fields_and_rejects_duplicates() -> None:
    tpl = QuestionnaireTemplate(
        agent_id="a1",
        welcome_message="hi",
        fields=[
            QuestionnaireField(key="b", label="B", question="qb", order=5),
            QuestionnaireField(key="a", label="A", question="qa", order=0),
        ],
    )
    assert [f.key for f in tpl.fields] == ["a", "b"]
    assert tpl.fields[0].order == 0 and tpl.fields[1].order == 1

    with pytest.raises(Exception):
        QuestionnaireTemplate(
            agent_id="a1",
            fields=[
                QuestionnaireField(key="dup", label="A", question="qa"),
                QuestionnaireField(key="dup", label="B", question="qb"),
            ],
        )


def test_template_rejects_too_many_fields() -> None:
    with pytest.raises(Exception):
        QuestionnaireTemplate(
            agent_id="a",
            fields=[
                QuestionnaireField(key=f"k{i}", label=f"L{i}", question="q")
                for i in range(21)
            ],
        )
