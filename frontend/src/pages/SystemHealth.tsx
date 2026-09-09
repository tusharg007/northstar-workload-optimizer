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
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

interface HealthStatus {
  status: 'ok' | 'error' | 'unknown' | 'manual';
  text: string;
}

interface DeadLetterEvent {
  outbox_event_id?: string;
  event_id?: string;
  event_type?: string;
  type?: string;
  status?: string;
}

interface WorkflowFailure {
  failure_id?: string;
  workflow_id?: string;
  execution_id?: string;
  failed_node?: string | null;
  error_class?: string | null;
  safe_message?: string;
  created_at?: string;
  first_seen_at?: string;
}

export default function SystemHealth() {
  const [fastApiHealth, setFastApiHealth] = useState<HealthStatus>({ status: 'unknown', text: 'Checking...' });
  const [n8nHealth, setN8nHealth] = useState<HealthStatus>({ status: 'unknown', text: 'Checking...' });
  const [postgresHealth, setPostgresHealth] = useState<HealthStatus>({ status: 'unknown', text: 'Checking...' });
  const [dlqEvents, setDlqEvents] = useState<DeadLetterEvent[]>([]);
  const [workflowFailures, setWorkflowFailures] = useState<WorkflowFailure[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);
  const [replayingId, setReplayingId] = useState<string | null>(null);
  const [reconciling, setReconciling] = useState(false);

  const fetchData = async () => {
    setError(null);
    try {
      const res = await checkHealth();
      setFastApiHealth({ status: res.status === 'ok' ? 'ok' : 'error', text: res.status === 'ok' ? 'Healthy' : 'Error' });
      setPostgresHealth(
        res.database === 'connected'
          ? { status: 'ok', text: 'Connected' }
          : res.database === 'disconnected'
            ? { status: 'error', text: 'Disconnected' }
            : { status: 'unknown', text: 'Not reported by API' },
      );
    } catch (e: any) {
      setFastApiHealth({ status: 'error', text: 'Unreachable' });
      setPostgresHealth({ status: 'unknown', text: 'API unavailable' });
      setError(e.message || 'Failed to check system health');
    }

    try {
      let n8nResponse: Response;
      try {
        n8nResponse = await fetch(
          `http://${window.location.hostname}:5679/healthz`,
          { cache: 'no-store', signal: AbortSignal.timeout(5_000) },
        );
      } catch {
        // n8n does not emit browser CORS headers on /healthz by default.
        n8nResponse = await fetch('/n8n-healthz', {
          cache: 'no-store',
          signal: AbortSignal.timeout(5_000),
        });
      }
      if (!n8nResponse.ok) throw new Error(`HTTP ${n8nResponse.status}`);
      setN8nHealth({ status: 'ok', text: 'Healthy' });
    } catch {
      setN8nHealth({ status: 'error', text: 'Unreachable' });
    }

    try {
      const dlq = await getDeadLetterEvents();
      setDlqEvents((dlq || []) as DeadLetterEvent[]);
    } catch (e: any) {
      console.error(e);
      setError(prev => prev ? `${prev} | Failed to load DLQ` : 'Failed to load DLQ events');
    }

    try {
      const failures = await getWorkflowFailures();
      setWorkflowFailures((failures || []) as WorkflowFailure[]);
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

  const replayEvent = async (event: DeadLetterEvent) => {
    const eventId = event.outbox_event_id;
    if (!eventId) {
      toast.error('Replay failed');
      return;
    }

    try {
      setReplayingId(eventId);
      const response = await fetch(`/api/internal/outbox/${encodeURIComponent(eventId)}/replay`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error(`Replay failed with HTTP ${response.status}`);
      toast.success('Event replayed');
      await fetchData();
    } catch (err) {
      console.error(err);
      toast.error('Replay failed');
    } finally {
      setReplayingId(null);
    }
  };

  const runReconciliation = async () => {
    try {
      setReconciling(true);
      const response = await fetch('/api/internal/reliability/reconcile', { method: 'POST' });
      if (!response.ok) throw new Error(`Reconciliation failed with HTTP ${response.status}`);
      toast.success('Reconciliation complete');
      await fetchData();
    } catch (err) {
      console.error(err);
      toast.error('Reconciliation failed');
    } finally {
      setReconciling(false);
    }
  };

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
            <StatusIcon status={n8nHealth.status} />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">{n8nHealth.text}</p>
          <a href={`http://${window.location.hostname}:5679`} target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 dark:text-indigo-400 flex items-center hover:underline">
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
            <StatusIcon status={postgresHealth.status} />
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">{postgresHealth.text}</p>
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
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={runReconciliation}
              disabled={reconciling}
            >
              {reconciling ? 'Reconciling...' : 'Run Reconciliation'}
            </Button>
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
                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Action</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                      {dlqEvents.map((evt, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-900 dark:text-gray-100 font-mono text-xs">{evt.outbox_event_id || evt.event_id || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-500 dark:text-gray-400">{evt.event_type || evt.type || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-red-600 dark:text-red-400">{evt.status || 'FAILED'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-right">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => replayEvent(evt)}
                              disabled={!evt.outbox_event_id || replayingId === evt.outbox_event_id}
                            >
                              {replayingId === evt.outbox_event_id ? 'Replaying...' : 'Replay'}
                            </Button>
                          </td>
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
                  {workflowFailures.length} Recorded
                </span>
              </div>
              {workflowFailures.length > 0 ? (
                <div className="mt-2 overflow-x-auto rounded border dark:border-gray-700">
                  <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-800/50">
                      <tr>
                        {['Workflow ID', 'Execution ID', 'Failed Node', 'Error Class', 'Safe Message', 'Created At'].map(column => (
                          <th key={column} className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
                      {workflowFailures.map((failure, index) => (
                        <tr key={failure.failure_id || `${failure.workflow_id}-${failure.execution_id}-${index}`}>
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">{failure.workflow_id || 'N/A'}</td>
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">{failure.execution_id || 'N/A'}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-gray-600 dark:text-gray-300">{failure.failed_node || 'N/A'}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-gray-600 dark:text-gray-300">{failure.error_class || 'N/A'}</td>
                          <td className="max-w-xs px-3 py-2 text-gray-600 dark:text-gray-300">{failure.safe_message || 'N/A'}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-gray-500 dark:text-gray-400">
                            {failure.created_at || failure.first_seen_at
                              ? new Date(failure.created_at || failure.first_seen_at!).toLocaleString()
                              : 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-2 text-sm italic text-gray-500 dark:text-gray-400">No workflow failures recorded.</p>
              )}
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
