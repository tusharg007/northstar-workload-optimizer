import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Shield,
  User,
  AlertCircle
} from 'lucide-react';
import { getExpenses, submitDecisionViaWebhook } from '../lib/api';
import type { ExpenseState } from '../types';
import { STATUS_COLORS, RISK_COLORS } from '../types';
import { formatCurrency, formatDate, humanizeStatus, cn } from '../lib/utils';

export default function Approvals() {
  const [expenses, setExpenses] = useState<ExpenseState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchApprovals = async () => {
    try {
      const [pending, escalated] = await Promise.all([
        getExpenses('PENDING_APPROVAL'),
        getExpenses('ESCALATED'),
      ]);
      // Sort by created_at desc roughly or just concatenate
      const combined = [...pending, ...escalated];
      // deduplicate if necessary, though status should be mutually exclusive
      setExpenses(combined);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch approvals');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
    const interval = setInterval(fetchApprovals, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Approval Inbox</h1>
        <p className="text-gray-500 mt-2">
          {expenses.length} {expenses.length === 1 ? 'item' : 'items'} pending review
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 text-red-700 rounded-md flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
        </div>
      )}

      {loading && expenses.length === 0 ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : expenses.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center shadow-sm">
          <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h3 className="text-xl font-medium text-gray-900 mb-2">All Caught Up!</h3>
          <p className="text-gray-500">There are no expenses waiting for your approval right now.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {expenses.map((expense) => (
            <ApprovalCard
              key={expense.expense_id}
              expense={expense}
              onDecided={() => {
                setExpenses(expenses.filter(e => e.expense_id !== expense.expense_id));
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalCard({ expense, onDecided }: { expense: ExpenseState, onDecided: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [approver, setApprover] = useState('Finance Director');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDecision = async (decision: 'approve' | 'reject') => {
    try {
      setSubmitting(true);
      setError(null);
      await submitDecisionViaWebhook(expense.expense_id, {
        decision,
        approver,
        comment,
      });
      onDecided();
    } catch (err: any) {
      setError(err.message || `Failed to ${decision} expense`);
      setSubmitting(false);
    }
  };

  const p = expense.input_payload;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden transition-all">
      <div
        className="p-5 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', STATUS_COLORS[expense.status] || 'bg-gray-100 text-gray-800')}>
              {humanizeStatus(expense.status)}
            </span>
            <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium flex items-center gap-1', RISK_COLORS[expense.risk_level ?? ''] || 'bg-gray-100 text-gray-800')}>
              <Shield className="w-3 h-3" />
              {expense.risk_level || 'N/A'} RISK
            </span>
            <span className="text-sm text-gray-500 font-mono">{expense.expense_id.substring(0, 8)}...</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
            <div>
              <p className="text-sm text-gray-500">Employee</p>
              <p className="font-medium text-gray-900 truncate">{p.employee_name}</p>
              <p className="text-xs text-gray-500">{p.department}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Amount</p>
              <p className="font-medium text-gray-900">{formatCurrency(p.amount)}</p>
              <p className="text-xs text-gray-500">{p.currency}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Details</p>
              <p className="font-medium text-gray-900 truncate">{p.merchant}</p>
              <p className="text-xs text-gray-500 truncate">{p.category}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Date</p>
              <p className="font-medium text-gray-900">{formatDate(p.transaction_date)}</p>
            </div>
          </div>

          {expense.anomaly_flags && expense.anomaly_flags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {expense.anomaly_flags.map((flag, idx) => (
                <span key={idx} className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-100">
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
        <div className="px-5 pb-5 pt-2 border-t border-gray-100 bg-gray-50">
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-900 mb-1">Description</h4>
            <p className="text-sm text-gray-700 bg-white p-3 rounded border border-gray-200">
              {p.description || 'No description provided.'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Approver Role / Name</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User className="h-4 w-4 text-gray-400" />
                </div>
                <input
                  type="text"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  className="pl-10 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white"
                  disabled={submitting}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Assigned Role</label>
              <div className="p-2 bg-white border border-gray-200 rounded-md text-sm text-gray-700 flex items-center gap-2">
                <Shield className="h-4 w-4 text-indigo-500" />
                {expense.approver_role || 'Manager'}
              </div>
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Decision Comment</label>
            <textarea
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white"
              placeholder="Add your review notes here..."
              disabled={submitting}
            />
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={() => handleDecision('reject')}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-4 py-2 border border-transparent text-sm font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" />
              Reject
            </button>
            <button
              onClick={() => handleDecision('approve')}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50"
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
