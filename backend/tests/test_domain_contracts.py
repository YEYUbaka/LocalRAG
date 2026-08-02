from dataclasses import FrozenInstanceError

import pytest

from app.domain.tenant import TenantScope
from app.schemas.sse import DoneEventV1, SSE_SCHEMA_VERSION


def test_tenant_scope_is_positive_and_immutable():
    scope = TenantScope(user_id=7, kb_id=11)
    assert (scope.user_id, scope.kb_id) == (7, 11)
    with pytest.raises(FrozenInstanceError):
        scope.user_id = 8
    with pytest.raises(ValueError, match="positive"):
        TenantScope(user_id=0, kb_id=11)


def test_done_event_has_frozen_schema_version():
    event = DoneEventV1(conversation_id=5)
    assert event.model_dump() == {
        "schema_version": SSE_SCHEMA_VERSION,
        "conversation_id": 5,
    }
