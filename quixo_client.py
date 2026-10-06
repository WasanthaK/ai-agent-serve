import os
import time
from typing import Literal, Optional
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from expert_contracts import ProductSurface


QuixoPackageType = Literal[
    "requirement_intelligence",
    "commercial_proposal",
]


class QuixoClientError(Exception):
    """Base error for the Quixo anti-corruption boundary."""


class QuixoConfigurationError(QuixoClientError):
    """Required Quixo client configuration is missing or invalid."""


class QuixoAuthenticationError(QuixoClientError):
    """Quixo rejected the configured service credential."""


class QuixoUnavailableError(QuixoClientError):
    """Quixo could not be reached within the bounded retry policy."""


class QuixoContractError(QuixoClientError):
    """Quixo returned an unexpected response or rejected the contract."""


class QuixoCallerContext(BaseModel):
    """Explicit product/authority context. No authority is inferred across fields."""

    model_config = ConfigDict(extra="forbid")

    product_surface: ProductSurface
    provider_company_id: Optional[UUID] = None
    buyer_organization_id: Optional[UUID] = None
    identity_user_id: Optional[UUID] = None
    public_reference: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )


class QuixoRequestContactPresence(BaseModel):
    """Presence-only contact projection; raw contact values stay in Quixo."""

    model_config = ConfigDict(extra="forbid")

    has_name: bool
    has_email: bool
    has_phone: bool


class QuixoRequestLocation(BaseModel):
    """Minimum stable location projection for expert reasoning."""

    model_config = ConfigDict(extra="forbid")

    address: Optional[str] = Field(default=None, max_length=500)
    suburb: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=100)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class QuixoExpertContext(BaseModel):
    """
    Versioned, minimum authorised projection of a Quixo ServiceRequest.

    This intentionally mirrors stable domain concepts rather than QuoteService's
    entity/table layout.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    service_request_id: UUID
    request_version: int = Field(ge=1)
    request_mode: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    category: Optional[str] = Field(default=None, max_length=200)
    subcategory: Optional[str] = Field(default=None, max_length=200)
    urgency: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)
    specification_path: Optional[str] = Field(default=None, max_length=100)
    buyer_organization_id: Optional[UUID] = None
    requested_by_identity_user_id: Optional[UUID] = None
    contact_presence: QuixoRequestContactPresence
    location: QuixoRequestLocation


class QuixoExpertEvidenceAttachment(BaseModel):
    """
    Reference/provenance attached to Quixo; never a commercial mutation command.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    package_type: QuixoPackageType
    package_id: UUID
    package_version: int = Field(ge=1)
    source_request_version: int = Field(ge=1)
    analysis_id: UUID
    model: str = Field(min_length=1, max_length=200)
    skill_versions: dict[str, str] = Field(default_factory=dict)
    directive: Optional[str] = Field(default=None, min_length=1, max_length=100)
    ready_for_pricing: Optional[bool] = None
    ready_for_provider_review: Optional[bool] = None
    requires_human_review: bool = False
    safety_escalated: bool = False


class QuixoExpertEvidenceReceipt(BaseModel):
    """Idempotent acknowledgement from Quixo for attached expert evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    accepted: bool
    service_request_id: UUID
    package_id: UUID
    package_version: int = Field(ge=1)
    evidence_reference: str = Field(min_length=1, max_length=500)


class QuixoClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=1)
    internal_service_key: str = Field(min_length=32)
    timeout_seconds: float = Field(gt=0, le=30)
    max_attempts: int = Field(ge=1, le=3)

    @classmethod
    def from_env(cls):
        base_url = os.getenv("QUIXO_QUOTE_BASE_URL", "").strip()
        internal_key = os.getenv("QUIXO_INTERNAL_SERVICE_KEY", "")
        if not base_url:
            raise QuixoConfigurationError(
                "QUIXO_QUOTE_BASE_URL is required for Quixo integration"
            )
        if not internal_key or len(internal_key) < 32:
            raise QuixoConfigurationError(
                "QUIXO_INTERNAL_SERVICE_KEY must be configured with at least 32 characters"
            )

        try:
            timeout_seconds = float(
                os.getenv("QUIXO_HTTP_TIMEOUT_SECONDS", "5")
            )
            max_attempts = int(
                os.getenv("QUIXO_HTTP_MAX_ATTEMPTS", "2")
            )
        except ValueError as exc:
            raise QuixoConfigurationError(
                "Quixo HTTP timeout/retry settings are invalid"
            ) from exc

        try:
            return cls(
                base_url=base_url.rstrip("/") + "/",
                internal_service_key=internal_key,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
            )
        except Exception as exc:
            raise QuixoConfigurationError(
                "Quixo client configuration is invalid"
            ) from exc


class QuixoClient:
    """
    Explicit anti-corruption adapter for the Quixo QuoteService.

    It does not expose generic request methods, direct database access or Quixo
    entity models. Each public method is a reviewed cross-product contract.
    """

    EXPERT_CONTEXT_PATH = (
        "api/v1/quotes/internal/requests/{request_id}/expert-context"
    )
    EXPERT_EVIDENCE_PATH = (
        "api/v1/quotes/internal/requests/{request_id}/expert-evidence"
    )

    def __init__(
        self,
        config: QuixoClientConfig,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        sleep=time.sleep,
    ):
        self._config = config
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            transport=transport,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def get_request_expert_context(
        self,
        request_id: UUID,
        *,
        caller: QuixoCallerContext,
        correlation_id: str,
    ) -> QuixoExpertContext:
        params = self._caller_params(caller)
        response = self._send(
            "GET",
            self.EXPERT_CONTEXT_PATH.format(request_id=request_id),
            caller=caller,
            correlation_id=correlation_id,
            params=params,
        )
        try:
            return QuixoExpertContext.model_validate(response.json())
        except Exception as exc:
            raise QuixoContractError(
                "Quixo returned invalid expert-context data"
            ) from exc

    def attach_request_expert_evidence(
        self,
        request_id: UUID,
        evidence: QuixoExpertEvidenceAttachment,
        *,
        caller: QuixoCallerContext,
        correlation_id: str,
        idempotency_key: str,
    ) -> QuixoExpertEvidenceReceipt:
        response = self._send(
            "POST",
            self.EXPERT_EVIDENCE_PATH.format(request_id=request_id),
            caller=caller,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            json_body={
                "caller_context": caller.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
            },
        )
        try:
            return QuixoExpertEvidenceReceipt.model_validate(response.json())
        except Exception as exc:
            raise QuixoContractError(
                "Quixo returned invalid expert-evidence receipt"
            ) from exc

    def _caller_params(self, caller: QuixoCallerContext):
        data = caller.model_dump(mode="json", exclude_none=True)
        return {
            "product_surface": data.pop("product_surface"),
            **data,
        }

    def _headers(
        self,
        *,
        caller: QuixoCallerContext,
        correlation_id: str,
        idempotency_key: Optional[str],
    ):
        if not correlation_id or len(correlation_id) > 500:
            raise QuixoContractError("Invalid correlation_id")
        headers = {
            "X-Internal-Key": self._config.internal_service_key,
            "X-Expert-Product-Surface": caller.product_surface,
            "X-Correlation-ID": correlation_id,
            "Accept": "application/json",
        }
        if idempotency_key is not None:
            if not idempotency_key or len(idempotency_key) > 500:
                raise QuixoContractError("Invalid idempotency_key")
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _send(
        self,
        method: str,
        path: str,
        *,
        caller: QuixoCallerContext,
        correlation_id: str,
        idempotency_key: Optional[str] = None,
        params=None,
        json_body=None,
    ):
        headers = self._headers(
            caller=caller,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        retryable_method = method == "GET" or idempotency_key is not None
        last_error = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                response = self._client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if not retryable_method or attempt >= self._config.max_attempts:
                    raise QuixoUnavailableError(
                        "Quixo is temporarily unavailable"
                    ) from exc
                self._backoff(attempt)
                continue

            if response.status_code in {401, 403}:
                raise QuixoAuthenticationError(
                    "Quixo rejected the service credential or acting context"
                )

            if response.status_code == 404:
                raise QuixoContractError("Quixo request was not found")

            if response.status_code in {408, 429} or 500 <= response.status_code < 600:
                if retryable_method and attempt < self._config.max_attempts:
                    self._backoff(attempt)
                    continue
                raise QuixoUnavailableError(
                    "Quixo is temporarily unavailable"
                )

            if response.status_code < 200 or response.status_code >= 300:
                raise QuixoContractError(
                    f"Quixo rejected the expert contract with status {response.status_code}"
                )

            return response

        raise QuixoUnavailableError(
            "Quixo is temporarily unavailable"
        ) from last_error

    def _backoff(self, attempt: int):
        self._sleep(min(0.1 * (2 ** (attempt - 1)), 0.5))
