import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  FileText,
  CheckCircle,
  Clock,
  AlertTriangle,
  ThumbsUp,
  Search,
  FileJson,
  FileSpreadsheet,
} from 'lucide-react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type Column,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
} from '@tanstack/react-table';
import { getExpenses } from '../lib/api';
import type { ExpenseState } from '../types';
import { STATUS_COLORS, RISK_COLORS } from '../types';
import { formatCurrency, formatDate, cn, humanizeStatus } from '../lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorAlert } from '@/components/ui/error-alert';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useEventStream } from '../hooks/useEventStream';

function SelectionCheckbox({
  checked,
  indeterminate = false,
  onChange,
  label,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: React.ChangeEventHandler<HTMLInputElement>;
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
      onChange={onChange}
      aria-label={label}
      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800"
    />
  );
}

function SortableHeader({ label, column }: { label: string; column: Column<ExpenseState, unknown> }) {
  const sorted = column.getIsSorted();
  return (
    <button
      type="button"
      onClick={column.getToggleSortingHandler()}
      className="inline-flex items-center gap-1 hover:text-gray-700 dark:hover:text-gray-200"
    >
      {label}
      {sorted === 'asc' ? (
        <ArrowUp className="h-3.5 w-3.5" />
      ) : sorted === 'desc' ? (
        <ArrowDown className="h-3.5 w-3.5" />
      ) : (
        <ArrowUpDown className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeCSV(value: unknown): string {
  const text = value == null ? '' : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export default function Dashboard() {
  const [expenses, setExpenses] = useState<ExpenseState[]>([]);
  const [filter, setFilter] = useState<string>('ALL');
  const [globalFilter, setGlobalFilter] = useState('');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
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

  useEventStream(event => {
    if (event.type === 'expense_created' || event.type === 'expense_updated') {
      void fetchExpenses();
    }
  });

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

  const columns = useMemo<ColumnDef<ExpenseState>[]>(() => [
    {
      id: 'select',
      header: ({ table }) => (
        <SelectionCheckbox
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected()}
          onChange={table.getToggleAllPageRowsSelectedHandler()}
          label="Select all expenses on this page"
        />
      ),
      cell: ({ row }) => (
        <SelectionCheckbox
          checked={row.getIsSelected()}
          indeterminate={row.getIsSomeSelected()}
          onChange={row.getToggleSelectedHandler()}
          label={`Select expense ${row.original.expense_id}`}
        />
      ),
      enableSorting: false,
      enableGlobalFilter: false,
    },
    {
      id: 'identity',
      accessorFn: expense => `${expense.input_payload.employee_name} ${expense.expense_id}`,
      header: 'ID & Employee',
      cell: ({ row }) => (
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {row.original.input_payload.employee_name}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {row.original.expense_id}
          </div>
        </div>
      ),
      enableSorting: false,
      enableGlobalFilter: true,
    },
    {
      id: 'category',
      accessorFn: expense => expense.input_payload.category,
      header: 'Category',
      cell: ({ getValue }) => <span className="text-gray-500 dark:text-gray-400">{String(getValue())}</span>,
      enableSorting: false,
      enableGlobalFilter: false,
    },
    {
      id: 'amount',
      accessorFn: expense => expense.input_payload.amount,
      header: ({ column }) => <SortableHeader label="Amount" column={column} />,
      cell: ({ getValue }) => (
        <span className="font-medium text-gray-900 dark:text-gray-100">
          {formatCurrency(Number(getValue()))}
        </span>
      ),
      enableGlobalFilter: false,
    },
    {
      id: 'risk',
      accessorFn: expense => expense.risk_level ?? '',
      header: 'Risk Level',
      cell: ({ row }) => (
        <Badge
          variant="outline"
          className={cn(
            'border-transparent',
            RISK_COLORS[row.original.risk_level ?? ''] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
          )}
        >
          {row.original.risk_level || 'N/A'}
        </Badge>
      ),
      enableSorting: false,
      enableGlobalFilter: false,
    },
    {
      id: 'status',
      accessorFn: expense => expense.status,
      header: 'Status',
      cell: ({ row }) => (
        <Badge
          variant="outline"
          className={cn(
            'border-transparent',
            STATUS_COLORS[row.original.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
          )}
        >
          {humanizeStatus(row.original.status)}
        </Badge>
      ),
      enableSorting: false,
      enableGlobalFilter: false,
    },
    {
      id: 'date',
      accessorFn: expense => expense.created_at,
      header: ({ column }) => <SortableHeader label="Date" column={column} />,
      cell: ({ getValue }) => <span className="text-gray-500 dark:text-gray-400">{formatDate(String(getValue()))}</span>,
      enableGlobalFilter: false,
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <Link
          to={`/expenses/${row.original.expense_id}`}
          className="text-indigo-600 hover:text-indigo-900 dark:text-indigo-400 dark:hover:text-indigo-300"
        >
          View
        </Link>
      ),
      enableSorting: false,
      enableGlobalFilter: false,
    },
  ], []);

  const table = useReactTable({
    data: filteredExpenses,
    columns,
    state: { globalFilter, sorting, rowSelection },
    onGlobalFilterChange: setGlobalFilter,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    globalFilterFn: (row, _columnId, value) => {
      const query = String(value).trim().toLowerCase();
      if (!query) return true;
      const expense = row.original;
      return [
        expense.input_payload.employee_name,
        expense.expense_id,
        expense.input_payload.merchant,
        expense.input_payload.category,
      ].some(field => field.toLowerCase().includes(query));
    },
    getRowId: expense => expense.expense_id,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 10 } },
  });

  const exportExpenses = table
    .getFilteredRowModel()
    .rows.map(row => row.original);

  const exportCSV = () => {
    const headers = [
      'expense_id',
      'employee_id',
      'employee_name',
      'department',
      'transaction_date',
      'merchant',
      'category',
      'description',
      'amount',
      'currency',
      'payment_method',
      'receipt_attached',
      'risk_level',
      'status',
      'approver_role',
      'decision',
      'decided_by',
      'decided_at',
      'created_at',
      'updated_at',
    ];
    const rows = exportExpenses.map(expense => [
      expense.expense_id,
      expense.input_payload.employee_id,
      expense.input_payload.employee_name,
      expense.input_payload.department,
      expense.input_payload.transaction_date,
      expense.input_payload.merchant,
      expense.input_payload.category,
      expense.input_payload.description,
      expense.input_payload.amount,
      expense.input_payload.currency,
      expense.input_payload.payment_method,
      expense.input_payload.receipt_attached,
      expense.risk_level,
      expense.status,
      expense.approver_role,
      expense.decision,
      expense.decided_by,
      expense.decided_at,
      expense.created_at,
      expense.updated_at,
    ]);
    const content = [headers, ...rows]
      .map(row => row.map(escapeCSV).join(','))
      .join('\r\n');
    downloadFile(
      content,
      `northstar-expenses-${new Date().toISOString().slice(0, 10)}.csv`,
      'text/csv;charset=utf-8',
    );
  };

  const exportJSON = () => {
    downloadFile(
      JSON.stringify(exportExpenses, null, 2),
      `northstar-expenses-${new Date().toISOString().slice(0, 10)}.json`,
      'application/json;charset=utf-8',
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Operations Overview</h1>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={exportCSV} disabled={exportExpenses.length === 0}>
            <FileSpreadsheet className="mr-2 h-4 w-4" />
            Export CSV
          </Button>
          <Button type="button" variant="outline" onClick={exportJSON} disabled={exportExpenses.length === 0}>
            <FileJson className="mr-2 h-4 w-4" />
            Export JSON
          </Button>
        </div>
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
          <div className="border-b border-gray-200 p-4 dark:border-gray-800">
            <label htmlFor="expense-search" className="sr-only">Search expenses</label>
            <div className="relative max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <Input
                id="expense-search"
                value={globalFilter}
                onChange={event => setGlobalFilter(event.target.value)}
                placeholder="Search employee, ID, merchant, or category..."
                className="pl-9"
              />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
              <thead className="bg-gray-50 dark:bg-gray-800/50">
                {table.getHeaderGroups().map(headerGroup => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map(header => (
                      <th
                        key={header.id}
                        className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={columns.length} className="px-6 py-4">
                        <Skeleton className="h-8 w-full" />
                      </td>
                    </tr>
                  ))
                ) : table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                      No expenses match this view and search.
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map(row => (
                    <tr key={row.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                      {row.getVisibleCells().map(cell => (
                        <td key={cell.id} className="whitespace-nowrap px-6 py-4 text-sm">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <label htmlFor="page-size">Rows per page</label>
              <select
                id="page-size"
                value={table.getState().pagination.pageSize}
                onChange={event => table.setPageSize(Number(event.target.value))}
                className="h-9 rounded-md border border-gray-300 bg-white px-2 text-gray-900 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
              >
                {[10, 25, 50].map(pageSize => (
                  <option key={pageSize} value={pageSize}>{pageSize}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Page {table.getState().pagination.pageIndex + 1} of {Math.max(table.getPageCount(), 1)}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}
              >
                Previous
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
