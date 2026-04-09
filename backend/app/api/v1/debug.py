"""Debug endpoint for checking recent webhook events."""

from fastapi import APIRouter
from app.models.conversation import MessageChannel
from app.config import get_settings
from app.dependencies import CommonDependencies, Depends
from app.utils.enum_helpers import get_enum_value

router = APIRouter()


@router.get("/debug/recent-instagram-conversations")
async def get_recent_instagram_conversations(
    deps: CommonDependencies = Depends(),
):
    """Get recent Instagram conversations for debugging."""
    dynamodb = deps.dynamodb
    
    all_conversations = await dynamodb.list_conversations(limit=20)
    
    instagram_convos = [
        conv for conv in all_conversations
        if get_enum_value(conv.channel) == MessageChannel.INSTAGRAM.value
    ]
    
    instagram_convos.sort(
        key=lambda x: x.updated_at if x.updated_at else x.created_at,
        reverse=True
    )
    
    result = []
    for conv in instagram_convos[:5]:
        messages = await dynamodb.list_messages(
            conversation_id=conv.conversation_id,
            limit=3,
            reverse=True
        )
        
        result.append({
            "conversation_id": conv.conversation_id,
            "agent_id": conv.agent_id,
            "status": get_enum_value(conv.status),
            "external_user_id": conv.external_user_id,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "messages": [
                {
                    "role": get_enum_value(msg.role),
                    "content": msg.content[:100],
                    "timestamp": msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp),
                }
                for msg in messages
            ]
        })
    
    return {
        "total": len(instagram_convos),
        "conversations": result
    }

