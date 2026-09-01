import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ErrorAlert } from '@/components/ui/error-alert';
import { Skeleton } from '@/components/ui/skeleton';
import { useTheme } from '@/components/theme-provider';
import { getExpenses } from '../lib/api';
import { formatCurrency, formatDate, humanizeStatus } from '../lib/utils';
import type { ExpenseState } from '../types';

const STATUS_CHART_COLORS: Record<string, string> = {
  AUTO_APPROVED: '#16a34a',
  PENDING_APPROVAL: '#d97706',
  ESCALATED: '#dc2626',
  APPROVED: '#2563eb',
  REJECTED: '#6b7280',
  REJECTED_VALIDATION: '#e11d48',
};

const RISK_CHART_COLORS: Record<string, string> = {
  LOW: '#16a34a',
  MEDIUM: '#ca8a04',
  HIGH: '#ea580c',
  CRITICAL: '#dc2626',
  UNKNOWN: '#6b7280',
};

const FALLBACK_COLOR = '#6366f1';

export default function Analytics() {
  const [expenses, setExpenses] = useState<ExpenseState[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { theme } = useTheme();
  const isDark = theme === 'dark'
    || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const fetchExpenses = useCallback(async () => {
    try {
      setError(null);
      setExpenses(await getExpenses());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load expense analytics');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchExpenses();
  }, [fetchExpenses]);

  const { statusData, riskData, categoryData, volumeData } = useMemo(() => {
    const statuses = new Map<string, number>();
    const risks = new Map<string, number>();
    const categories = new Map<string, number>();
    const dailyVolume = new Map<string, number>();

    for (const expense of expenses) {
      statuses.set(expense.status, (statuses.get(expense.status) ?? 0) + 1);

      const risk = expense.risk_level ?? 'UNKNOWN';
      risks.set(risk, (risks.get(risk) ?? 0) + 1);

      const category = expense.input_payload.category;
      categories.set(
        category,
        (categories.get(category) ?? 0) + Number(expense.input_payload.amount),
      );

      const day = expense.created_at.slice(0, 10);
      dailyVolume.set(day, (dailyVolume.get(day) ?? 0) + 1);
    }

    return {
      statusData: Array.from(statuses, ([status, value]) => ({
        key: status,
        name: humanizeStatus(status),
        value,
      })),
      riskData: Array.from(risks, ([risk, value]) => ({
        key: risk,
        name: humanizeStatus(risk),
        value,
      })),
      categoryData: Array.from(categories, ([category, amount]) => ({
        category,
        amount,
      })).sort((a, b) => b.amount - a.amount),
      volumeData: Array.from(dailyVolume, ([day, count]) => ({
        day,
        date: formatDate(day),
        count,
      })).sort((a, b) => a.day.localeCompare(b.day)),
    };
  }, [expenses]);

  const axisColor = isDark ? '#9ca3af' : '#6b7280';
  const gridColor = isDark ? '#374151' : '#e5e7eb';
  const tooltipStyle = {
    backgroundColor: isDark ? '#111827' : '#ffffff',
    borderColor: isDark ? '#374151' : '#e5e7eb',
    borderRadius: '0.5rem',
    color: isDark ? '#f3f4f6' : '#111827',
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Expense Analytics</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Operational trends computed from the current expense records.
        </p>
      </div>

      {error && <ErrorAlert message={error} onRetry={() => void fetchExpenses()} />}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[390px] rounded-xl" />
          ))}
        </div>
      ) : expenses.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No analytics data"
          description="Submit an expense to populate the analytics charts."
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Expenses by Status</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                    {statusData.map(item => (
                      <Cell key={item.key} fill={STATUS_CHART_COLORS[item.key] ?? FALLBACK_COLOR} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: axisColor }} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Risk Distribution</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={riskData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                    {riskData.map(item => (
                      <Cell key={item.key} fill={RISK_CHART_COLORS[item.key] ?? FALLBACK_COLOR} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: axisColor }} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Spend by Category</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} margin={{ top: 8, right: 8, left: 8, bottom: 48 }}>
                  <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="category" tick={{ fill: axisColor, fontSize: 11 }} angle={-30} textAnchor="end" interval={0} />
                  <YAxis tick={{ fill: axisColor, fontSize: 12 }} tickFormatter={value => `$${Number(value).toLocaleString()}`} />
                  <Tooltip contentStyle={tooltipStyle} formatter={value => [formatCurrency(Number(value)), 'Spend']} />
                  <Bar dataKey="amount" fill={isDark ? '#818cf8' : '#4f46e5'} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Expense Volume Over Time</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={volumeData} margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                  <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: axisColor, fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fill: axisColor, fontSize: 12 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line type="monotone" dataKey="count" name="Expenses" stroke={isDark ? '#a5b4fc' : '#4f46e5'} strokeWidth={3} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
