"""Tenant ownership helpers for the Phase 8 migration boundary.

A missing tenant key represents the explicitly supported legacy/unowned scope.
A configured tenant key must resolve to one active durable tenant before it may
own or read tenant-scoped request data.
"""

from tenant_directory import get_tenant_by_key


class TenantScopeError(RuntimeError):
    pass


def resolve_active_tenant_id(tenant_key):
    if tenant_key is None:
        return None

    tenant = get_tenant_by_key(tenant_key)
    if tenant is None:
        raise TenantScopeError("Authenticated tenant does not exist")
    if tenant["status"] != "active":
        raise TenantScopeError("Authenticated tenant is not active")
    return tenant["id"]


def tenant_id_from_request(request):
    state = getattr(request, "state", None)
    tenant_key = (
        getattr(state, "tenant_key", None)
        if state is not None
        else None
    )
    return resolve_active_tenant_id(tenant_key)
