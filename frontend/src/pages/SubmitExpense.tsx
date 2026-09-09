import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Coffee, Plane, ShieldAlert, CalendarX, ArrowRight, CheckCircle2, XCircle, AlertTriangle, Loader2, MessageCircleQuestion } from 'lucide-react';
import { submitExpense } from '../lib/api';
import { ExpenseSubmission, DEPARTMENTS, CATEGORIES, ExpenseState, STATUS_COLORS, RISK_COLORS } from '../types';
import { cn, humanizeStatus, formatCurrency } from '../lib/utils';
import { ErrorAlert } from '@/components/ui/error-alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

export default function SubmitExpense() {
  const [formData, setFormData] = useState<ExpenseSubmission>({
    expense_id: '',
    employee_id: '',
    employee_name: '',
    department: 'Sales',
    transaction_date: new Date().toISOString().split('T')[0],
    merchant: '',
    category: 'Travel',
    description: '',
    amount: 0,
    currency: 'USD',
    payment_method: 'Corporate Card',
    receipt_attached: true,
  });

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ExpenseState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [policyQuery, setPolicyQuery] = useState('');
  const [policyAnswer, setPolicyAnswer] = useState('');
  const [copilotError, setCopilotError] = useState<string | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    const val = type === 'number' ? parseFloat(value) : value;
    setFormData(prev => ({ ...prev, [name]: val }));
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: checked }));
  };

  const loadPreset = (preset: 'coffee' | 'travel' | 'suspicious' | 'invalid') => {
    const randomSuffix = crypto.randomUUID();
    let data: ExpenseSubmission;
    const today = new Date();

    if (preset === 'coffee') {
      data = {
        expense_id: `DEMO-COFFEE-${randomSuffix}`,
        employee_id: 'EMP-101',
        employee_name: 'Avery Morgan',
        department: 'Operations',
        category: 'Meals & Entertainment',
        amount: 28.50,
        merchant: 'Campus Coffee',
        description: 'Team coffee meeting',
        transaction_date: today.toISOString().split('T')[0],
        payment_method: 'Corporate Card',
        receipt_attached: true,
        currency: 'USD',
      };
    } else if (preset === 'travel') {
      const weekdayDate = new Date();
      if (weekdayDate.getUTCDay() === 0 || weekdayDate.getUTCDay() === 6) {
        weekdayDate.setUTCDate(weekdayDate.getUTCDate() - (weekdayDate.getUTCDay() === 0 ? 2 : 1));
      }
      data = {
        expense_id: `DEMO-TRAVEL-${randomSuffix}`,
        employee_id: 'EMP-101',
        employee_name: 'Avery Morgan',
        department: 'Operations',
        category: 'Travel',
        amount: 640,
        merchant: 'Regional Air',
        description: 'Client site travel',
        transaction_date: weekdayDate.toISOString().split('T')[0],
        payment_method: 'Corporate Card',
        receipt_attached: true,
        currency: 'USD',
      };
    } else if (preset === 'suspicious') {
      const sat = new Date();
      sat.setUTCDate(sat.getUTCDate() - ((sat.getUTCDay() + 1) % 7));
      data = {
        expense_id: `DEMO-SUSPICIOUS-${randomSuffix}`,
        employee_id: 'EMP-042',
        employee_name: 'Jordan Lee',
        department: 'IT',
        category: 'Software & Subscriptions',
        amount: 3000,
        merchant: 'Cloud Vendor',
        description: 'DUPLICATE annual platform renewal',
        transaction_date: sat.toISOString().split('T')[0],
        payment_method: 'Corporate Card',
        receipt_attached: false,
        currency: 'USD',
      };
    } else {
      const future = new Date();
      future.setUTCDate(future.getUTCDate() + 30);
      data = {
        expense_id: `DEMO-INVALID-${randomSuffix}`,
        employee_id: 'EMP-099',
        employee_name: 'Test User',
        department: 'Finance',
        category: 'Office Supplies',
        amount: 50,
        merchant: 'Office Depot',
        description: 'Office supplies',
        transaction_date: future.toISOString().split('T')[0],
        payment_method: 'Corporate Card',
        receipt_attached: true,
        currency: 'USD',
      };
    }
    setFormData(data);
    setResult(null);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await submitExpense(formData);
      setResult(res);
      toast.success('Expense submitted successfully!');
    } catch (err: any) {
      const msg = err.message || 'Failed to submit expense';
      setError(msg);
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePolicyQuery = async () => {
    const query = policyQuery.trim();
    if (!query) return;
    setCopilotLoading(true);
    setPolicyAnswer('');
    setCopilotError(null);
    try {
      const response = await fetch('/webhook/northstar-policy-query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Correlation-ID': `northstar-policy-ui-${Date.now()}`,
        },
        body: JSON.stringify({ query }),
        signal: AbortSignal.timeout(30_000),
      });
      const body = await response.json().catch(() => null) as { answer?: string; message?: string } | null;
      if (!response.ok) {
        throw new Error(body?.message || `Policy Copilot failed with HTTP ${response.status}`);
      }
      if (!body?.answer) {
        throw new Error('Policy Copilot returned an empty answer');
      }
      setPolicyAnswer(body.answer);
    } catch (err: any) {
      const message = err.message || 'Policy Copilot is unavailable';
      setCopilotError(message);
      toast.error(message);
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Submit Expense</h1>
        <Button type="button" variant="outline" onClick={() => setCopilotOpen(true)}>
          <MessageCircleQuestion className="mr-2 h-4 w-4" />
          Ask Policy Copilot
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <button
          type="button"
          onClick={() => loadPreset('coffee')}
          className="p-4 border border-gray-200 dark:border-gray-800 rounded-lg bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <Coffee className="text-blue-500" size={24} />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto-Approve Coffee ($28.50)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('travel')}
          className="p-4 border border-gray-200 dark:border-gray-800 rounded-lg bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <Plane className="text-indigo-500 dark:text-indigo-400" size={24} />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Normal Travel ($640)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('suspicious')}
          className="p-4 border border-red-200 dark:border-red-900/50 rounded-lg bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <ShieldAlert className="text-red-500" size={24} />
          <span className="text-sm font-medium text-red-900 dark:text-red-400">Suspicious Software ($3,000)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('invalid')}
          className="p-4 border border-gray-200 dark:border-gray-800 rounded-lg bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <CalendarX className="text-amber-500" size={24} />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Invalid Future Date</span>
        </button>
      </div>

      <div className="bg-white dark:bg-gray-900 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-800">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Expense ID</label>
              <input
                type="text"
                name="expense_id"
                required
                value={formData.expense_id}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Employee ID</label>
              <input
                type="text"
                name="employee_id"
                required
                value={formData.employee_id}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Employee Name</label>
              <input
                type="text"
                name="employee_name"
                required
                value={formData.employee_name}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Department</label>
              <select
                name="department"
                value={formData.department}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              >
                {DEPARTMENTS.map(dept => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Category</label>
              <select
                name="category"
                value={formData.category}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              >
                {CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Amount</label>
              <div className="relative rounded-md shadow-sm">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <span className="text-gray-500 sm:text-sm">$</span>
                </div>
                <input
                  type="number"
                  name="amount"
                  step="0.01"
                  required
                  value={formData.amount || ''}
                  onChange={handleInputChange}
                  className="w-full rounded-md border-gray-300 dark:border-gray-700 pl-7 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Merchant</label>
              <input
                type="text"
                name="merchant"
                required
                value={formData.merchant}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Transaction Date</label>
              <input
                type="date"
                name="transaction_date"
                required
                value={formData.transaction_date}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
              <textarea
                name="description"
                rows={2}
                value={formData.description}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 dark:border-gray-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2 bg-white dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div className="md:col-span-2 flex items-center h-10">
              <input
                id="receipt"
                type="checkbox"
                name="receipt_attached"
                checked={formData.receipt_attached}
                onChange={handleCheckboxChange}
                className="h-4 w-4 rounded border-gray-300 dark:border-gray-700 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="receipt" className="ml-2 block text-sm text-gray-900 dark:text-gray-300">
                Receipt Attached
              </label>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isLoading || !!result}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {isLoading ? 'Submitting...' : 'Submit Expense'}
            </button>
          </div>
        </form>
      </div>

      {error && <ErrorAlert message={error} />}

      {result && (
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-gray-50 dark:bg-gray-800/50 px-6 py-4 border-b border-gray-200 dark:border-gray-800">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center">
              {result.status === 'REJECTED_VALIDATION' ? (
                <XCircle className="h-5 w-5 text-red-500 mr-2" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-green-500 mr-2" />
              )}
              Submission Result
            </h3>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-center space-x-4">
              <span className={cn('inline-flex items-center px-3 py-1 rounded-full text-sm font-medium', STATUS_COLORS[result.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
                {humanizeStatus(result.status)}
              </span>
              <span className={cn('inline-flex items-center px-3 py-1 rounded-full text-sm font-medium', RISK_COLORS[result.risk_level ?? ''] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
                {result.risk_level || 'N/A'} Risk
              </span>
            </div>

            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-md p-4 text-sm text-gray-700 dark:text-gray-300 border border-gray-100 dark:border-gray-800">
              <span className="font-semibold text-gray-900 dark:text-gray-100">Reason: </span>
              {result.message}
            </div>

            {result.anomaly_flags && result.anomaly_flags.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2 flex items-center">
                  <AlertTriangle className="h-4 w-4 text-amber-500 mr-1" />
                  Flags Detected
                </h4>
                <div className="flex flex-wrap gap-2">
                  {result.anomaly_flags.map((flag, i) => (
                    <span key={i} className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400 border border-red-200 dark:border-red-800">
                      {flag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="pt-4 flex justify-between items-center border-t border-gray-100 dark:border-gray-800">
              <button
                onClick={() => {
                  setResult(null);
                  setFormData(prev => ({ ...prev, expense_id: '' }));
                }}
                className="text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
              >
                Submit Another
              </button>

              <Link
                to={`/expenses/${result.expense_id}`}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
              >
                View Details
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      )}

      <Dialog open={copilotOpen} onOpenChange={setCopilotOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ask Policy Copilot</DialogTitle>
            <DialogDescription>
              Get an advisory answer grounded in North Star&apos;s certified policies. The copilot cannot approve or reject expenses.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              value={policyQuery}
              onChange={event => setPolicyQuery(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter' && !copilotLoading) void handlePolicyQuery();
              }}
              placeholder="Can I expense a $200 team dinner?"
              disabled={copilotLoading}
              aria-label="Policy question"
            />
            {copilotLoading && (
              <div className="flex items-center gap-2 rounded-md bg-gray-50 p-4 text-sm text-gray-600 dark:bg-gray-900 dark:text-gray-300">
                <Loader2 className="h-4 w-4 animate-spin" />
                Checking certified policies...
              </div>
            )}
            {copilotError && <ErrorAlert message={copilotError} />}
            {policyAnswer && (
              <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-4 text-sm leading-6 text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200">
                {policyAnswer}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              onClick={() => void handlePolicyQuery()}
              disabled={copilotLoading || !policyQuery.trim()}
            >
              {copilotLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Ask
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
