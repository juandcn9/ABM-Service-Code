PRAGMA foreign_keys = ON;

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    migration_name TEXT NOT NULL UNIQUE
        CHECK (length(migration_name) BETWEEN 1 AND 128 AND migration_name NOT GLOB '*[^-A-Za-z0-9._~]*'),
    checksum TEXT NOT NULL
        CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    applied_at TEXT NOT NULL
        CHECK (length(applied_at) = 20
            AND applied_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', applied_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', applied_at) = applied_at)
);

CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY
        CHECK (length(account_id) BETWEEN 1 AND 128 AND account_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    customer_id TEXT NOT NULL UNIQUE
        CHECK (length(customer_id) BETWEEN 1 AND 128 AND customer_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    eligibility_reference TEXT NOT NULL
        CHECK (length(eligibility_reference) BETWEEN 1 AND 128 AND eligibility_reference NOT GLOB '*[^-A-Za-z0-9._~]*'),
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    current_balance_cents INTEGER NOT NULL DEFAULT 0
        CHECK (current_balance_cents BETWEEN -9007199254740991 AND 9007199254740991),
    restriction TEXT NOT NULL DEFAULT 'none'
        CHECK (restriction IN ('none', 'outgoing_blocked')),
    restriction_decision_reference TEXT
        CHECK (restriction_decision_reference IS NULL
            OR (length(restriction_decision_reference) BETWEEN 1 AND 128
                AND restriction_decision_reference NOT GLOB '*[^-A-Za-z0-9._~]*')),
    created_at TEXT NOT NULL
        CHECK (length(created_at) = 20
            AND created_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) = created_at),
    closed_at TEXT
        CHECK (closed_at IS NULL OR (length(closed_at) = 20
            AND closed_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', closed_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', closed_at) = closed_at)),
    CHECK ((status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL)),
    CHECK ((restriction = 'none' AND restriction_decision_reference IS NULL)
        OR (restriction = 'outgoing_blocked' AND restriction_decision_reference IS NOT NULL))
);

CREATE TABLE movements (
    movement_id TEXT PRIMARY KEY
        CHECK (length(movement_id) BETWEEN 1 AND 128 AND movement_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    counterparty_account_id TEXT REFERENCES accounts(account_id),
    movement_type TEXT NOT NULL
        CHECK (movement_type IN ('incoming_ach','outgoing_ach','internal_transfer','card','correction')),
    state TEXT NOT NULL
        CHECK (state IN ('pending','accepted_with_hold','submitted','settled','completed',
            'rejected','cancelled_before_submission','authorized_with_hold','cleared','late_cleared',
            'reversed','expired','returned','refunded','corrected')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 1 AND 9007199254740991),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    external_reference TEXT
        CHECK (external_reference IS NULL OR (length(external_reference) BETWEEN 1 AND 128
            AND external_reference NOT GLOB '*[^-A-Za-z0-9._~]*')),
    created_at TEXT NOT NULL
        CHECK (length(created_at) = 20 AND created_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) = created_at),
    updated_at TEXT NOT NULL
        CHECK (length(updated_at) = 20 AND updated_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) = updated_at),
    CHECK (counterparty_account_id IS NULL OR counterparty_account_id <> account_id)
);

CREATE TABLE movement_evidence (
    evidence_reference TEXT PRIMARY KEY
        CHECK (length(evidence_reference) BETWEEN 1 AND 128 AND evidence_reference NOT GLOB '*[^-A-Za-z0-9._~]*'),
    movement_id TEXT NOT NULL REFERENCES movements(movement_id),
    evidence_kind TEXT NOT NULL
        CHECK (evidence_kind IN ('settlement','return','submission','rejection','cancellation',
            'clearing','reversal','expiration','refund')),
    occurred_at TEXT NOT NULL
        CHECK (length(occurred_at) = 20 AND occurred_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', occurred_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', occurred_at) = occurred_at),
    UNIQUE (movement_id, evidence_kind)
);

CREATE TABLE holds (
    hold_id TEXT PRIMARY KEY
        CHECK (length(hold_id) BETWEEN 1 AND 128 AND hold_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    movement_id TEXT NOT NULL UNIQUE REFERENCES movements(movement_id),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 1 AND 9007199254740991),
    state TEXT NOT NULL CHECK (state IN ('active', 'released', 'posted')),
    evidence_reference TEXT REFERENCES movement_evidence(evidence_reference),
    created_at TEXT NOT NULL
        CHECK (length(created_at) = 20 AND created_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) = created_at),
    finalized_at TEXT
        CHECK (finalized_at IS NULL OR (length(finalized_at) = 20
            AND finalized_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', finalized_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', finalized_at) = finalized_at)),
    CHECK ((state = 'active' AND finalized_at IS NULL)
        OR (state <> 'active' AND finalized_at IS NOT NULL))
);

CREATE TABLE ledger_entries (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL UNIQUE
        CHECK (length(entry_id) BETWEEN 1 AND 128 AND entry_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    movement_id TEXT NOT NULL REFERENCES movements(movement_id),
    effect_kind TEXT NOT NULL
        CHECK (effect_kind IN ('incoming_settlement','incoming_return','outgoing_settlement',
            'outgoing_return','transfer_source_debit','transfer_destination_credit',
            'card_clearing','card_refund','correction')),
    direction TEXT NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 1 AND 9007199254740991),
    authorized_caller_id TEXT NOT NULL
        CHECK (length(authorized_caller_id) BETWEEN 1 AND 128 AND authorized_caller_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    authorized_role TEXT NOT NULL
        CHECK (length(authorized_role) BETWEEN 1 AND 128 AND authorized_role NOT GLOB '*[^-A-Za-z0-9._~]*'),
    external_reference TEXT
        CHECK (external_reference IS NULL OR (length(external_reference) BETWEEN 1 AND 128
            AND external_reference NOT GLOB '*[^-A-Za-z0-9._~]*')),
    correction_of_entry_id TEXT REFERENCES ledger_entries(entry_id),
    created_at TEXT NOT NULL
        CHECK (length(created_at) = 20 AND created_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) = created_at),
    CHECK ((effect_kind IN ('incoming_settlement','outgoing_return','transfer_destination_credit','card_refund') AND direction = 'credit')
        OR (effect_kind IN ('incoming_return','outgoing_settlement','transfer_source_debit','card_clearing') AND direction = 'debit')
        OR effect_kind = 'correction'),
    UNIQUE (movement_id, effect_kind)
);

CREATE TABLE idempotency_outcomes (
    scope TEXT NOT NULL
        CHECK (length(scope) BETWEEN 1 AND 128 AND scope NOT GLOB '*[^-A-Za-z0-9._~]*'),
    idempotency_key TEXT NOT NULL
        CHECK (length(idempotency_key) BETWEEN 1 AND 128 AND idempotency_key NOT GLOB '*[^-A-Za-z0-9._~]*'),
    fingerprint TEXT NOT NULL
        CHECK (length(fingerprint) = 64 AND fingerprint NOT GLOB '*[^0-9a-f]*'),
    instruction_id TEXT NOT NULL
        CHECK (length(instruction_id) BETWEEN 1 AND 128 AND instruction_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    outcome_class TEXT NOT NULL CHECK (outcome_class IN ('success','deterministic_rejection')),
    http_status INTEGER NOT NULL CHECK ((http_status BETWEEN 200 AND 299) OR http_status IN (404,409,422)),
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    created_at TEXT NOT NULL
        CHECK (length(created_at) = 20 AND created_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', created_at) = created_at),
    CHECK ((outcome_class = 'success'
            AND http_status BETWEEN 200 AND 299
            AND json_extract(response_json, '$.ok') = 1)
        OR (outcome_class = 'deterministic_rejection'
            AND json_extract(response_json, '$.ok') = 0
            AND ((http_status = 404
                    AND json_extract(response_json, '$.error.code') IN ('ACCOUNT_NOT_FOUND','MOVEMENT_NOT_FOUND'))
                OR (http_status = 409
                    AND json_extract(response_json, '$.error.code') IN ('DUPLICATE_ACCOUNT','INVALID_TRANSITION'))
                OR (http_status = 422
                    AND json_extract(response_json, '$.error.code') IN ('ACCOUNT_CLOSED','AMOUNT_MISMATCH',
                        'CLOSURE_PRECONDITION_FAILED','INSUFFICIENT_FUNDS','OUTGOING_BLOCKED'))))),
    PRIMARY KEY (scope, idempotency_key)
);

CREATE TABLE audit_trace (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT REFERENCES accounts(account_id),
    instruction_id TEXT NOT NULL
        CHECK (length(instruction_id) BETWEEN 1 AND 128 AND instruction_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    movement_id TEXT REFERENCES movements(movement_id),
    ledger_entry_id TEXT REFERENCES ledger_entries(entry_id),
    evidence_reference TEXT REFERENCES movement_evidence(evidence_reference),
    movement_state TEXT
        CHECK (movement_state IS NULL OR movement_state IN ('pending','accepted_with_hold','submitted','settled',
            'completed','rejected','cancelled_before_submission','authorized_with_hold','cleared',
            'late_cleared','reversed','expired','returned','refunded','corrected')),
    operation TEXT NOT NULL
        CHECK (length(operation) BETWEEN 1 AND 128 AND operation NOT GLOB '*[^-A-Za-z0-9._~]*'),
    outcome TEXT NOT NULL CHECK (outcome = 'accepted'),
    caller_id TEXT NOT NULL
        CHECK (length(caller_id) BETWEEN 1 AND 128 AND caller_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    caller_role TEXT NOT NULL
        CHECK (length(caller_role) BETWEEN 1 AND 128 AND caller_role NOT GLOB '*[^-A-Za-z0-9._~]*'),
    correlation_id TEXT NOT NULL
        CHECK (length(correlation_id) BETWEEN 1 AND 128 AND correlation_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    external_reference TEXT
        CHECK (external_reference IS NULL OR (length(external_reference) BETWEEN 1 AND 128
            AND external_reference NOT GLOB '*[^-A-Za-z0-9._~]*')),
    occurred_at TEXT NOT NULL
        CHECK (length(occurred_at) = 20 AND occurred_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', occurred_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', occurred_at) = occurred_at)
);

CREATE TABLE retention_metadata (
    account_id TEXT PRIMARY KEY REFERENCES accounts(account_id),
    record_type TEXT NOT NULL DEFAULT 'account' CHECK (record_type = 'account'),
    record_id TEXT NOT NULL UNIQUE
        CHECK (length(record_id) BETWEEN 1 AND 128
            AND record_id NOT GLOB '*[^-A-Za-z0-9._~]*'),
    final_at TEXT
        CHECK (final_at IS NULL OR (length(final_at) = 20
            AND final_at GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', final_at) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', final_at) = final_at)),
    eligible_after TEXT
        CHECK (eligible_after IS NULL OR (length(eligible_after) = 20
            AND eligible_after GLOB '????-??-??T??:??:??Z'
            AND strftime('%Y-%m-%dT%H:%M:%SZ', eligible_after) IS NOT NULL
            AND strftime('%Y-%m-%dT%H:%M:%SZ', eligible_after) = eligible_after)),
    legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0, 1)),
    legal_hold_decision_reference TEXT
        CHECK (legal_hold_decision_reference IS NULL
            OR (length(legal_hold_decision_reference) BETWEEN 1 AND 128
                AND legal_hold_decision_reference NOT GLOB '*[^-A-Za-z0-9._~]*')),
    CHECK (record_id = account_id),
    CHECK ((final_at IS NULL AND eligible_after IS NULL)
        OR (final_at IS NOT NULL AND eligible_after IS NOT NULL AND eligible_after >= final_at)),
    CHECK ((legal_hold = 0 AND legal_hold_decision_reference IS NULL)
        OR (legal_hold = 1 AND legal_hold_decision_reference IS NOT NULL))
);

CREATE INDEX idx_ledger_account_sequence ON ledger_entries(account_id, sequence);
CREATE INDEX idx_holds_account_state ON holds(account_id, state);
CREATE INDEX idx_movements_account_state ON movements(account_id, state);
CREATE INDEX idx_evidence_movement ON movement_evidence(movement_id, evidence_kind);
CREATE INDEX idx_trace_account_sequence ON audit_trace(account_id, sequence);
CREATE INDEX idx_retention_eligibility ON retention_metadata(legal_hold, eligible_after);

CREATE TRIGGER schema_version_no_update BEFORE UPDATE ON schema_version
BEGIN SELECT RAISE(ABORT, 'schema version history is immutable'); END;
CREATE TRIGGER schema_version_no_delete BEFORE DELETE ON schema_version
BEGIN SELECT RAISE(ABORT, 'schema version history is immutable'); END;
CREATE TRIGGER movement_evidence_no_update BEFORE UPDATE ON movement_evidence
BEGIN SELECT RAISE(ABORT, 'movement evidence is immutable'); END;
CREATE TRIGGER movement_evidence_no_delete BEFORE DELETE ON movement_evidence
BEGIN SELECT RAISE(ABORT, 'movement evidence deletion is not implemented in demonstration'); END;
CREATE TRIGGER ledger_entries_no_update BEFORE UPDATE ON ledger_entries
BEGIN SELECT RAISE(ABORT, 'ledger entries are immutable'); END;
CREATE TRIGGER ledger_entries_no_delete BEFORE DELETE ON ledger_entries
BEGIN SELECT RAISE(ABORT, 'ledger deletion is not implemented in demonstration'); END;
CREATE TRIGGER audit_trace_no_update BEFORE UPDATE ON audit_trace
BEGIN SELECT RAISE(ABORT, 'audit trace is immutable'); END;
CREATE TRIGGER audit_trace_no_delete BEFORE DELETE ON audit_trace
BEGIN SELECT RAISE(ABORT, 'audit deletion is not implemented in demonstration'); END;
