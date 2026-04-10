"""Payment provider factory."""

from app.models.payment import PaymentProvider, PaymentSettings
from app.services.payment.base import AbstractPaymentProvider


def get_payment_provider(settings: PaymentSettings) -> AbstractPaymentProvider:
    """Return the correct provider implementation for the given settings."""
    provider = settings.provider
    if isinstance(provider, str):
        provider = PaymentProvider(provider)

    if provider == PaymentProvider.TELEGRAM_NATIVE:
        from app.services.payment.telegram_native import TelegramNativeProvider
        return TelegramNativeProvider()

    if provider == PaymentProvider.EXTERNAL_LINK:
        from app.services.payment.external_link import ExternalLinkProvider
        return ExternalLinkProvider()

    raise ValueError(f"Unknown payment provider: {provider}")
