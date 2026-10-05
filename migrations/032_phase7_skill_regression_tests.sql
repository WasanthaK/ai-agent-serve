CREATE TABLE IF NOT EXISTS service_skill_regression_tests (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES agent_requests(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL UNIQUE
        REFERENCES service_skill_improvement_proposals(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    base_skill_version TEXT NOT NULL,
    change_scope TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    suite_version TEXT NOT NULL,
    case_results JSONB NOT NULL,
    total_cases INTEGER NOT NULL,
    target_cases INTEGER NOT NULL,
    fixed_target_cases INTEGER NOT NULL,
    regression_failures INTEGER NOT NULL,
    candidate_failures INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    tested_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT skill_regression_skill_nonempty
        CHECK (length(trim(skill_name)) > 0),
    CONSTRAINT skill_regression_version_nonempty
        CHECK (length(trim(base_skill_version)) > 0),
    CONSTRAINT skill_regression_scope_valid
        CHECK (change_scope IN ('instructions', 'policy')),
    CONSTRAINT skill_regression_suite_nonempty
        CHECK (length(trim(suite_name)) > 0),
    CONSTRAINT skill_regression_suite_version_nonempty
        CHECK (length(trim(suite_version)) > 0),
    CONSTRAINT skill_regression_cases_nonempty
        CHECK (jsonb_typeof(case_results) = 'array'
            AND jsonb_array_length(case_results) > 0),
    CONSTRAINT skill_regression_total_positive
        CHECK (total_cases > 0),
    CONSTRAINT skill_regression_target_positive
        CHECK (target_cases > 0),
    CONSTRAINT skill_regression_fixed_target_valid
        CHECK (fixed_target_cases >= 0 AND fixed_target_cases <= target_cases),
    CONSTRAINT skill_regression_regression_failures_valid
        CHECK (regression_failures >= 0),
    CONSTRAINT skill_regression_candidate_failures_valid
        CHECK (candidate_failures >= 0),
    CONSTRAINT skill_regression_verdict_valid
        CHECK (verdict IN ('pass', 'fail')),
    CONSTRAINT skill_regression_tester_nonempty
        CHECK (length(trim(tested_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_service_skill_regression_tests_request
    ON service_skill_regression_tests(request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_service_skill_regression_tests_skill
    ON service_skill_regression_tests(
        skill_name,
        base_skill_version,
        created_at
    );
