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

interface HealthStatus {
  status: 'ok' | 'error' | 'unknown' | 'manual';
  text: string;
}

export default function SystemHealth() {
  const [fastApiHealth, setFastApiHealth] = useState<HealthStatus>({ status: 'unknown', text: 'Checking...' });
  const [dlqEvents, setDlqEvents] = useState<any[]>([]);
  const [workflowFailures, setWorkflowFailures] = useState<any[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      const res = await checkHealth();
      setFastApiHealth({ status: res.status === 'ok' ? 'ok' : 'error', text: res.status === 'ok' ? 'Healthy' : 'Error' });
    } catch (e) {
      setFastApiHealth({ status: 'error', text: 'Unreachable' });
    }

    try {
      const dlq = await getDeadLetterEvents();
      setDlqEvents(dlq || []);
    } catch (e) {
      console.error(e);
    }

    try {
      const failures = await getWorkflowFailures();
      setWorkflowFailures(failures || []);
    } catch (e) {
      console.error(e);
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
    <div className="max-w-7xl mx-auto p-6 space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center">
            <Heart className="mr-3 h-8 w-8 text-rose-600" />
            System Health
          </h1>
          <p className="mt-2 text-gray-600">
            Monitor core infrastructure, workflows, and message queues.
          </p>
        </div>
        <div className="text-sm text-gray-500">
          Last updated: {lastUpdated.toLocaleTimeString()}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* FastAPI */}
        <div className="bg-white p-5 rounded-lg shadow border border-gray-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-indigo-100 p-2 rounded"><Server className="h-5 w-5 text-indigo-600" /></div>
              <h3 className="font-semibold text-gray-900">FastAPI</h3>
            </div>
            <StatusIcon status={fastApiHealth.status} />
          </div>
          <p className="text-sm text-gray-600">{fastApiHealth.text}</p>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 flex items-center hover:underline">
            View Swagger <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>

        {/* n8n */}
        <div className="bg-white p-5 rounded-lg shadow border border-gray-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-amber-100 p-2 rounded"><Workflow className="h-5 w-5 text-amber-600" /></div>
              <h3 className="font-semibold text-gray-900">n8n</h3>
            </div>
            <StatusIcon status="manual" />
          </div>
          <p className="text-sm text-gray-600">Check manually</p>
          <a href="http://127.0.0.1:5679" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 flex items-center hover:underline">
            Open Editor <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>

        {/* PostgreSQL */}
        <div className="bg-white p-5 rounded-lg shadow border border-gray-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-100 p-2 rounded"><Database className="h-5 w-5 text-blue-600" /></div>
              <h3 className="font-semibold text-gray-900">PostgreSQL</h3>
            </div>
            <StatusIcon status={fastApiHealth.status === 'ok' ? 'ok' : 'unknown'} />
          </div>
          <p className="text-sm text-gray-600">{fastApiHealth.status === 'ok' ? 'Connected via API' : 'Status unknown'}</p>
        </div>

        {/* Metabase */}
        <div className="bg-white p-5 rounded-lg shadow border border-gray-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center space-x-3">
              <div className="bg-emerald-100 p-2 rounded"><BarChart className="h-5 w-5 text-emerald-600" /></div>
              <h3 className="font-semibold text-gray-900">Metabase</h3>
            </div>
            <StatusIcon status="manual" />
          </div>
          <p className="text-sm text-gray-600">Check manually</p>
          <a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer" className="mt-4 text-xs text-indigo-600 flex items-center hover:underline">
            Open Dashboards <ExternalLink className="ml-1 h-3 w-3" />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
            <h3 className="text-lg font-medium text-gray-900">Reliability Monitor</h3>
          </div>
          <div className="p-6 space-y-6">
            <div>
              <div className="flex justify-between items-center mb-2">
                <h4 className="text-sm font-semibold text-gray-700">Dead Letter Queue</h4>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${dlqEvents.length > 0 ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                  {dlqEvents.length} Events
                </span>
              </div>
              {dlqEvents.length > 0 ? (
                <div className="mt-2 border rounded overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {dlqEvents.map((evt, i) => (
                        <tr key={i}>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-900 font-mono text-xs">{evt.outbox_event_id || evt.event_id || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-gray-500">{evt.event_type || evt.type || 'N/A'}</td>
                          <td className="px-3 py-2 whitespace-nowrap text-red-600">{evt.status || 'FAILED'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-gray-500 italic">No dead letter events.</p>
              )}
            </div>

            <div>
              <div className="flex justify-between items-center">
                <h4 className="text-sm font-semibold text-gray-700">Workflow Failures</h4>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${workflowFailures.length > 0 ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                  {workflowFailures.length} Open
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
            <h3 className="text-lg font-medium text-gray-900">Architecture Overview</h3>
          </div>
          <div className="p-6">
            <p className="text-gray-700 leading-relaxed mb-4">
              North Star is a governed expense-operations platform with deterministic policy execution, 
              durable n8n workflows, PostgreSQL persistence, decision provenance, and MCP interfaces.
            </p>
            <div className="space-y-3 mt-6">
              <h4 className="text-sm font-semibold text-gray-900 border-b pb-2">Quick Links</h4>
              <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border hover:bg-gray-50 transition">
                <Code className="h-5 w-5 text-indigo-500 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900">FastAPI Swagger</div>
                  <div className="text-xs text-gray-500">API Documentation</div>
                </div>
              </a>
              <a href="http://127.0.0.1:5679" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border hover:bg-gray-50 transition">
                <Workflow className="h-5 w-5 text-amber-500 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900">n8n Editor</div>
                  <div className="text-xs text-gray-500">Workflow Automation</div>
                </div>
              </a>
              <a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer" className="flex items-center p-3 rounded-lg border hover:bg-gray-50 transition">
                <BarChart className="h-5 w-5 text-emerald-500 mr-3" />
                <div>
                  <div className="text-sm font-medium text-gray-900">Metabase Dashboards</div>
                  <div className="text-xs text-gray-500">Analytics and Reporting</div>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
