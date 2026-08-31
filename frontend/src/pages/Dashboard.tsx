import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileText,
  CheckCircle,
  Clock,
  AlertTriangle,
  ThumbsUp,
} from 'lucide-react';
import { getExpenses } from '../lib/api';
import { ExpenseState, STATUS_COLORS, RISK_COLORS } from '../types';
import { formatCurrency, formatDate, cn, humanizeStatus } from '../lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorAlert } from '@/components/ui/error-alert';
import { EmptyState } from '@/components/ui/empty-state';
import { toast } from 'sonner';

export default function Dashboard() {
  const [expenses, setExpenses] = useState<ExpenseState[]>([]);
  const [filter, setFilter] = useState<string>('ALL');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const fetchExpenses = async () => {
    try {
      setError(null);
      const data = await getExpenses();
      setExpenses(data);
    } catch (err: any) {
      console.error('Failed to fetch expenses', err);
      setError(err.message || 'Failed to fetch expenses');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchExpenses();
    const interval = setInterval(fetchExpenses, 5000);
    return () => clearInterval(interval);
  }, []);

  const total = expenses.length;
  const autoApproved = expenses.filter(e => e.status === 'AUTO_APPROVED').length;
  const pendingReview = expenses.filter(
    e => e.status === 'PENDING_APPROVAL' || e.status === 'ESCALATED'
  ).length;
  const escalated = expenses.filter(e => e.status === 'ESCALATED').length;
  const approved = expenses.filter(e => e.status === 'APPROVED').length;
  const rejectedVal = expenses.filter(e => e.status === 'REJECTED_VALIDATION').length;
  const rejected = expenses.filter(e => e.status === 'REJECTED').length;

  const filteredExpenses =
    filter === 'ALL'
      ? expenses
      : expenses.filter(e => e.status === filter);

  const TABS = [
    { id: 'ALL', label: 'All', count: total },
    { id: 'PENDING_APPROVAL', label: humanizeStatus('PENDING_APPROVAL'), count: expenses.filter(e => e.status === 'PENDING_APPROVAL').length },
    { id: 'ESCALATED', label: humanizeStatus('ESCALATED'), count: escalated },
    { id: 'AUTO_APPROVED', label: humanizeStatus('AUTO_APPROVED'), count: autoApproved },
    { id: 'APPROVED', label: humanizeStatus('APPROVED'), count: approved },
    { id: 'REJECTED', label: humanizeStatus('REJECTED'), count: rejected },
    { id: 'REJECTED_VALIDATION', label: humanizeStatus('REJECTED_VALIDATION'), count: rejectedVal },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Operations Overview</h1>
      </div>

      {error && <ErrorAlert message={error} onRetry={fetchExpenses} />}

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {isLoading && expenses.length === 0 ? (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : (
          <>
            <div className="bg-white dark:bg-gray-900 p-4 rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 flex items-center space-x-4">
              <div className="p-3 bg-blue-50 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400 rounded-full">
                <FileText size={24} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Expenses</p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{total}</p>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-900 p-4 rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 flex items-center space-x-4">
              <div className="p-3 bg-green-50 dark:bg-green-900/50 text-green-600 dark:text-green-400 rounded-full">
                <CheckCircle size={24} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Auto-Approved</p>
                <div className="flex items-baseline space-x-2">
                  <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{autoApproved}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {total > 0 ? Math.round((autoApproved / total) * 100) : 0}%
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-900 p-4 rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 flex items-center space-x-4">
              <div className="p-3 bg-amber-50 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400 rounded-full">
                <Clock size={24} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Pending Review</p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{pendingReview}</p>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-900 p-4 rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 flex items-center space-x-4">
              <div className="p-3 bg-red-50 dark:bg-red-900/50 text-red-600 dark:text-red-400 rounded-full">
                <AlertTriangle size={24} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Escalated</p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{escalated}</p>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-900 p-4 rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 flex items-center space-x-4">
              <div className="p-3 bg-indigo-50 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 rounded-full">
                <ThumbsUp size={24} />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Approved</p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{approved}</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800">
        <nav className="-mb-px flex space-x-6 overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={cn(
                'whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm',
                filter === tab.id
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              )}
            >
              {tab.label} ({tab.count})
            </button>
          ))}
        </nav>
      </div>

      {/* Table */}
      {!isLoading && expenses.length === 0 ? (
        <EmptyState 
          icon={FileText} 
          title='No expenses found' 
          description='Submit your first expense to get started.' 
          actionLabel='Submit Expense' 
          onAction={() => navigate('/submit')} 
        />
      ) : (
        <div className="bg-white dark:bg-gray-900 shadow-sm rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
              <thead className="bg-gray-50 dark:bg-gray-800/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    ID & Employee
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Category
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Risk
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="relative px-6 py-3">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={7} className="px-6 py-4">
                        <Skeleton className="h-8 w-full" />
                      </td>
                    </tr>
                  ))
                ) : filteredExpenses.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                      No expenses found in this view.
                    </td>
                  </tr>
                ) : (
                  filteredExpenses.map(expense => (
                    <tr key={expense.expense_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {expense.input_payload.employee_name}
                        </div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {expense.expense_id}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {expense.input_payload.category}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100">
                        {formatCurrency(expense.input_payload.amount)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={cn(
                            'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                            RISK_COLORS[expense.risk_level ?? ''] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
                          )}
                        >
                          {expense.risk_level || 'N/A'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={cn(
                            'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                            STATUS_COLORS[expense.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
                          )}
                        >
                          {humanizeStatus(expense.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(expense.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          to={`/expenses/${expense.expense_id}`}
                          className="text-indigo-600 hover:text-indigo-900 dark:text-indigo-400 dark:hover:text-indigo-300"
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
