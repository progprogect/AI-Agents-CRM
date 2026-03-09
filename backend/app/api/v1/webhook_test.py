"""Test endpoints for webhook debugging."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.dependencies import CommonDependencies

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook-test/simulate-instagram")
async def simulate_instagram_webhook(
    request: Request,
    deps: CommonDependencies = Depends(),
):
    """Simulate Instagram webhook event for testing."""
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
        
        logger.info("="*80)
        logger.info("🧪 SIMULATED INSTAGRAM WEBHOOK EVENT")
        logger.info("="*80)
        logger.info(f"Full payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        # Forward to Instagram service directly
        from app.services.instagram_service import InstagramService
        from app.services.channel_binding_service import ChannelBindingService
        from app.storage.resolver import get_secrets_manager
        from app.config import get_settings
        
        settings = get_settings()
        secrets_manager = get_secrets_manager()
        binding_service = ChannelBindingService(deps.dynamodb, secrets_manager)
        instagram_service = InstagramService(binding_service, deps.dynamodb, settings)
        
        # Process webhook event
        await instagram_service.handle_webhook_event(payload)
        
        result = {"status": "ok"}
        
        return {
            "status": "ok",
            "message": "Webhook simulation completed",
            "result": result,
        }
    
    except Exception as e:
        logger.exception(f"Error simulating webhook: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/webhook-test/check-config")
async def check_webhook_config(
    deps: CommonDependencies = Depends(),
):
    """Check webhook configuration."""
    from app.config import get_settings
    
    settings = get_settings()
    
    base = (settings.app_url or "").rstrip("/")
    return {
        "webhook_verify_token_configured": settings.instagram_webhook_verify_token is not None,
        "app_secret_configured": settings.instagram_app_secret is not None,
        "webhook_url": f"{base}/api/v1/instagram/webhook",
        "webhook_verify_url": f"{base}/api/v1/instagram/webhook",
    }

