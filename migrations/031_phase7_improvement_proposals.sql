CREATE TABLE IF NOT EXISTS service_skill_improvement_proposals (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    evaluation_id UUID NOT NULL UNIQUE
        REFERENCES service_skill_evaluations(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    base_skill_version TEXT NOT NULL,
    change_scope TEXT NOT NULL,
    base_instructions_snapshot TEXT NOT NULL,
    proposed_change TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    proposed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT improvement_proposal_skill_nonempty
        CHECK (length(trim(skill_name)) > 0),
    CONSTRAINT improvement_proposal_version_nonempty
        CHECK (length(trim(base_skill_version)) > 0),
    CONSTRAINT improvement_proposal_scope_valid
        CHECK (change_scope IN ('instructions', 'policy')),
    CONSTRAINT improvement_proposal_base_nonempty
        CHECK (length(trim(base_instructions_snapshot)) > 0),
    CONSTRAINT improvement_proposal_change_nonempty
        CHECK (length(trim(proposed_change)) > 0),
    CONSTRAINT improvement_proposal_rationale_nonempty
        CHECK (length(trim(rationale)) > 0),
    CONSTRAINT improvement_proposal_status_valid
        CHECK (status = 'proposed'),
    CONSTRAINT improvement_proposal_proposer_nonempty
        CHECK (length(trim(proposed_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_service_skill_improvement_proposals_request
    ON service_skill_improvement_proposals(request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_service_skill_improvement_proposals_skill
    ON service_skill_improvement_proposals(
        skill_name,
        base_skill_version,
        created_at
    );
