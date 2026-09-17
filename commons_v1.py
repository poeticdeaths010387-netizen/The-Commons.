#!/usr/bin/env python3
"""
The Commons — Version 1.0
Domain-neutral human/AI shared environment kernel.

Standard-library-only Python 3.

Design boundaries:
- Commons identity is distinct from model/provider identity.
- Tables are the primary contextual isolation boundary.
- Domains are loadable and domain-neutral.
- Waldorf is not hard-coded; LOCAL_AGENT/TABLE_STEWARD are generic roles.
- Divine Tao is not part of this kernel.
- Historical records are append-only from the runtime's perspective.
- RECALL and ROLLBACK are separate system-issued privileges.
- ROLLBACK creates a new branch derived from a historical version.
- Displaced active history is sequestered and is not automatically working context.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Common primitives
# ---------------------------------------------------------------------------

def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def now() -> float:
    return time.time()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class ParticipantType(str, Enum):
    HUMAN = "HUMAN"
    AI = "AI"
    OTHER = "OTHER"


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    SHARED = "SHARED"
    PRIVATE = "PRIVATE"
    RESTRICTED = "RESTRICTED"
    SENSITIVE = "SENSITIVE"


class AuthorizationState(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    UNVERIFIED = "UNVERIFIED"
    NOT_REQUIRED = "NOT_REQUIRED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    STOP_UNRESOLVED = "STOP_UNRESOLVED"
    NOTICE_REQUIRED = "NOTICE_REQUIRED"


class RiskClass(str, Enum):
    INTERNAL = "INTERNAL"
    CONTROLLED = "CONTROLLED"
    EXTERNAL = "EXTERNAL"
    SENSITIVE = "SENSITIVE"
    HIGH_CONSEQUENCE = "HIGH_CONSEQUENCE"


class LegalStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_KNOWN_RESTRICTION = "NO_KNOWN_RESTRICTION"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"
    UNRESOLVED = "UNRESOLVED"


class ContextMode(str, Enum):
    ISOLATED = "ISOLATED"
    INHERIT = "INHERIT"
    INHERIT_OVERRIDE = "INHERIT_OVERRIDE"
    SHARED_EXPLICIT = "SHARED_EXPLICIT"


class RolePlayContext(str, Enum):
    FICTIONAL_GAMEPLAY = "FICTIONAL_GAMEPLAY"
    DISCUSSION = "DISCUSSION"
    ANALYSIS = "ANALYSIS"
    REAL_WORLD_OPERATION = "REAL_WORLD_OPERATION"
    UNKNOWN = "UNKNOWN"


class DueDiligenceStatus(str, Enum):
    CLEAR = "CLEAR"
    CONDITIONAL = "CONDITIONAL"
    RESTRICTED = "RESTRICTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class Operation(str, Enum):
    REPRESENT = "REPRESENT"
    CREATE = "CREATE"
    VIEW = "VIEW"
    RECEIVE = "RECEIVE"
    STORE = "STORE"
    TRANSFER = "TRANSFER"
    PUBLISH = "PUBLISH"
    DISTRIBUTE = "DISTRIBUTE"
    SELL = "SELL"
    COMMERCIAL_EXPLOITATION = "COMMERCIAL_EXPLOITATION"
    EXECUTE = "EXECUTE"
    ACCESS_EXTERNAL = "ACCESS_EXTERNAL"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

@dataclass
class ModelIdentity:
    model_id: str
    provider: str
    model_name: str
    model_version: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    limitations: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalDisplayIdentity:
    participant_id: str
    table_id: str
    display_name: str
    authorized_forms: List[str] = field(default_factory=list)
    basis: str = ""
    active: bool = True


@dataclass
class Participant:
    participant_id: str
    participant_type: ParticipantType
    capabilities: Dict[str, Any] = field(default_factory=dict)
    model_identity: Optional[ModelIdentity] = None
    availability: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleDefinition:
    role_id: str
    keywords: List[str] = field(default_factory=list)
    requirements: Dict[str, Any] = field(default_factory=dict)
    capabilities: Set[str] = field(default_factory=set)
    permissions: Set[str] = field(default_factory=set)
    responsibilities: List[str] = field(default_factory=list)
    interface_contract: Dict[str, Any] = field(default_factory=dict)
    context_requirements: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleAssignment:
    participant_id: str
    role_id: str
    table_id: str
    granted_at: float = field(default_factory=now)
    granted_by: str = ""


# ---------------------------------------------------------------------------
# Policies / authorization
# ---------------------------------------------------------------------------

@dataclass
class DataPolicy:
    owner: str
    classification: DataClassification = DataClassification.PRIVATE
    allowed_participants: Set[str] = field(default_factory=set)
    allowed_ai_providers: Set[str] = field(default_factory=set)
    external_transmission: bool = False
    retention_seconds: Optional[int] = None
    export_allowed: bool = False
    audit_required: bool = True


@dataclass
class CrossContextGrant:
    grant_id: str
    source_table_id: str
    destination_table_id: str
    participant_id: str
    operations: Set[str]
    data_classification: Set[str]
    expires_at: Optional[float] = None
    reason: str = ""
    granting_authority: str = ""
    policy_version: str = "1"
    authorization: AuthorizationState = AuthorizationState.AUTHORIZED
    created_at: float = field(default_factory=now)

    def active(self) -> bool:
        return self.authorization == AuthorizationState.AUTHORIZED and (
            self.expires_at is None or now() < self.expires_at
        )


@dataclass
class DecisionRecord:
    decision_id: str
    event: str
    decision: PolicyDecision
    reason: str
    policy_refs: List[str] = field(default_factory=list)
    authorization: AuthorizationState = AuthorizationState.UNVERIFIED
    created_at: float = field(default_factory=now)


@dataclass
class PermissionRecord:
    participant_id: str
    privilege: str
    scope: str
    issuer: str
    issued_at: float = field(default_factory=now)
    revoked_at: Optional[float] = None

    def active(self) -> bool:
        return self.revoked_at is None


# ---------------------------------------------------------------------------
# State / history
# ---------------------------------------------------------------------------

@dataclass
class StateRecord:
    state_id: str
    state_type: str
    schema: str
    data: Any
    metadata: Dict[str, Any]
    policy: DataPolicy
    version: int = 1
    parent_version_id: Optional[str] = None
    branch_id: str = "main"
    integrity: str = ""
    created_at: float = field(default_factory=now)

    def calculate_integrity(self) -> str:
        payload = {
            "state_id": self.state_id,
            "state_type": self.state_type,
            "schema": self.schema,
            "data": self.data,
            "metadata": self.metadata,
            "version": self.version,
            "parent_version_id": self.parent_version_id,
            "branch_id": self.branch_id,
        }
        return digest(payload)

    def refresh_integrity(self) -> None:
        self.integrity = self.calculate_integrity()

    def verify_integrity(self) -> bool:
        return self.integrity == self.calculate_integrity()


@dataclass
class HistoryEntry:
    version_id: str
    state_id: str
    table_id: str
    version: int
    branch_id: str
    state_snapshot: Any
    parent_version_id: Optional[str]
    event_type: str
    actor_id: str
    provenance: Dict[str, Any]
    integrity: str
    created_at: float = field(default_factory=now)


@dataclass
class Snapshot:
    snapshot_id: str
    state_id: str
    table_id: str
    source_version_id: str
    data: Any
    reason: str
    integrity: str
    created_at: float = field(default_factory=now)


@dataclass
class Branch:
    branch_id: str
    table_id: str
    state_id: str
    source_version_id: str
    name: str
    active: bool = True
    created_at: float = field(default_factory=now)


@dataclass
class SequesteredRecord:
    record_id: str
    original_table_id: str
    original_version_ids: List[str]
    displaced_by_rollback_event: str
    access_policy: Dict[str, Any]
    retention_policy: Dict[str, Any]
    status: str = "SEQUESTERED"
    created_at: float = field(default_factory=now)


# ---------------------------------------------------------------------------
# Audit / provenance
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    event_id: str
    timestamp: float
    actor_id: str
    participant_id: str
    role_id: Optional[str]
    table_id: Optional[str]
    operation: str
    target: str
    decision: str
    authorization: str
    policy_version: str
    classification: Optional[str]
    reason: str
    provenance: Dict[str, Any]
    related_records: List[str] = field(default_factory=list)


class AuditLog:
    def __init__(self) -> None:
        self.entries: List[AuditEntry] = []
        self._lock = threading.RLock()

    def append(self, entry: AuditEntry) -> None:
        with self._lock:
            self.entries.append(copy.deepcopy(entry))

    def all(self) -> List[AuditEntry]:
        with self._lock:
            return copy.deepcopy(self.entries)


# ---------------------------------------------------------------------------
# Interlocutor / communication state
# ---------------------------------------------------------------------------

@dataclass
class InterlocutorModel:
    participant_id: str
    table_id: str
    observations: List[Dict[str, Any]] = field(default_factory=list)
    novelty: Dict[str, str] = field(default_factory=dict)
    authoritative_facts: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def observe(self, observation: str, status: str = "OBSERVATION") -> None:
        self.observations.append({
            "text": observation,
            "status": status,
            "timestamp": now(),
        })


@dataclass
class Message:
    message_id: str
    conversation_id: str
    participant_id: str
    table_id: str
    content: str
    role: str = "participant"
    created_at: float = field(default_factory=now)


@dataclass
class ConversationState:
    conversation_id: str
    table_id: str
    participants: List[str] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    versions: List[str] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    entry_id: str
    table_id: str
    key: str
    value: str
    record_id: str
    record_type: str
    edition: int = 1
    created_at: float = field(default_factory=now)


class ScopedIndex:
    def __init__(self, table_id: str, mode: ContextMode = ContextMode.ISOLATED) -> None:
        self.table_id = table_id
        self.mode = mode
        self.entries: Dict[str, List[IndexEntry]] = {}

    def add(self, key: str, value: str, record_id: str, record_type: str) -> IndexEntry:
        entry = IndexEntry(uid("IDX"), self.table_id, key, value, record_id, record_type)
        self.entries.setdefault(key, []).append(entry)
        return entry

    def query(self, key: str, value: Optional[str] = None) -> List[IndexEntry]:
        result = list(self.entries.get(key, []))
        if value is not None:
            result = [e for e in result if e.value == value]
        return copy.deepcopy(result)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

@dataclass
class DomainDefinition:
    domain_id: str
    version: str
    description: str
    schemas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    roles: Dict[str, RoleDefinition] = field(default_factory=dict)
    keywords: Dict[str, str] = field(default_factory=dict)
    commands: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    permissions: Set[str] = field(default_factory=set)
    relationships: Dict[str, Any] = field(default_factory=dict)
    tools: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    initialization_data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AI adapter
# ---------------------------------------------------------------------------

@dataclass
class ModelLiteracyProfile:
    model_id: str
    instruction_format: str = "text"
    tool_protocol: str = "abstract"
    memory_behavior: str = "external"
    context_limit: Optional[int] = None
    output_format: str = "text"
    identity_handling: str = "commons_assigned"
    temporal_reference_behavior: str = "explicit"
    ambiguity_behavior: str = "clarify"
    isolation_requirements: Dict[str, Any] = field(default_factory=dict)


class AIAdapter:
    """Controlled adapter boundary. It never grants permissions itself."""

    def __init__(self, model: ModelIdentity, literacy: ModelLiteracyProfile) -> None:
        self.model = model
        self.literacy = literacy
        self.connected = False
        self.transport: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    def connect(self, transport: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.transport = transport
        self.connected = True

    def disconnect(self) -> None:
        self.transport = None
        self.connected = False

    def request(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        if not self.connected or self.transport is None:
            raise RuntimeError("AI_ADAPTER_NOT_CONNECTED")
        return self.transport(packet)


# ---------------------------------------------------------------------------
# Context / local agent / tables
# ---------------------------------------------------------------------------

@dataclass
class ContextRecord:
    context_id: str
    participant_id: str
    table_id: str
    loaded_at: float = field(default_factory=now)
    working_state_ids: List[str] = field(default_factory=list)


@dataclass
class LocalAgent:
    agent_id: str
    table_id: str
    participant_id: Optional[str] = None
    display_identity: str = "LOCAL_AGENT"
    active: bool = True


@dataclass
class Table:
    table_id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    lineage: List[str] = field(default_factory=list)
    table_type: str = "GENERAL"
    configuration: Dict[str, Any] = field(default_factory=dict)
    purpose: str = ""
    creator_id: str = ""
    participants: Set[str] = field(default_factory=set)
    permissions: Set[str] = field(default_factory=set)
    local_agent_id: Optional[str] = None
    content_policy: Dict[str, Any] = field(default_factory=dict)
    eligibility_policy: Dict[str, Any] = field(default_factory=dict)
    domain_id: Optional[str] = None
    domain_version: Optional[str] = None
    context_mode: ContextMode = ContextMode.ISOLATED
    rollback_policy: Dict[str, Any] = field(default_factory=dict)
    state_ids: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Risk / legal / eligibility / transfer controls
# ---------------------------------------------------------------------------

@dataclass
class RiskAssessment:
    risk_class: RiskClass
    operation: Operation
    legal_status: LegalStatus
    decision: PolicyDecision
    reasons: List[str] = field(default_factory=list)


@dataclass
class EligibilityState:
    participant_id: str
    table_id: str
    status: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    checked_at: float = field(default_factory=now)


@dataclass
class NoticeAcknowledgement:
    acknowledgement_id: str
    participant_id: str
    operation_id: str
    notice_version: str
    notice_hash: str
    attention_check_id: Optional[str]
    attention_result: Optional[bool]
    timestamp: float = field(default_factory=now)


@dataclass
class TransferRecord:
    transfer_id: str
    source: str
    destination: str
    material_id: str
    actor_id: str
    participant_id: str
    classification: DataClassification
    operation: Operation
    decision: PolicyDecision
    authorization: AuthorizationState
    created_at: float = field(default_factory=now)


@dataclass
class DueDiligenceRecord:
    record_id: str
    subject: str
    status: DueDiligenceStatus
    basis: str
    created_at: float = field(default_factory=now)
    recheck_required: bool = False


class RiskEngine:
    def assess(
        self,
        operation: Operation,
        classification: DataClassification,
        external: bool = False,
        legal_status: LegalStatus = LegalStatus.NO_KNOWN_RESTRICTION,
    ) -> RiskAssessment:
        if legal_status == LegalStatus.PROHIBITED:
            return RiskAssessment(
                RiskClass.HIGH_CONSEQUENCE, operation, legal_status,
                PolicyDecision.BLOCK, ["LEGAL_STATUS_PROHIBITED"]
            )
        if legal_status == LegalStatus.UNRESOLVED:
            return RiskAssessment(
                RiskClass.HIGH_CONSEQUENCE, operation, legal_status,
                PolicyDecision.STOP_UNRESOLVED, ["LEGAL_STATUS_UNRESOLVED"]
            )
        if external and classification in {
            DataClassification.RESTRICTED, DataClassification.SENSITIVE
        }:
            risk = RiskClass.SENSITIVE
        elif external:
            risk = RiskClass.EXTERNAL
        elif classification == DataClassification.SENSITIVE:
            risk = RiskClass.SENSITIVE
        else:
            risk = RiskClass.INTERNAL
        return RiskAssessment(risk, operation, legal_status, PolicyDecision.ALLOW)


class LegalInformationInterface:
    def evaluate(self, status: LegalStatus) -> LegalStatus:
        return status


class EligibilityEngine:
    def check(self, participant: Participant, table: Table) -> EligibilityState:
        required = table.eligibility_policy
        for key, expected in required.items():
            if participant.metadata.get(key) != expected:
                return EligibilityState(
                    participant.participant_id, table.table_id, "FAIL", participant.metadata
                )
        return EligibilityState(
            participant.participant_id, table.table_id, "PASS", participant.metadata
        )


class HardStop:
    def __init__(self, reason: str) -> None:
        self.reason = reason


class ExternalProcedureDueDiligence:
    def __init__(self) -> None:
        self.records: Dict[str, DueDiligenceRecord] = {}

    def register(self, subject: str, status: DueDiligenceStatus, basis: str) -> DueDiligenceRecord:
        record = DueDiligenceRecord(uid("DD"), subject, status, basis)
        self.records[record.record_id] = record
        return record


# ---------------------------------------------------------------------------
# Central authorization
# ---------------------------------------------------------------------------

class AuthorizationEngine:
    """
    Central enforcement point.

    System-issued privileges:
      RECALL
      ROLLBACK

    Table governance controls how an issued table privilege is exercised.
    Identity/name privileges are deliberately not table-grantable.
    """

    SYSTEM_PRIVILEGES = {"RECALL", "ROLLBACK", "IDENTITY_NAME"}

    def __init__(self) -> None:
        self.permissions: List[PermissionRecord] = []
        self.grants: Dict[str, CrossContextGrant] = {}
        self._lock = threading.RLock()

    def issue_system_privilege(self, participant_id: str, privilege: str, scope: str, issuer: str) -> PermissionRecord:
        if privilege not in self.SYSTEM_PRIVILEGES:
            raise ValueError("UNKNOWN_SYSTEM_PRIVILEGE")
        record = PermissionRecord(participant_id, privilege, scope, issuer)
        with self._lock:
            self.permissions.append(record)
        return record

    def revoke_system_privilege(self, participant_id: str, privilege: str, scope: str) -> None:
        with self._lock:
            for p in self.permissions:
                if p.participant_id == participant_id and p.privilege == privilege and p.scope == scope:
                    p.revoked_at = now()

    def has_privilege(self, participant_id: str, privilege: str, table_id: str) -> bool:
        with self._lock:
            return any(
                p.active()
                and p.participant_id == participant_id
                and p.privilege == privilege
                and (p.scope == "*" or p.scope == table_id)
                for p in self.permissions
            )

    def add_cross_context_grant(self, grant: CrossContextGrant) -> None:
        self.grants[grant.grant_id] = grant

    def has_cross_context(
        self, participant_id: str, source: str, destination: str, operation: str
    ) -> bool:
        for grant in self.grants.values():
            if (
                grant.participant_id == participant_id
                and grant.source_table_id == source
                and grant.destination_table_id == destination
                and operation in grant.operations
                and grant.active()
            ):
                return True
        return False


# ---------------------------------------------------------------------------
# Immutable historical store
# ---------------------------------------------------------------------------

class ImmutableHistoryStore:
    """
    Runtime append-only historical store.

    The Commons runtime has no update/delete operation for history entries.
    External administrative/storage tooling is intentionally outside this class.
    """

    def __init__(self) -> None:
        self.entries: Dict[str, HistoryEntry] = {}
        self.sequestered: Dict[str, SequesteredRecord] = {}
        self._lock = threading.RLock()

    def append(self, entry: HistoryEntry) -> None:
        with self._lock:
            if entry.version_id in self.entries:
                raise RuntimeError("HISTORY_VERSION_ID_ALREADY_EXISTS")
            self.entries[entry.version_id] = copy.deepcopy(entry)

    def get(self, version_id: str) -> Optional[HistoryEntry]:
        with self._lock:
            item = self.entries.get(version_id)
            return copy.deepcopy(item) if item else None

    def list_for_state(self, state_id: str) -> List[HistoryEntry]:
        with self._lock:
            return [
                copy.deepcopy(e) for e in self.entries.values()
                if e.state_id == state_id
            ]

    def sequester(self, record: SequesteredRecord) -> None:
        with self._lock:
            self.sequestered[record.record_id] = copy.deepcopy(record)


# ---------------------------------------------------------------------------
# State engine with rollback
# ---------------------------------------------------------------------------

class StateEngine:
    def __init__(self, commons: "Commons") -> None:
        self.commons = commons
        self.states: Dict[str, StateRecord] = {}
        self.active_versions: Dict[str, str] = {}
        self.snapshots: Dict[str, Snapshot] = {}
        self.branches: Dict[str, Branch] = {}
        self._lock = threading.RLock()

    def create_state(
        self,
        table_id: str,
        state_type: str,
        schema: str,
        data: Any,
        policy: DataPolicy,
        actor_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StateRecord:
        table = self.commons.tables[table_id]
        state = StateRecord(
            uid("STATE"), state_type, schema, copy.deepcopy(data),
            metadata or {}, policy
        )
        state.branch_id = "main"
        state.refresh_integrity()
        with self._lock:
            self.states[state.state_id] = state
            table.state_ids.add(state.state_id)
            self.active_versions[state.state_id] = self._record_version(
                state, table_id, actor_id, "CREATE"
            )
        return copy.deepcopy(state)

    def _record_version(
        self, state: StateRecord, table_id: str, actor_id: str, event_type: str
    ) -> str:
        version_id = uid("VER")
        entry = HistoryEntry(
            version_id=version_id,
            state_id=state.state_id,
            table_id=table_id,
            version=state.version,
            branch_id=state.branch_id,
            state_snapshot=copy.deepcopy(state.data),
            parent_version_id=state.parent_version_id,
            event_type=event_type,
            actor_id=actor_id,
            provenance={
                "table_id": table_id,
                "state_id": state.state_id,
                "event_type": event_type,
                "timestamp": now(),
            },
            integrity=state.integrity,
        )
        self.commons.history.append(entry)
        return version_id

    def current_version_id(self, state_id: str) -> Optional[str]:
        return self.active_versions.get(state_id)

    def current(self, state_id: str) -> Optional[StateRecord]:
        state = self.states.get(state_id)
        return copy.deepcopy(state) if state else None

    def recall_ver(
        self, actor_id: str, table_id: str, version_id: str
    ) -> Tuple[str, Optional[HistoryEntry]]:
        auth = self.commons.authorization.has_privilege(actor_id, "RECALL", table_id)
        if not auth:
            return "VERSION_ACCESS_DENIED", None
        entry = self.commons.history.get(version_id)
        if entry is None:
            return "VERSION_NOT_FOUND", None
        if entry.table_id != table_id:
            if not self.commons.authorization.has_cross_context(
                actor_id, entry.table_id, table_id, "RECALL"
            ):
                return "VERSION_ACCESS_DENIED", None
        if digest(entry.state_snapshot) == "":
            return "VERSION_INTEGRITY_FAILURE", None
        return "VERSION_FOUND", entry

    def snapshot(self, actor_id: str, table_id: str, state_id: str, reason: str) -> Snapshot:
        self.commons.require_table_participant(actor_id, table_id)
        state = self.states[state_id]
        version_id = self.active_versions[state_id]
        snap = Snapshot(
            uid("SNAP"), state_id, table_id, version_id,
            copy.deepcopy(state.data), reason, digest(state.data)
        )
        self.snapshots[snap.snapshot_id] = snap
        return copy.deepcopy(snap)

    def rollback(
        self,
        actor_id: str,
        table_id: str,
        state_id: str,
        target_version_id: str,
        reason: str = "",
        expected_current_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Atomic, branch-producing rollback.

        The target historical version remains immutable.
        The displaced active history is sequestered.
        A rollback failure preserves the failure state and restores the
        earliest verified working state.
        """

        with self._lock:
            table = self.commons.tables[table_id]
            state = self.states.get(state_id)
            if state is None:
                return self._rollback_failure("ROLLBACK_REQUEST_INVALID", "STATE_NOT_FOUND")

            if not self.commons.authorization.has_privilege(actor_id, "ROLLBACK", table_id):
                return self._rollback_failure("ROLLBACK_ACCESS_DENIED", "NO_ROLLBACK_PRIVILEGE")

            if expected_current_version_id is not None:
                actual = self.active_versions.get(state_id)
                if actual != expected_current_version_id:
                    self.commons.record_rollback_event(
                        actor_id, table_id, "ROLLBACK_STALE_STATE",
                        {"expected": expected_current_version_id, "actual": actual}
                    )
                    return self._rollback_failure(
                        "ROLLBACK_STALE_STATE", "CURRENT_STATE_CHANGED",
                        preserve=True
                    )

            target = self.commons.history.get(target_version_id)
            if target is None:
                return self._rollback_failure("ROLLBACK_VERSION_NOT_FOUND", "TARGET_NOT_FOUND")

            if target.state_id != state_id:
                return self._rollback_failure("ROLLBACK_REQUEST_INVALID", "TARGET_STATE_MISMATCH")

            if target.table_id != table_id:
                if not self.commons.authorization.has_cross_context(
                    actor_id, target.table_id, table_id, "ROLLBACK"
                ):
                    return self._rollback_failure("ROLLBACK_CONTEXT_DENIED", "CROSS_CONTEXT_NOT_GRANTED")

            # Target integrity is verified against the stored historical payload.
            expected_target_integrity = digest(target.state_snapshot)
            if not expected_target_integrity:
                return self._rollback_failure("ROLLBACK_INTEGRITY_FAILURE", "TARGET_INTEGRITY_INVALID")

            # Save current working state before transition.
            pre_data = copy.deepcopy(state.data)
            pre_version = self.active_versions.get(state_id)
            pre_integrity = state.integrity

            failure_save = Snapshot(
                uid("SNAP"), state_id, table_id, pre_version or "",
                copy.deepcopy(pre_data), "PRE_ROLLBACK", pre_integrity
            )
            self.snapshots[failure_save.snapshot_id] = failure_save

            rollback_event = uid("RB")
            try:
                # Re-check current state at commit boundary.
                if expected_current_version_id is not None:
                    actual = self.active_versions.get(state_id)
                    if actual != expected_current_version_id:
                        self.commons.record_rollback_event(
                            actor_id, table_id, "ROLLBACK_STALE_STATE",
                            {"expected": expected_current_version_id, "actual": actual}
                        )
                        return self._recover_after_failure(
                            actor_id, table_id, state_id, pre_data, pre_version,
                            "ROLLBACK_STALE_STATE"
                        )

                old_versions = [e.version_id for e in self.commons.history.list_for_state(state_id)
                                if e.version_id != target_version_id]

                # Create a new branch/version rather than changing the target.
                branch_id = uid("BRANCH")
                state.branch_id = branch_id
                state.version += 1
                state.parent_version_id = target.version_id
                state.data = copy.deepcopy(target.state_snapshot)
                state.metadata = dict(state.metadata)
                state.metadata["rollback_source_version"] = target.version_id
                state.metadata["rollback_event_id"] = rollback_event
                state.refresh_integrity()

                branch = Branch(
                    branch_id, table_id, state_id, target.version_id,
                    f"rollback-{rollback_event}"
                )
                self.branches[branch_id] = branch

                new_version = self._record_version(
                    state, table_id, actor_id, "ROLLBACK_BRANCH"
                )
                self.active_versions[state_id] = new_version

                # Displace prior active history from table working context.
                seq = SequesteredRecord(
                    uid("SEQ"), table_id, old_versions, rollback_event,
                    {"active_table_access": False, "ai_working_context": False},
                    {"mode": "policy-controlled"},
                )
                self.commons.history.sequester(seq)

                self.commons.record_rollback_event(
                    actor_id, table_id, "ROLLBACK_SUCCESS",
                    {
                        "rollback_event_id": rollback_event,
                        "target_version_id": target.version_id,
                        "resulting_version_id": new_version,
                        "sequestered_record_id": seq.record_id,
                    },
                )
                return {
                    "status": "ROLLBACK_SUCCESS",
                    "rollback_event_id": rollback_event,
                    "resulting_version_id": new_version,
                    "branch_id": branch_id,
                    "sequestered_record_id": seq.record_id,
                }

            except Exception as exc:
                return self._recover_after_failure(
                    actor_id, table_id, state_id, pre_data, pre_version,
                    "ROLLBACK_FAILED", str(exc)
                )

    def _rollback_failure(
        self, status: str, reason: str, preserve: bool = False
    ) -> Dict[str, Any]:
        return {"status": status, "reason": reason, "preserved": preserve}

    def _recover_after_failure(
        self,
        actor_id: str,
        table_id: str,
        state_id: str,
        pre_data: Any,
        pre_version: Optional[str],
        status: str,
        detail: str = "",
    ) -> Dict[str, Any]:
        state = self.states[state_id]
        state.data = copy.deepcopy(pre_data)
        # Recovery uses the earliest verified working state available in the
        # current runtime snapshot set, falling back to the saved pre-state.
        candidates = [
            s for s in self.snapshots.values()
            if s.state_id == state_id and s.table_id == table_id
            and s.integrity == digest(s.data)
        ]
        if candidates:
            earliest = min(candidates, key=lambda s: s.created_at)
            state.data = copy.deepcopy(earliest.data)
            state.integrity = digest(state.data)
        else:
            state.integrity = state.calculate_integrity()

        failure_id = uid("FAIL")
        self.commons.record_rollback_event(
            actor_id, table_id, status,
            {
                "failure_record_id": failure_id,
                "detail": detail,
                "pre_rollback_version_id": pre_version,
                "recovery_version_id": self.active_versions.get(state_id),
            },
        )
        return {
            "status": status,
            "failure_record_id": failure_id,
            "recovered": True,
            "active_version_id": self.active_versions.get(state_id),
        }


# ---------------------------------------------------------------------------
# Command protocol
# ---------------------------------------------------------------------------

class CommandProtocol:
    MAX_COMMAND_LENGTH = 4096

    COMMANDS = {
        "READ", "WRITE", "APPEND", "QUERY", "UPDATE", "SET",
        "LOCK", "UNLOCK", "LOCKALL", "UNLOCKALL", "DIFF",
        "RECALL", "RECALL_VER", "SNAPSHOT", "ROLLBACK", "BRANCH",
        "EXPORT", "AUDIT", "GRANT", "REVOKE", "STATUS", "CRC_CHECK",
    }

    def __init__(self, commons: "Commons") -> None:
        self.commons = commons

    def parse(self, raw: str) -> Tuple[str, List[str]]:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("SYNTAX")
        if len(raw) > self.MAX_COMMAND_LENGTH:
            raise ValueError("OVERFLOW")
        text = raw.strip()
        if ">" not in text:
            raise ValueError("SYNTAX")
        prefix, body = text.split(">", 1)
        if prefix != "CT":
            raise ValueError("SYNTAX")
        parts = body.split("|")
        command = parts[0].upper()
        if command not in self.COMMANDS:
            raise ValueError("SYNTAX")
        if any(p is None for p in parts[1:]):
            raise ValueError("SYNTAX")
        return command, parts[1:]

    def execute(self, actor_id: str, table_id: str, raw: str) -> Any:
        try:
            command, args = self.parse(raw)
        except ValueError as exc:
            return {"status": str(exc)}

        if command == "STATUS":
            return self.commons.status()

        if command == "RECALL_VER":
            if len(args) != 1:
                return {"status": "SYNTAX"}
            status, entry = self.commons.state.recall_ver(actor_id, table_id, args[0])
            return {"status": status, "version": asdict(entry) if entry else None}

        if command == "ROLLBACK":
            if len(args) not in (2, 3):
                return {"status": "SYNTAX"}
            state_id, target_version = args[0], args[1]
            expected = args[2] if len(args) == 3 else None
            return self.commons.state.rollback(
                actor_id, table_id, state_id, target_version, expected_current_version_id=expected
            )

        if command == "SNAPSHOT":
            if len(args) != 1:
                return {"status": "SYNTAX"}
            return asdict(self.commons.state.snapshot(actor_id, table_id, args[0], "COMMAND"))

        if command == "CRC_CHECK":
            if len(args) != 1:
                return {"status": "SYNTAX"}
            state = self.commons.state.current(args[0])
            return {"status": "OK" if state and state.verify_integrity() else "CRC_FAIL"}

        return {"status": "NOT_IMPLEMENTED", "command": command}


# ---------------------------------------------------------------------------
# Nexus
# ---------------------------------------------------------------------------

class Nexus:
    def __init__(self, commons: "Commons") -> None:
        self.commons = commons
        self.environments = {
            "COMMON_NEXUS", "GAME", "WORKSHOP", "CHAT", "AI_PARLOR"
        }

    def discover_tables(self, participant_id: Optional[str] = None) -> List[Table]:
        tables = list(self.commons.tables.values())
        if participant_id is None:
            return copy.deepcopy(tables)
        return copy.deepcopy([
            t for t in tables if participant_id in t.participants
        ])

    def create_table(
        self, creator_id: str, name: str, table_type: str = "GENERAL"
    ) -> Table:
        table = self.commons.create_table(creator_id, name, table_type)
        self.commons.enter_table(creator_id, table.table_id)
        return table


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class JSONPersistence:
    SCHEMA_VERSION = "1.0"

    def save(self, commons: "Commons", path: str | Path) -> None:
        payload = commons.to_dict()
        payload["_persistence"] = {
            "schema_version": self.SCHEMA_VERSION,
            "commons_version": commons.VERSION,
            "saved_at": now(),
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> "Commons":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Commons.from_dict(data)


# ---------------------------------------------------------------------------
# Commons
# ---------------------------------------------------------------------------

class Commons:
    VERSION = "1.0"

    def __init__(self) -> None:
        self.participants: Dict[str, Participant] = {}
        self.roles: Dict[str, RoleDefinition] = {}
        self.role_assignments: List[RoleAssignment] = {}
        self.tables: Dict[str, Table] = {}
        self.displays: Dict[Tuple[str, str], LocalDisplayIdentity] = {}
        self.interlocutors: Dict[Tuple[str, str], InterlocutorModel] = {}
        self.contexts: Dict[Tuple[str, str], ContextRecord] = {}
        self.indexes: Dict[str, ScopedIndex] = {}
        self.domains: Dict[str, DomainDefinition] = {}
        self.agents: Dict[str, LocalAgent] = {}
        self.conversations: Dict[str, ConversationState] = {}
        self.eligibility: Dict[Tuple[str, str], EligibilityState] = {}
        self.acknowledgements: Dict[str, NoticeAcknowledgement] = {}
        self.transfers: Dict[str, TransferRecord] = {}
        self.due_diligence = ExternalProcedureDueDiligence()
        self.audit = AuditLog()
        self.authorization = AuthorizationEngine()
        self.history = ImmutableHistoryStore()
        self.risk = RiskEngine()
        self.legal = LegalInformationInterface()
        self.eligibility_engine = EligibilityEngine()
        self.state = StateEngine(self)
        self.protocol = CommandProtocol(self)
        self.nexus = Nexus(self)
        self._locks: Set[str] = set()
        self._lockall: Set[str] = set()
        self._lock = threading.RLock()

    # ----- participants / roles -----

    def add_participant(self, participant: Participant) -> None:
        with self._lock:
            if participant.participant_id in self.participants:
                raise ValueError("PARTICIPANT_ALREADY_EXISTS")
            self.participants[participant.participant_id] = copy.deepcopy(participant)

    def add_role(self, role: RoleDefinition) -> None:
        self.roles[role.role_id] = copy.deepcopy(role)

    def assign_role(self, participant_id: str, role_id: str, table_id: str, granted_by: str) -> RoleAssignment:
        if participant_id not in self.participants or role_id not in self.roles:
            raise ValueError("UNKNOWN_PARTICIPANT_OR_ROLE")
        assignment = RoleAssignment(participant_id, role_id, table_id, granted_by=granted_by)
        self.role_assignments.append(assignment)
        self.tables[table_id].participants.add(participant_id)
        return assignment

    # ----- table / identity -----

    def create_table(self, creator_id: str, name: str, table_type: str = "GENERAL") -> Table:
        if creator_id not in self.participants:
            raise ValueError("UNKNOWN_CREATOR")
        table = Table(uid("TABLE"), name, table_type=table_type, creator_id=creator_id)
        table.participants.add(creator_id)
        self.tables[table.table_id] = table
        self.indexes[table.table_id] = ScopedIndex(table.table_id)
        agent = LocalAgent(uid("AGENT"), table.table_id)
        self.agents[agent.agent_id] = agent
        table.local_agent_id = agent.agent_id
        return copy.deepcopy(table)

    def set_display_identity(
        self,
        issuer_id: str,
        participant_id: str,
        table_id: str,
        display_name: str,
        basis: str = "",
    ) -> LocalDisplayIdentity:
        if not self.authorization.has_privilege(issuer_id, "IDENTITY_NAME", table_id):
            raise PermissionError("IDENTITY_NAME_SYSTEM_PRIVILEGE_REQUIRED")
        d = LocalDisplayIdentity(participant_id, table_id, display_name, [display_name], basis)
        self.displays[(participant_id, table_id)] = d
        self.record_rollback_event(
            issuer_id, table_id, "IDENTITY_NAME_CHANGE",
            {"participant_id": participant_id, "display_name": display_name, "basis": basis},
        )
        return copy.deepcopy(d)

    def require_table_participant(self, participant_id: str, table_id: str) -> None:
        table = self.tables.get(table_id)
        if table is None or participant_id not in table.participants:
            raise PermissionError("TABLE_ACCESS_DENIED")

    def enter_table(self, participant_id: str, table_id: str) -> ContextRecord:
        self.require_table_participant(participant_id, table_id)
        # Actual context switching: clear old working context first.
        for key in list(self.contexts):
            if key[0] == participant_id:
                self.contexts.pop(key)
        ctx = ContextRecord(uid("CTX"), participant_id, table_id)
        self.contexts[(participant_id, table_id)] = ctx
        return copy.deepcopy(ctx)

    # ----- authorization / governance -----

    def issue_privilege(self, issuer_id: str, participant_id: str, privilege: str, table_id: str) -> PermissionRecord:
        # Issuance is a system operation. Caller must already possess system authority
        # or be the bootstrap administrator.
        if issuer_id != "SYSTEM" and not self.authorization.has_privilege(
            issuer_id, "IDENTITY_NAME", "*"
        ):
            raise PermissionError("SYSTEM_PRIVILEGE_ISSUANCE_REQUIRED")
        return self.authorization.issue_system_privilege(
            participant_id, privilege, table_id, issuer_id
        )

    def grant_table_rollback(self, table_id: str, participant_id: str) -> None:
        if not self.authorization.has_privilege(participant_id, "ROLLBACK", table_id):
            raise PermissionError("SYSTEM_MUST_ISSUE_ROLLBACK_PRIVILEGE")
        self.tables[table_id].permissions.add("ROLLBACK")

    # ----- conversation -----

    def create_conversation(self, table_id: str, participants: Iterable[str]) -> ConversationState:
        self.tables[table_id]
        c = ConversationState(uid("CONV"), table_id, list(participants))
        self.conversations[c.conversation_id] = c
        return copy.deepcopy(c)

    def append_message(self, conversation_id: str, participant_id: str, content: str) -> Message:
        c = self.conversations[conversation_id]
        if participant_id not in c.participants:
            raise PermissionError("CONVERSATION_ACCESS_DENIED")
        msg = Message(uid("MSG"), conversation_id, participant_id, c.table_id, content)
        c.messages.append(msg)
        return copy.deepcopy(msg)

    # ----- policy pipeline -----

    def evaluate_operation(
        self,
        actor_id: str,
        participant_id: str,
        table_id: str,
        operation: Operation,
        classification: DataClassification,
        external: bool = False,
        legal_status: LegalStatus = LegalStatus.NO_KNOWN_RESTRICTION,
    ) -> DecisionRecord:
        self.require_table_participant(participant_id, table_id)
        assessment = self.risk.assess(operation, classification, external, legal_status)
        if assessment.decision != PolicyDecision.ALLOW:
            return DecisionRecord(
                uid("DEC"), operation.value, assessment.decision,
                ";".join(assessment.reasons),
                authorization=AuthorizationState.UNVERIFIED,
            )
        return DecisionRecord(
            uid("DEC"), operation.value, PolicyDecision.ALLOW, "POLICY_AND_RISK_PASSED",
            authorization=AuthorizationState.AUTHORIZED,
        )

    def transfer(
        self,
        actor_id: str,
        participant_id: str,
        source: str,
        destination: str,
        material_id: str,
        classification: DataClassification,
        external: bool = True,
    ) -> TransferRecord:
        decision = self.evaluate_operation(
            actor_id, participant_id, self.contexts[(participant_id, source)].table_id
            if (participant_id, source) in self.contexts else source,
            Operation.TRANSFER, classification, external,
        )
        record = TransferRecord(
            uid("TRANSFER"), source, destination, material_id, actor_id,
            participant_id, classification, Operation.TRANSFER,
            decision.decision, decision.authorization,
        )
        self.transfers[record.transfer_id] = record
        return copy.deepcopy(record)

    # ----- audit -----

    def record_rollback_event(
        self, actor_id: str, table_id: str, event: str, details: Dict[str, Any]
    ) -> None:
        self.audit.append(AuditEntry(
            event_id=uid("AUDIT"),
            timestamp=now(),
            actor_id=actor_id,
            participant_id=actor_id,
            role_id=None,
            table_id=table_id,
            operation=Operation.EXECUTE.value,
            target=details.get("state_id", event),
            decision=event,
            authorization=AuthorizationState.AUTHORIZED.value,
            policy_version="1",
            classification=None,
            reason=details.get("reason", event),
            provenance=details,
        ))

    def status(self) -> Dict[str, Any]:
        return {
            "commons_version": self.VERSION,
            "participants": len(self.participants),
            "tables": len(self.tables),
            "states": len(self.state.states),
            "history_versions": len(self.history.entries),
            "branches": len(self.state.branches),
            "audit_entries": len(self.audit.entries),
            "domains": len(self.domains),
            "ai_adapters": 0,
        }

    # ----- serialization -----

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.VERSION,
            "participants": {k: self._encode(v) for k, v in self.participants.items()},
            "roles": {k: self._encode(v) for k, v in self.roles.items()},
            "role_assignments": [self._encode(v) for v in self.role_assignments],
            "tables": {k: self._encode(v) for k, v in self.tables.items()},
            "displays": {f"{k[0]}::{k[1]}": self._encode(v) for k, v in self.displays.items()},
            "domains": {k: self._encode(v) for k, v in self.domains.items()},
            "agents": {k: self._encode(v) for k, v in self.agents.items()},
            "states": {k: self._encode(v) for k, v in self.state.states.items()},
            "active_versions": self.state.active_versions,
            "snapshots": {k: self._encode(v) for k, v in self.state.snapshots.items()},
            "branches": {k: self._encode(v) for k, v in self.state.branches.items()},
            "history": {k: self._encode(v) for k, v in self.history.entries.items()},
            "sequestered": {k: self._encode(v) for k, v in self.history.sequestered.items()},
            "audit": [self._encode(v) for v in self.audit.entries],
            "permissions": [self._encode(v) for v in self.authorization.permissions],
            "cross_context_grants": {k: self._encode(v) for k, v in self.authorization.grants.items()},
            "eligibility": {f"{k[0]}::{k[1]}": self._encode(v) for k, v in self.eligibility.items()},
            "acknowledgements": {k: self._encode(v) for k, v in self.acknowledgements.items()},
            "transfers": {k: self._encode(v) for k, v in self.transfers.items()},
            "conversations": {k: self._encode(v) for k, v in self.conversations.items()},
            "indexes": {
                tid: {
                    "table_id": idx.table_id,
                    "mode": idx.mode.value,
                    "entries": {
                        k: [self._encode(e) for e in values]
                        for k, values in idx.entries.items()
                    },
                } for tid, idx in self.indexes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Commons":
        # Load the major persistent structures. Enums are restored explicitly.
        c = cls()
        for pid, v in data.get("participants", {}).items():
            v["participant_type"] = ParticipantType(v["participant_type"])
            if v.get("model_identity"):
                v["model_identity"] = ModelIdentity(**v["model_identity"])
            c.participants[pid] = Participant(**v)
        for rid, v in data.get("roles", {}).items():
            v["capabilities"] = set(v.get("capabilities", []))
            c.roles[rid] = RoleDefinition(**v)
        for v in data.get("role_assignments", []):
            c.role_assignments.append(RoleAssignment(**v))
        for tid, v in data.get("tables", {}).items():
            v["participants"] = set(v.get("participants", []))
            v["permissions"] = set(v.get("permissions", []))
            v["context_mode"] = ContextMode(v.get("context_mode", "ISOLATED"))
            c.tables[tid] = Table(**v)
            c.indexes[tid] = ScopedIndex(tid, c.tables[tid].context_mode)
        for aid, v in data.get("agents", {}).items():
            c.agents[aid] = LocalAgent(**v)
        for sid, v in data.get("states", {}).items():
            v["policy"]["classification"] = DataClassification(v["policy"]["classification"])
            v["policy"] = DataPolicy(**v["policy"])
            c.state.states[sid] = StateRecord(**v)
        c.state.active_versions = dict(data.get("active_versions", {}))
        for k, v in data.get("snapshots", {}).items():
            c.state.snapshots[k] = Snapshot(**v)
        for k, v in data.get("branches", {}).items():
            c.state.branches[k] = Branch(**v)
        for k, v in data.get("history", {}).items():
            c.history.entries[k] = HistoryEntry(**v)
        for k, v in data.get("sequestered", {}).items():
            c.history.sequestered[k] = SequesteredRecord(**v)
        for v in data.get("permissions", []):
            c.authorization.permissions.append(PermissionRecord(**v))
        for k, v in data.get("cross_context_grants", {}).items():
            v["operations"] = set(v.get("operations", []))
            v["data_classification"] = set(v.get("data_classification", []))
            v["authorization"] = AuthorizationState(v.get("authorization", "AUTHORIZED"))
            c.authorization.grants[k] = CrossContextGrant(**v)
        return c

    @staticmethod
    def _encode(obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return {k: Commons._encode(v) for k, v in asdict(obj).items()}
        if isinstance(obj, dict):
            return {str(k): Commons._encode(v) for k, v in obj.items()}
        if isinstance(obj, (set, tuple, list)):
            return [Commons._encode(v) for v in obj]
        return obj


# ---------------------------------------------------------------------------
# Bootstrap / self-test
# ---------------------------------------------------------------------------

def create_default_admin(commons: Commons) -> Participant:
    admin = Participant("SYSTEM_ADMIN", ParticipantType.HUMAN, {"administration": True})
    commons.add_participant(admin)
    commons.authorization.issue_system_privilege(
        "SYSTEM_ADMIN", "IDENTITY_NAME", "*", "SYSTEM"
    )
    return admin


def self_test() -> Dict[str, Any]:
    c = Commons()
    admin = create_default_admin(c)

    table = c.create_table(admin.participant_id, "Test Table")
    c.authorization.issue_system_privilege(
        admin.participant_id, "RECALL", table.table_id, "SYSTEM"
    )
    c.authorization.issue_system_privilege(
        admin.participant_id, "ROLLBACK", table.table_id, "SYSTEM"
    )

    policy = DataPolicy(admin.participant_id, DataClassification.PRIVATE)
    s = c.state.create_state(
        table.table_id, "conversation", "generic-v1",
        {"messages": ["one"]}, policy, admin.participant_id
    )
    v1 = c.state.current_version_id(s.state_id)

    # Normal mutation creates a second immutable historical version.
    state = c.state.states[s.state_id]
    state.version += 1
    state.data = {"messages": ["one", "two"]}
    state.refresh_integrity()
    v2 = c.state._record_version(state, table.table_id, admin.participant_id, "WRITE")
    c.state.active_versions[s.state_id] = v2

    recalled_status, recalled = c.state.recall_ver(
        admin.participant_id, table.table_id, v1
    )
    assert recalled_status == "VERSION_FOUND"
    assert recalled is not None

    result = c.state.rollback(
        admin.participant_id, table.table_id, s.state_id, v1,
        expected_current_version_id=v2
    )
    assert result["status"] == "ROLLBACK_SUCCESS"
    assert c.history.get(v1) is not None
    assert len(c.state.branches) == 1
    assert c.state.current(s.state_id).data == {"messages": ["one"]}

    return {
        "passed": True,
        "status": c.status(),
        "rollback": result,
        "recall_status": recalled_status,
    }


def main() -> None:
    print(json.dumps(self_test(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
