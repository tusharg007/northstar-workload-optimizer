import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Shield,
  User,
} from 'lucide-react';
import { getExpenses, submitDecisionViaWebhook } from '../lib/api';
import type { ExpenseState } from '../types';
import { STATUS_COLORS, RISK_COLORS } from '../types';
import { formatCurrency, formatDate, humanizeStatus, cn } from '../lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorAlert } from '@/components/ui/error-alert';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useEventStream } from '../hooks/useEventStream';

function SelectionCheckbox({
  checked,
  indeterminate = false,
  onChange,
  label,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  const checkboxRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (checkboxRef.current) checkboxRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={checkboxRef}
      type="checkbox"
      checked={checked}
      onChange={event => onChange(event.target.checked)}
      aria-label={label}
      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800"
    />
  );
}

export default function Approvals() {
  const [expenses, setExpenses] = useState<ExpenseState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkApproving, setBulkApproving] = useState(false);
  const expandedIdRef = useRef<string | null>(null);

  const fetchApprovals = async (force = false) => {
    try {
      if (expandedIdRef.current && !force) return;
      
      const [pending, escalated] = await Promise.all([
        getExpenses('PENDING_APPROVAL'),
        getExpenses('ESCALATED'),
      ]);
      const combined = [...pending, ...escalated];
      setExpenses(combined);
      setSelectedIds(current => new Set(
        [...current].filter(id => combined.some(expense => expense.expense_id === id)),
      ));
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch approvals');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchApprovals();
    const interval = setInterval(() => void fetchApprovals(), 5000);
    return () => clearInterval(interval);
  }, []);

  useEventStream(event => {
    if (event.type === 'expense_updated') {
      void fetchApprovals(true);
    }
  });

  const allSelected = expenses.length > 0 && expenses.every(expense => selectedIds.has(expense.expense_id));
  const someSelected = selectedIds.size > 0 && !allSelected;

  const toggleAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(expenses.map(expense => expense.expense_id)));
  };

  const toggleSelected = (expenseId: string, selected: boolean) => {
    setSelectedIds(current => {
      const next = new Set(current);
      if (selected) next.add(expenseId);
      else next.delete(expenseId);
      return next;
    });
  };

  const approveSelected = async () => {
    const selected = expenses.filter(expense => selectedIds.has(expense.expense_id));
    if (selected.length === 0) return;
    if (!window.confirm(`Approve ${selected.length} expenses? This cannot be undone.`)) return;

    setBulkApproving(true);
    const approvedIds = new Set<string>();
    let successCount = 0;

    for (const expense of selected) {
      try {
        await submitDecisionViaWebhook(expense.expense_id, {
          decision: 'approve',
          approver: 'Batch Approval',
          comment: 'Bulk approved',
        });
        approvedIds.add(expense.expense_id);
        successCount += 1;
      } catch (err) {
        console.error(`Failed to bulk approve ${expense.expense_id}`, err);
      }
    }

    setExpenses(current => current.filter(expense => !approvedIds.has(expense.expense_id)));
    setSelectedIds(current => new Set([...current].filter(id => !approvedIds.has(id))));
    toast.success(`${successCount} of ${selected.length} approved`);
    setBulkApproving(false);
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Approval Inbox</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            {expenses.length} {expenses.length === 1 ? 'item' : 'items'} pending review
          </p>
        </div>
        {expenses.length > 0 && (
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            <SelectionCheckbox
              checked={allSelected}
              indeterminate={someSelected}
              onChange={toggleAll}
              label="Select all approval items"
            />
            Select All
          </label>
        )}
      </div>

      {error && <ErrorAlert message={error} onRetry={() => void fetchApprovals()} />}

      {loading && expenses.length === 0 ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full rounded-lg" />
          ))}
        </div>
      ) : expenses.length === 0 ? (
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-12 text-center shadow-sm">
          <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h3 className="text-xl font-medium text-gray-900 dark:text-gray-100 mb-2">All Caught Up!</h3>
          <p className="text-gray-500 dark:text-gray-400">There are no expenses waiting for your approval right now.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {expenses.map((expense) => (
            <ApprovalCard
              key={expense.expense_id}
              expense={expense}
              expandedIdRef={expandedIdRef}
              selected={selectedIds.has(expense.expense_id)}
              onSelectedChange={selected => toggleSelected(expense.expense_id, selected)}
              onDecided={() => {
                setExpenses(current => current.filter(e => e.expense_id !== expense.expense_id));
                toggleSelected(expense.expense_id, false);
              }}
            />
          ))}
        </div>
      )}

      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 right-6 z-40">
          <Button
            type="button"
            onClick={approveSelected}
            disabled={bulkApproving}
            className="bg-green-600 shadow-lg hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600"
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            {bulkApproving ? 'Approving...' : `Approve Selected (${selectedIds.size})`}
          </Button>
        </div>
      )}
    </div>
  );
}

function ApprovalCard({
  expense,
  onDecided,
  expandedIdRef,
  selected,
  onSelectedChange,
}: {
  expense: ExpenseState;
  onDecided: () => void;
  expandedIdRef: React.MutableRefObject<string | null>;
  selected: boolean;
  onSelectedChange: (selected: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [approver, setApprover] = useState('Finance Director');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleExpanded = () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    if (newExpanded) {
      expandedIdRef.current = expense.expense_id;
    } else if (expandedIdRef.current === expense.expense_id) {
      expandedIdRef.current = null;
    }
  };

  const handleDecision = async (decision: 'approve' | 'reject') => {
    try {
      setSubmitting(true);
      setError(null);
      await submitDecisionViaWebhook(expense.expense_id, {
        decision,
        approver,
        comment,
      });
      toast.success(decision === 'approve' ? 'Expense approved!' : 'Expense rejected!');
      expandedIdRef.current = null;
      onDecided();
    } catch (err: any) {
      const msg = err.message || `Failed to ${decision} expense`;
      setError(msg);
      toast.error(msg);
      setSubmitting(false);
    }
  };

  const p = expense.input_payload;

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm overflow-hidden transition-all">
      <div
        className="p-5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center justify-between"
        onClick={toggleExpanded}
      >
        <div
          className="mr-4 flex-shrink-0"
          onClick={event => event.stopPropagation()}
        >
          <SelectionCheckbox
            checked={selected}
            onChange={onSelectedChange}
            label={`Select expense ${expense.expense_id}`}
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', STATUS_COLORS[expense.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
              {humanizeStatus(expense.status)}
            </span>
            <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium flex items-center gap-1', RISK_COLORS[expense.risk_level ?? ''] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
              <Shield className="w-3 h-3" />
              {expense.risk_level || 'N/A'} RISK
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400 font-mono">{expense.expense_id.substring(0, 8)}...</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Employee</p>
              <p className="font-medium text-gray-900 dark:text-gray-100 truncate">{p.employee_name}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{p.department}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Amount</p>
              <p className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(p.amount)}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{p.currency}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Details</p>
              <p className="font-medium text-gray-900 dark:text-gray-100 truncate">{p.merchant}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{p.category}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Date</p>
              <p className="font-medium text-gray-900 dark:text-gray-100">{formatDate(p.transaction_date)}</p>
            </div>
          </div>

          {expense.anomaly_flags && expense.anomaly_flags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {expense.anomaly_flags.map((flag, idx) => (
                <span key={idx} className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-100 dark:border-red-800">
                  <AlertTriangle className="w-3 h-3" />
                  {flag}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="ml-4 flex-shrink-0">
          {expanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 pt-2 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/20">
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Description</h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 p-3 rounded border border-gray-200 dark:border-gray-800">
              {p.description || 'No description provided.'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Approver Role / Name</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User className="h-4 w-4 text-gray-400" />
                </div>
                <input
                  type="text"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  className="pl-10 block w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-900 dark:text-gray-100"
                  disabled={submitting}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Assigned Role</label>
              <div className="p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-md text-sm text-gray-700 dark:text-gray-300 flex items-center gap-2">
                <Shield className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
                {expense.approver_role || 'Manager'}
              </div>
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Decision Comment</label>
            <textarea
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="block w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-900 dark:text-gray-100"
              placeholder="Add your review notes here..."
              disabled={submitting}
            />
          </div>

          <div className="flex justify-end gap-3">
            <Button asChild variant="outline">
              <Link to={`/expenses/${expense.expense_id}`}>View Full Details</Link>
            </Button>
            <button
              onClick={() => handleDecision('reject')}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-4 py-2 border border-transparent text-sm font-medium rounded-md text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 transition-colors"
            >
              <XCircle className="w-4 h-4" />
              Reject
            </button>
            <button
              onClick={() => handleDecision('approve')}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 transition-colors"
            >
              {submitting ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              ) : (
                <CheckCircle className="w-4 h-4" />
              )}
              Approve
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
