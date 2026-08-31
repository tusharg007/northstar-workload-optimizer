import React, { useEffect, useState } from 'react';
import { checkHealth, getDeadLetterEvents, getWorkflowFailures } from '../lib/api';
import {
  Server,
  Database,
  Workflow,
  Activity,
  ExternalLink,
  AlertCircle,
  CheckCircle,
  Heart,
  BarChart,
  Code
} from 'lucide-react';
import { ErrorAlert } from '@/components/ui/error-alert';

interface HealthStatus {
  status: 'ok' | 'error' | 'unknown' | 'manual';
  text: string;
}

export default function SystemHealth() {
  const [fastApiHealth, setFastApiHealth] = useState<HealthStatus>({ status: 'unknown', text: 'Checking...' });
  const [dlqEvents, setDlqEvents] = useState<any[]>([]);
  const [workflowFailures, setWorkflowFailures] = useState<any[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setError(null);
    try {
      const res = await checkHealth();
      setFastApiHealth({ status: res.status === 'ok' ? 'ok' : 'error', text: res.status === 'ok' ? 'Healthy' : 'Error' });
    } catch (e: any) {
      setFastApiHealth({ status: 'error', text: 'Unreachable' });
      setError(e.message || 'Failed to check system health');
    }

    try {
      const dlq = await getDeadLetterEvents();
      setDlqEvents(dlq || []);
    } catch (e: any) {
      console.error(e);
      setError(prev => prev ? `${prev} | Failed to load DLQ` : 'Failed to load DLQ events');
    }

    try {
      const failures = await getWorkflowFailures();
      setWorkflowFailures(failures || []);
    } catch (e: any) {
      console.error(e);
      setError(prev => prev ? `${prev} | Failed to load workflow failures` : 'Failed to load workflow failures');
    }

    setLastUpdated(new Date());
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const StatusIcon = ({ status }: { status: HealthStatus['status'] }) => {
    switch (status) {
      case 'ok': return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'error': return <AlertCircle className="h-5 w-5 text-red-500" />;
      case 'manual': return <Activity className="h-5 w-5 text-blue-500" />;
      default: return <Activity className="h-5 w-5 text-gray-400" />;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 flex items-center">
            <Heart className="mr-3 h-8 w-8 text-rose-600 dark:text-rose-400" />
            System Health
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Monitor core infrastructure, workflows, and message queues.
          </p>
        </div>
        <div className="text-sm text-gray-500 dark:text-gray-400">
          Last updated: {lastUpdated.toLocaleTimeString()}
        </div>
      </div>

      {error && <ErrorAlert message={error} onRetry={fetchData} />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* FastAPI */}
        <div className="bg-white dark:bg-gray-900 p-5 rounded-lg shadow border border-gray-200 dark:border-gray-800">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-indigo-100 dark:bg-indigo-900/30 p-2 rounded"><Server className="h-5 w-5 text-indigo-600 dark:text-indigo-400" /></div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">FastAPI</h3>
            </div>
            <StatusIcon status={fastApiHealth.status} />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">{fastApiHealth.text}</p>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 dark:text-indigo-400 flex items-center hover:underline">
            View Swagger <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>

        {/* n8n */}
        <div className="bg-white dark:bg-gray-900 p-5 rounded-lg shadow border border-gray-200 dark:border-gray-800">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-amber-100 dark:bg-amber-900/30 p-2 rounded"><Workflow className="h-5 w-5 text-amber-600 dark:text-amber-400" /></div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">n8n</h3>
            </div>
            <StatusIcon status="manual" />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">Check manually</p>
          <a href="http://127.0.0.1:5679" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 dark:text-indigo-400 flex items-center hover:underline">
            Open Editor <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>

        {/* PostgreSQL */}
        <div className="bg-white dark:bg-gray-900 p-5 rounded-lg shadow border border-gray-200 dark:border-gray-800">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-100 dark:bg-blue-900/30 p-2 rounded"><Database className="h-5 w-5 text-blue-600 dark:text-blue-400" /></div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">PostgreSQL</h3>
            </div>
            <StatusIcon status={fastApiHealth.status === 'ok' ? 'ok' : 'unknown'} />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">{fastApiHealth.status === 'ok' ? 'Connected via API' : 'Status unknown'}</p>
        </div>

        {/* Metabase */}
        <div className="bg-white dark:bg-gray-900 p-5 rounded-lg shadow border border-gray-200 dark:border-gray-800">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-emerald-100 dark:bg-emerald-900/30 p-2 rounded"><BarChart className="h-5 w-5 text-emerald-600 dark:text-emerald-400" /></div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">Metabase</h3>
            </div>
            <StatusIcon status="manual" />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">Check manually</p>
          <a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 dark:text-indigo-400 flex items-center hover:underline">
            Open Dashboards <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-lg shadow border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex items-center justify-between">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Reliability Monitor</h3>
          </div>
          <div className="p-6 space-y-6">
            <div>
              <div className="flex justify-between items-center mb-2">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Dead Letter Queue</h4>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${dlqEvents.length > 0 ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400' : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'}`}>
                  {dlqEvents.length} Events
                </span>
              </div>
              {dlqEvents.length > 0 ? (
                <div className="mt-2 border dark:border-gray-700 rounded overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800/50">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">ID</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Type</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                      {dlqEvents.map((evt, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-900 dark:text-gray-100 font-mono text-xs">{evt.outbox_event_id || evt.event_id || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-500 dark:text-gray-400">{evt.event_type || evt.type || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-red-600 dark:text-red-400">{evt.status || 'FAILED'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 italic">No dead letter events.</p>
              )}
            </div>

            <div>
              <div className="flex justify-between items-center">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Workflow Failures</h4>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${workflowFailures.length > 0 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400' : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'}`}>
                  {workflowFailures.length} Open
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-lg shadow border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Architecture Overview</h3>
          </div>
          <div className="p-6">
            <p className="text-gray-700 dark:text-gray-300 leading-relaxed mb-4">
              North Star is a governed expense-operations platform with deterministic policy execution,
              durable n8n workflows, PostgreSQL persistence, decision provenance, and MCP interfaces.
            </p>
            <div className="space-y-3 mt-6">
              <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 border-b border-gray-200 dark:border-gray-800 pb-2">Quick Links</h4>
              <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition">
                <Code className="h-5 w-5 text-indigo-500 dark:text-indigo-400 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">FastAPI Swagger</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">API Documentation</div>
                </div>
              </a>
              <a href="http://127.0.0.1:5679" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition">
                <Workflow className="h-5 w-5 text-amber-500 dark:text-amber-400 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">n8n Editor</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Workflow Automation</div>
                </div>
              </a>
              <a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition">
                <BarChart className="h-5 w-5 text-emerald-500 dark:text-emerald-400 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Metabase Dashboards</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Analytics and Reporting</div>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
