"""Runtime application composition for provider-specific inbound routes."""

from app import (
    analysis_skill_versions_for_result,
    analyze_quote_request,
    app,
)
from db import get_request, save_request
from quixo_whatsapp_routes import build_quixo_whatsapp_router
from sendgrid_routes import build_sendgrid_router
from skill_promotion import load_active_skill_promotions


# Restore durable human-approved skill promotions before serving requests.
load_active_skill_promotions()


app.include_router(
    build_sendgrid_router(
        analyze_quote_request=analyze_quote_request,
        save_request=save_request,
        get_request=get_request,
        skill_versions=analysis_skill_versions_for_result,
    )
)

app.include_router(
    build_quixo_whatsapp_router(
        analyze_quote_request=analyze_quote_request,
        save_request=save_request,
        get_request=get_request,
        skill_versions=analysis_skill_versions_for_result,
    )
)
