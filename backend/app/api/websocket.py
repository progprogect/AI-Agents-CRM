"""WebSocket handler for real-time chat."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.models.conversation import ConversationStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.agent_service import create_agent_service
from app.services.conversation_service import ConversationService
from app.storage.dynamodb import DynamoDBClient
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL = 25
HEARTBEAT_TIMEOUT = 5


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str) -> None:
        """Accept and store WebSocket connection."""
        await websocket.accept()
        self.active_connections[conversation_id] = websocket

        # Start heartbeat task
        self.heartbeat_tasks[conversation_id] = asyncio.create_task(
            self._heartbeat_loop(conversation_id)
        )

        logger.info(f"WebSocket connected: conversation_id={conversation_id}")

    async def disconnect(self, conversation_id: str) -> None:
        """Remove WebSocket connection."""
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

        # Cancel heartbeat task
        if conversation_id in self.heartbeat_tasks:
            self.heartbeat_tasks[conversation_id].cancel()
            del self.heartbeat_tasks[conversation_id]

        logger.info(f"WebSocket disconnected: conversation_id={conversation_id}")

    async def send_message(self, conversation_id: str, message: dict) -> bool:
        """Send message to specific conversation."""
        if conversation_id not in self.active_connections:
            return False

        websocket = self.active_connections[conversation_id]
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(
                f"Failed to send message to {conversation_id}: {e}",
                exc_info=True,
            )
            await self.disconnect(conversation_id)
            return False

    async def send_error(self, conversation_id: str, error_message: str) -> None:
        """Send error message to conversation."""
        await self.send_message(
            conversation_id,
            {
                "type": "error",
                "message": error_message,
                "timestamp": None,
            },
        )

    async def _heartbeat_loop(self, conversation_id: str) -> None:
        """Send periodic ping messages."""
        try:
            while conversation_id in self.active_connections:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if conversation_id in self.active_connections:
                    await self.send_message(
                        conversation_id,
                        {"type": "ping", "timestamp": None},
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error for {conversation_id}: {e}")

    def is_connected(self, conversation_id: str) -> bool:
        """Check if conversation has active connection."""
        return conversation_id in self.active_connections


# Global connection manager instance
connection_manager = ConnectionManager()


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for real-time chat."""
    await connection_manager.connect(websocket, conversation_id)

    try:
        # Get dependencies (simplified - in production use proper DI)
        from app.config import get_settings
        from app.dependencies import get_dynamodb

        settings = get_settings()
        dynamodb = get_dynamodb()
        conversation_service = ConversationService(dynamodb)

        # Verify conversation exists
        conversation = await dynamodb.get_conversation(conversation_id)
        if not conversation:
            await connection_manager.send_error(
                conversation_id, "Conversation not found"
            )
            await connection_manager.disconnect(conversation_id)
            return

        # Verify conversation is for web chat channel
        conversation_channel = get_enum_value(conversation.channel)
        if conversation_channel != MessageChannel.WEB_CHAT.value:
            await connection_manager.send_error(
                conversation_id,
                f"WebSocket is only available for web_chat channel, but conversation uses {conversation_channel}",
            )
            await connection_manager.disconnect(conversation_id)
            return

        # Send initial status
        # Handle both enum and string status (from DynamoDB)
        status_value = get_enum_value(conversation.status)
        await connection_manager.send_message(
            conversation_id,
            {
                "type": "status",
                "status": status_value,
                "conversation_id": conversation_id,
                "timestamp": None,
            },
        )

        while True:
            # Receive message from client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT + 10
                )
            except asyncio.TimeoutError:
                # Send ping to check connection
                await connection_manager.send_message(
                    conversation_id, {"type": "ping", "timestamp": None}
                )
                continue

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await connection_manager.send_error(
                    conversation_id, "Invalid JSON format"
                )
                continue

            # Handle different message types
            message_type = message_data.get("type")

            if message_type == "message":
                await _handle_message(
                    conversation_id,
                    message_data,
                    conversation_service,
                    dynamodb,
                )
            elif message_type == "ping":
                await connection_manager.send_message(
                    conversation_id, {"type": "pong", "timestamp": None}
                )
            elif message_type == "typing":
                # Forward typing indicator (could be broadcast to admin panel)
                pass
            else:
                await connection_manager.send_error(
                    conversation_id, f"Unknown message type: {message_type}"
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: conversation_id={conversation_id}")
    except Exception as e:
        logger.error(
            f"WebSocket error for {conversation_id}: {e}",
            exc_info=True,
        )
        await connection_manager.send_error(
            conversation_id, "An error occurred processing your message"
        )
    finally:
        await connection_manager.disconnect(conversation_id)


async def _handle_message(
    conversation_id: str,
    message_data: dict,
    conversation_service: ConversationService,
    dynamodb: DynamoDBClient,
) -> None:
    """Handle incoming message from client."""
    content = message_data.get("content", "").strip()
    if not content:
        await connection_manager.send_error(
            conversation_id, "Message content cannot be empty"
        )
        return

    # Get conversation
    conversation = await dynamodb.get_conversation(conversation_id)
    if not conversation:
        await connection_manager.send_error(
            conversation_id, "Conversation not found"
        )
        return

    # Check if conversation is active
    # Handle both enum and string status (from DynamoDB)
    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        await connection_manager.send_error(
            conversation_id, "Conversation is closed"
        )
        return

    # Create user message
    message_id = str(uuid.uuid4())
    user_message = Message(
        message_id=message_id,
        conversation_id=conversation_id,
        agent_id=conversation.agent_id,
        role=MessageRole.USER,
        content=content,
        channel=conversation.channel,
        timestamp=utc_now(),
    )

    await dynamodb.create_message(user_message)

    # Send user message confirmation
    await connection_manager.send_message(
        conversation_id,
        {
            "type": "message",
            "message_id": message_id,
            "role": "user",
            "content": content,
            "timestamp": to_utc_iso_string(user_message.timestamp),
        },
    )

    # Check if conversation is handled by human - don't process with agent
    if status_value in [
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ]:
        # Don't process with agent, just return
        return

    # Get agent configuration
    agent_data = await dynamodb.get_agent(conversation.agent_id)
    if not agent_data or "config" not in agent_data:
        await connection_manager.send_error(
            conversation_id, "Agent configuration not found"
        )
        return

    try:
        agent_config = AgentConfig.from_dict(agent_data["config"])
    except Exception as e:
        logger.error(f"Failed to load agent config: {e}", exc_info=True)
        await connection_manager.send_error(
            conversation_id, "Invalid agent configuration"
        )
        return

    # Process message through agent service
    # WebSocket is only for web_chat, so create WebChatSender
    from app.services.channel_sender import WebChatSender
    
    web_chat_sender = WebChatSender(dynamodb)
    agent_service = create_agent_service(agent_config, dynamodb, web_chat_sender)
    
    try:
        result = await conversation_service.process_message(
            conversation_id=conversation_id,
            user_message=content,
            agent_service=agent_service,
        )

        # Handle escalation
        if result.get("escalate"):
            await connection_manager.send_message(
                conversation_id,
                {
                    "type": "handoff",
                    "conversation_id": conversation_id,
                    "reason": result.get("escalation_reason", "Escalation required"),
                    "status": ConversationStatus.NEEDS_HUMAN.value,
                    "timestamp": None,
                },
            )
            return

        # Send agent response
        # Agent message is already created in agent_service.process_message
        agent_response = result.get("response")
        agent_message_id = result.get("agent_message_id")
        agent_message_timestamp = result.get("agent_message_timestamp")
        
        if agent_response and agent_message_id:
            # Use timestamp from result to avoid extra DB query
            timestamp = agent_message_timestamp or to_utc_iso_string(utc_now())
            ws_payload: dict = {
                "type": "message",
                "message_id": agent_message_id,
                "role": "agent",
                "content": agent_response,
                "timestamp": timestamp,
            }
            if result.get("rag_media_url"):
                ws_payload["media_url"] = result["rag_media_url"]
                ws_payload["media_type"] = result.get("rag_media_type")
            await connection_manager.send_message(conversation_id, ws_payload)
        elif agent_response:
            # If message wasn't created in agent_service (shouldn't happen, but handle gracefully)
            await connection_manager.send_error(
                conversation_id, "Failed to save agent response"
            )
        else:
            await connection_manager.send_error(
                conversation_id, "Failed to generate agent response"
            )
    except Exception as e:
        logger.error(
            f"Error processing message in WebSocket for conversation {conversation_id}: {e}",
            exc_info=True,
        )
        await connection_manager.send_error(
            conversation_id,
            "An error occurred while processing your message. Please try again.",
        )
        return


async def send_message_to_conversation(conversation_id: str, message: dict) -> bool:
    """Send message to specific conversation via WebSocket (utility function)."""
    return await connection_manager.send_message(conversation_id, message)
