CREATE TABLE IF NOT EXISTS service_skill_improvement_revisions (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL
        REFERENCES service_skill_improvement_proposals(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    supersedes_regression_test_id UUID NOT NULL UNIQUE
        REFERENCES service_skill_regression_tests(id) ON DELETE RESTRICT,
    proposed_change TEXT NOT NULL,
    rationale TEXT NOT NULL,
    revised_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT skill_improvement_revision_number_positive
        CHECK (revision_number > 0),
    CONSTRAINT skill_improvement_revision_change_nonempty
        CHECK (length(trim(proposed_change)) > 0),
    CONSTRAINT skill_improvement_revision_rationale_nonempty
        CHECK (length(trim(rationale)) > 0),
    CONSTRAINT skill_improvement_revision_reviser_nonempty
        CHECK (length(trim(revised_by)) > 0),
    CONSTRAINT skill_improvement_revision_unique_number
        UNIQUE (proposal_id, revision_number)
);

CREATE INDEX IF NOT EXISTS idx_skill_improvement_revisions_request
    ON service_skill_improvement_revisions(request_id, created_at);

ALTER TABLE service_skill_regression_tests
    ADD COLUMN IF NOT EXISTS revision_id UUID
        REFERENCES service_skill_improvement_revisions(id) ON DELETE CASCADE;

ALTER TABLE service_skill_regression_tests
    DROP CONSTRAINT IF EXISTS service_skill_regression_tests_proposal_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_regression_base_proposal
    ON service_skill_regression_tests(proposal_id)
    WHERE revision_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_regression_revision
    ON service_skill_regression_tests(revision_id)
    WHERE revision_id IS NOT NULL;
