CREATE TABLE IF NOT EXISTS service_skill_evaluations (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    analysis_event_id UUID NOT NULL
        REFERENCES agent_events(id) ON DELETE RESTRICT,
    skill_name TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    verdict TEXT NOT NULL,
    notes TEXT NOT NULL,
    outcome_snapshot JSONB NOT NULL,
    evaluated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT skill_evaluation_name_nonempty
        CHECK (length(trim(skill_name)) > 0),
    CONSTRAINT skill_evaluation_version_nonempty
        CHECK (length(trim(skill_version)) > 0),
    CONSTRAINT skill_evaluation_verdict_valid
        CHECK (verdict IN ('pass', 'needs_review', 'fail')),
    CONSTRAINT skill_evaluation_notes_nonempty
        CHECK (length(trim(notes)) > 0),
    CONSTRAINT skill_evaluation_evaluator_nonempty
        CHECK (length(trim(evaluated_by)) > 0),
    CONSTRAINT skill_evaluation_event_skill_unique
        UNIQUE (analysis_event_id, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_service_skill_evaluations_request
    ON service_skill_evaluations(request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_service_skill_evaluations_skill
    ON service_skill_evaluations(skill_name, skill_version, created_at);
