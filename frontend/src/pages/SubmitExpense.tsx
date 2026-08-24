import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Coffee, Plane, ShieldAlert, CalendarX, ArrowRight, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { submitExpense } from '../lib/api';
import { ExpenseSubmission, DEPARTMENTS, CATEGORIES, ExpenseState, STATUS_COLORS, RISK_COLORS } from '../types';
import { cn, humanizeStatus, formatCurrency } from '../lib/utils';

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
    const randomSuffix = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
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
      if (weekdayDate.getDay() === 0 || weekdayDate.getDay() === 6) {
        weekdayDate.setDate(weekdayDate.getDate() - (weekdayDate.getDay() === 0 ? 2 : 1));
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
      sat.setDate(sat.getDate() - ((sat.getDay() + 1) % 7));
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
      future.setDate(future.getDate() + 30);
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
    } catch (err: any) {
      setError(err.message || 'Failed to submit expense');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Submit Expense</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <button
          type="button"
          onClick={() => loadPreset('coffee')}
          className="p-4 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <Coffee className="text-blue-500" size={24} />
          <span className="text-sm font-medium text-gray-700">Auto-Approve Coffee ($28.50)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('travel')}
          className="p-4 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <Plane className="text-indigo-500" size={24} />
          <span className="text-sm font-medium text-gray-700">Normal Travel ($640)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('suspicious')}
          className="p-4 border border-red-200 rounded-lg bg-red-50 hover:bg-red-100 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <ShieldAlert className="text-red-500" size={24} />
          <span className="text-sm font-medium text-red-900">Suspicious Software ($3,000)</span>
        </button>
        <button
          type="button"
          onClick={() => loadPreset('invalid')}
          className="p-4 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 flex flex-col items-center justify-center text-center space-y-2 transition-colors"
        >
          <CalendarX className="text-amber-500" size={24} />
          <span className="text-sm font-medium text-gray-700">Invalid Future Date</span>
        </button>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Expense ID</label>
              <input
                type="text"
                name="expense_id"
                required
                value={formData.expense_id}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Employee ID</label>
              <input
                type="text"
                name="employee_id"
                required
                value={formData.employee_id}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Employee Name</label>
              <input
                type="text"
                name="employee_name"
                required
                value={formData.employee_name}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
              <select
                name="department"
                value={formData.department}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              >
                {DEPARTMENTS.map(dept => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
              <select
                name="category"
                value={formData.category}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              >
                {CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Amount</label>
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
                  className="w-full rounded-md border-gray-300 pl-7 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Merchant</label>
              <input
                type="text"
                name="merchant"
                required
                value={formData.merchant}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Transaction Date</label>
              <input
                type="date"
                name="transaction_date"
                required
                value={formData.transaction_date}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                name="description"
                rows={2}
                value={formData.description}
                onChange={handleInputChange}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2"
              />
            </div>
            <div className="md:col-span-2 flex items-center h-10">
              <input
                id="receipt"
                type="checkbox"
                name="receipt_attached"
                checked={formData.receipt_attached}
                onChange={handleCheckboxChange}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="receipt" className="ml-2 block text-sm text-gray-900">
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

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <XCircle className="h-5 w-5 text-red-400" aria-hidden="true" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        </div>
      )}

      {result && (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
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
              <span className={cn('inline-flex items-center px-3 py-1 rounded-full text-sm font-medium', STATUS_COLORS[result.status])}>
                {humanizeStatus(result.status)}
              </span>
              <span className={cn('inline-flex items-center px-3 py-1 rounded-full text-sm font-medium', RISK_COLORS[result.risk_level ?? ''] || 'bg-gray-100 text-gray-800')}>
                {result.risk_level || 'N/A'} Risk
              </span>
            </div>

            <div className="bg-gray-50 rounded-md p-4 text-sm text-gray-700 border border-gray-100">
              <span className="font-semibold text-gray-900">Reason: </span>
              {result.message}
            </div>

            {result.anomaly_flags && result.anomaly_flags.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-900 mb-2 flex items-center">
                  <AlertTriangle className="h-4 w-4 text-amber-500 mr-1" />
                  Flags Detected
                </h4>
                <div className="flex flex-wrap gap-2">
                  {result.anomaly_flags.map((flag, i) => (
                    <span key={i} className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-red-100 text-red-800 border border-red-200">
                      {flag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="pt-4 flex justify-between items-center border-t border-gray-100">
              <button
                onClick={() => {
                  setResult(null);
                  setFormData(prev => ({ ...prev, expense_id: '' }));
                }}
                className="text-sm font-medium text-gray-600 hover:text-gray-900"
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
    </div>
  );
}
