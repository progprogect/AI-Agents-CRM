"""Base tool class for LangChain tools."""

from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    """Base input for tools."""

    pass


class BaseAgentTool(BaseTool, ABC):
    """Base class for agent tools."""

    name: str
    description: str

    def __init__(self, agent_id: Optional[str] = None, **kwargs):
        """Initialize tool."""
        super().__init__(**kwargs)
        # Use object.__setattr__ to bypass Pydantic validation for agent_id
        object.__setattr__(self, 'agent_id', agent_id)

    @abstractmethod
    async def _arun(self, *args, **kwargs):
        """Async run method."""
        pass

    @abstractmethod
    def _run(self, *args, **kwargs):
        """Sync run method."""
        pass




