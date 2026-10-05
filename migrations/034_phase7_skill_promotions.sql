ALTER TABLE service_skill_improvement_proposals
    DROP CONSTRAINT IF EXISTS improvement_proposal_status_valid;

ALTER TABLE service_skill_improvement_proposals
    ADD CONSTRAINT improvement_proposal_status_valid
        CHECK (status IN ('proposed', 'promoted'));

CREATE TABLE IF NOT EXISTS service_skill_promotions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL UNIQUE
        REFERENCES service_skill_improvement_proposals(id) ON DELETE CASCADE,
    revision_id UUID
        REFERENCES service_skill_improvement_revisions(id) ON DELETE RESTRICT,
    regression_test_id UUID NOT NULL UNIQUE
        REFERENCES service_skill_regression_tests(id) ON DELETE RESTRICT,
    skill_name TEXT NOT NULL,
    base_skill_version TEXT NOT NULL,
    promoted_skill_version TEXT NOT NULL,
    change_scope TEXT NOT NULL,
    base_instructions_snapshot TEXT NOT NULL,
    promoted_instructions TEXT NOT NULL,
    reason TEXT NOT NULL,
    promoted_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT skill_promotion_skill_nonempty
        CHECK (length(trim(skill_name)) > 0),
    CONSTRAINT skill_promotion_base_version_nonempty
        CHECK (length(trim(base_skill_version)) > 0),
    CONSTRAINT skill_promotion_new_version_nonempty
        CHECK (length(trim(promoted_skill_version)) > 0),
    CONSTRAINT skill_promotion_scope_valid
        CHECK (change_scope IN ('instructions', 'policy')),
    CONSTRAINT skill_promotion_base_instructions_nonempty
        CHECK (length(trim(base_instructions_snapshot)) > 0),
    CONSTRAINT skill_promotion_promoted_instructions_nonempty
        CHECK (length(trim(promoted_instructions)) > 0),
    CONSTRAINT skill_promotion_reason_nonempty
        CHECK (length(trim(reason)) > 0),
    CONSTRAINT skill_promotion_actor_nonempty
        CHECK (length(trim(promoted_by)) > 0),
    CONSTRAINT skill_promotion_unique_version
        UNIQUE (skill_name, promoted_skill_version)
);

CREATE INDEX IF NOT EXISTS idx_service_skill_promotions_request
    ON service_skill_promotions(request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_service_skill_promotions_skill
    ON service_skill_promotions(skill_name, created_at);
