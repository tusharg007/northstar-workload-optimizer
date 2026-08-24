/* ──────────────────────────────────────────────────────────────
   North Star Frontend — Shared TypeScript Types
   Maps directly to FastAPI response schemas.
   ────────────────────────────────────────────────────────────── */

// ── Expense ─────────────────────────────────────────────────

export interface ExpenseSubmission {
  expense_id: string;
  employee_id: string;
  employee_name: string;
  department: string;
  transaction_date: string;
  merchant: string;
  category: string;
  description: string;
  amount: number;
  currency: string;
  payment_method: string;
  receipt_attached: boolean;
}

export interface AnomalyResult {
  is_anomalous: boolean;
  confidence_score: number;
  risk_level: string;
  flags: string[];
}

export interface DecisionResult {
  approver_role: string;
  approver_level: number;
  auto_approved: boolean;
  requires_review: boolean;
  reason: string;
}

export interface ValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface ProcessingResult {
  status: string;
  validation: ValidationResult;
  anomaly: AnomalyResult;
  decision: DecisionResult;
  notification?: Record<string, unknown>;
  policy_evaluations?: Array<Record<string, unknown>>;
  risk_evaluations?: Array<Record<string, unknown>>;
}

export interface ExpenseState {
  expense_id: string;
  input_payload: ExpenseSubmission;
  result: ProcessingResult;
  status: ExpenseStatus;
  risk_level: RiskLevel | null;
  approver_role: string | null;
  decision: string | null;
  decided_by: string | null;
  decision_comment: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
  anomaly_flags: string[];
  message: string;
}

export type ExpenseStatus =
  | 'AUTO_APPROVED'
  | 'PENDING_APPROVAL'
  | 'ESCALATED'
  | 'APPROVED'
  | 'REJECTED'
  | 'REJECTED_VALIDATION';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// ── Explanation ─────────────────────────────────────────────

export interface Explanation {
  expense_id: string;
  status: string;
  risk_level: string;
  anomaly_flags: string[];
  routing_decision: Record<string, unknown>;
  approver: string;
  reason: string;
  provenance_id: string | null;
  provenance_hash: string | null;
  evidence_verified: boolean | null;
}

// ── Lineage ─────────────────────────────────────────────────

export interface LineageEvent {
  source: string;
  event_type: string;
  timestamp: string;
  status: string;
  sequence: number | null;
}

export interface Lineage {
  expense_id: string;
  correlation_id: string;
  workflow_run_id: string;
  events: LineageEvent[];
}

// ── Provenance ──────────────────────────────────────────────

export interface ProvenanceView {
  provenance_id: string;
  expense_id: string;
  workflow_run_id: string;
  correlation_id: string;
  source_payload_hash: string;
  context_as_of: string;
  context_resolved_at: string;
  automated_status: string;
  risk_level: string;
  context_trust_state: string;
  decision_engine_version: string;
  risk_engine_version: string;
  provenance_hash: string;
  policies: Array<Record<string, unknown>>;
  terms: Array<Record<string, unknown>>;
  rules: Array<Record<string, unknown>>;
  trust: Array<Record<string, unknown>>;
  risk: Array<Record<string, unknown>>;
  human_decisions: Array<Record<string, unknown>>;
}

export interface VerifyResult {
  provenance_id: string;
  status: 'PASS' | 'FAIL';
  stored_hash: string;
  recomputed_hash: string;
  failures: string[];
}

export interface DecisionTrace {
  provenance_id: string;
  expense_id: string;
  automated_decision: Record<string, unknown>;
  human_decision: Record<string, unknown> | null;
  context_snapshot: Record<string, unknown>;
  rule_evaluations: Array<Record<string, unknown>>;
  risk_signals: Array<Record<string, unknown>>;
}

// ── Context ─────────────────────────────────────────────────

export interface PolicySummary {
  policy_id: string;
  policy_key: string;
  policy_name: string;
  domain: string;
  description: string;
  owner: ContextOwner;
  version_count: number;
}

export interface PolicyVersion {
  policy_version_id: string;
  version_number: number;
  status: string;
  effective_from: string;
  effective_to: string | null;
  certified_at: string | null;
  content_hash: string;
  rules: PolicyRule[];
}

export interface PolicyRule {
  policy_rule_id: string;
  rule_key: string;
  rule_name: string;
  description: string;
  rule_type: string;
  parameters: Record<string, unknown>;
}

export interface TermSummary {
  business_term_id: string;
  term_key: string;
  canonical_name: string;
  domain: string;
  owner: ContextOwner;
  version_count: number;
}

export interface TermVersion {
  term_version_id: string;
  version_number: number;
  status: string;
  definition: string;
  effective_from: string;
  effective_to: string | null;
  certified_at: string | null;
  content_hash: string;
}

export interface ContextOwner {
  owner_id: string;
  owner_key: string;
  display_name: string;
  owner_type: string;
  domain: string;
  active: boolean;
}

// ── Health ───────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  service?: string;
}

// ── Decision ────────────────────────────────────────────────

export interface DecisionRequest {
  decision: 'approve' | 'reject';
  approver: string;
  comment: string;
}

// ── Constants ───────────────────────────────────────────────

export const DEPARTMENTS = [
  'Sales', 'IT', 'Marketing', 'Finance', 'HR', 'Operations',
] as const;

export const CATEGORIES = [
  'Travel',
  'Meals & Entertainment',
  'Office Supplies',
  'Software & Subscriptions',
  'Training & Development',
  'Client Entertainment',
  'Transportation',
  'Telecommunications',
  'Equipment',
  'Miscellaneous',
] as const;

export const STATUS_COLORS: Record<string, string> = {
  AUTO_APPROVED: 'bg-green-100 text-green-800',
  PENDING_APPROVAL: 'bg-amber-100 text-amber-800',
  ESCALATED: 'bg-red-100 text-red-800',
  APPROVED: 'bg-blue-100 text-blue-800',
  REJECTED: 'bg-gray-100 text-gray-800',
  REJECTED_VALIDATION: 'bg-rose-100 text-rose-800',
};

export const RISK_COLORS: Record<string, string> = {
  LOW: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  HIGH: 'bg-orange-100 text-orange-700',
  CRITICAL: 'bg-red-100 text-red-700',
};
