"""Runtime application composition for provider-specific inbound routes."""

from app import (
    ANALYSIS_SKILL_VERSIONS,
    analyze_quote_request,
    app,
)
from db import get_request, save_request
from quixo_whatsapp_routes import build_quixo_whatsapp_router
from sendgrid_routes import build_sendgrid_router


app.include_router(
    build_sendgrid_router(
        analyze_quote_request=analyze_quote_request,
        save_request=save_request,
        get_request=get_request,
        skill_versions=ANALYSIS_SKILL_VERSIONS,
    )
)

app.include_router(
    build_quixo_whatsapp_router(
        analyze_quote_request=analyze_quote_request,
        save_request=save_request,
        get_request=get_request,
        skill_versions=ANALYSIS_SKILL_VERSIONS,
    )
)
