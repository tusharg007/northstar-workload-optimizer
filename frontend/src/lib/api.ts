/* ──────────────────────────────────────────────────────────────
   North Star Frontend — API Client
   Typed fetch wrappers for the FastAPI backend.
   In Docker, requests go through nginx reverse proxy.
   In dev, Vite proxy handles the forwarding.
   ────────────────────────────────────────────────────────────── */

import type {
  ExpenseSubmission,
  ExpenseState,
  Explanation,
  Lineage,
  ProvenanceView,
  VerifyResult,
  DecisionTrace,
  DecisionRequest,
  PolicySummary,
  PolicyVersion,
  TermSummary,
  TermVersion,
  HealthResponse,
} from '../types';
import { toast } from 'sonner';

// When served through nginx or Vite proxy, use relative paths.
// The proxy handles routing /api/* to FastAPI and /webhook/* to n8n.
const API_BASE = import.meta.env.VITE_API_BASE || '';
const N8N_BASE = import.meta.env.VITE_N8N_BASE || '';

// ── Helpers ─────────────────────────────────────────────────

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 429) {
      toast.warning('Rate limited. Please wait a moment.');
    }
    const body = await res.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail
        ? typeof parsed.detail === 'string'
          ? parsed.detail
          : JSON.stringify(parsed.detail, null, 2)
        : body;
    } catch {
      // keep raw text
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── Health ───────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  return fetchJSON(`${API_BASE}/health`);
}

// ── Expense Operations ──────────────────────────────────────

export async function submitExpenseViaWebhook(
  payload: ExpenseSubmission,
  idempotencyKey: string,
): Promise<ExpenseState> {
  return fetchJSON(`${N8N_BASE}/webhook/northstar-expense`, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: { 'Idempotency-Key': idempotencyKey },
    signal: AbortSignal.timeout(15_000),
  });
}

export async function submitExpenseDirect(
  payload: ExpenseSubmission,
  idempotencyKey?: string,
): Promise<ExpenseState> {
  const headers: Record<string, string> = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return fetchJSON(`${API_BASE}/api/expenses/process`, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers,
  });
}

export async function submitExpense(
  payload: ExpenseSubmission,
): Promise<ExpenseState> {
  const idempotencyKey = `northstar:frontend:expense:${payload.expense_id}`;
  return submitExpenseViaWebhook(payload, idempotencyKey);
}

export async function getExpenses(
  status?: string,
): Promise<ExpenseState[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return fetchJSON(`${API_BASE}/api/expenses${qs}`);
}

export async function getExpense(id: string): Promise<ExpenseState> {
  return fetchJSON(`${API_BASE}/api/expenses/${encodeURIComponent(id)}`);
}

export async function getExplanation(id: string): Promise<Explanation> {
  return fetchJSON(
    `${API_BASE}/api/expenses/${encodeURIComponent(id)}/explanation`,
  );
}

export async function getLineage(id: string): Promise<Lineage> {
  return fetchJSON(
    `${API_BASE}/api/expenses/${encodeURIComponent(id)}/lineage`,
  );
}

// ── Decisions ───────────────────────────────────────────────

export async function submitDecision(
  expenseId: string,
  decision: DecisionRequest,
): Promise<ExpenseState> {
  return fetchJSON(
    `${API_BASE}/api/expenses/${encodeURIComponent(expenseId)}/decision`,
    { method: 'POST', body: JSON.stringify(decision) },
  );
}

export async function submitDecisionViaWebhook(
  expenseId: string,
  decision: DecisionRequest,
): Promise<ExpenseState> {
  return fetchJSON(`${N8N_BASE}/webhook/northstar-approval`, {
    method: 'POST',
    body: JSON.stringify({
      expense_id: expenseId,
      decision: decision.decision,
      approver: decision.approver,
      comment: decision.comment,
    }),
  });
}

// ── Provenance ──────────────────────────────────────────────

export async function getProvenance(
  expenseId: string,
): Promise<ProvenanceView> {
  return fetchJSON(
    `${API_BASE}/api/provenance/expenses/${encodeURIComponent(expenseId)}`,
  );
}

export async function verifyProvenance(
  provenanceId: string,
): Promise<VerifyResult> {
  return fetchJSON(
    `${API_BASE}/api/provenance/decisions/${encodeURIComponent(provenanceId)}/verify`,
  );
}

export async function getDecisionTrace(
  expenseId: string,
): Promise<DecisionTrace> {
  return fetchJSON(
    `${API_BASE}/api/provenance/expenses/${encodeURIComponent(expenseId)}/trace`,
  );
}

// ── Governed Context ────────────────────────────────────────

export async function getPolicies(): Promise<PolicySummary[]> {
  return fetchJSON(`${API_BASE}/api/context/policies`);
}

export async function getPolicyVersions(
  policyKey: string,
): Promise<PolicyVersion[]> {
  return fetchJSON(
    `${API_BASE}/api/context/policies/${encodeURIComponent(policyKey)}/versions`,
  );
}

export async function getTerms(): Promise<TermSummary[]> {
  return fetchJSON(`${API_BASE}/api/context/terms`);
}

export async function getTermVersions(
  termKey: string,
): Promise<TermVersion[]> {
  return fetchJSON(
    `${API_BASE}/api/context/terms/${encodeURIComponent(termKey)}/versions`,
  );
}

// ── Internal / Reliability (for System Health page) ─────────

export async function getDeadLetterEvents(): Promise<unknown[]> {
  return fetchJSON(`${API_BASE}/api/internal/outbox/dead-letter`);
}

export async function getWorkflowFailures(): Promise<unknown[]> {
  return fetchJSON(`${API_BASE}/api/internal/workflow-failures?status=OPEN`);
}
