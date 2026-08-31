import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ChevronLeft,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Shield,
  FileText,
  Activity,
  Server,
  AlertCircle,
  Copy,
  Check
} from 'lucide-react';
import {
  getExpense,
  getExplanation,
  getLineage,
  getProvenance,
  verifyProvenance
} from '../lib/api';
import type {
  ExpenseState,
  Explanation,
  Lineage,
  ProvenanceView,
  VerifyResult
} from '../types';
import { STATUS_COLORS, RISK_COLORS } from '../types';
import { formatCurrency, formatDate, formatDateTime, humanizeStatus, cn } from '../lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

export default function ExpenseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'overview' | 'lineage' | 'provenance'>('overview');

  const [expense, setExpense] = useState<ExpenseState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    const fetchBase = async () => {
      try {
        setLoading(true);
        const data = await getExpense(id);
        setExpense(data);
      } catch (err: any) {
        setError(err.message || 'Failed to load expense details');
      } finally {
        setLoading(false);
      }
    };

    fetchBase();
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
        <Skeleton className="w-24 h-6 mb-4" />
        <Skeleton className="w-full h-32" />
        <Skeleton className="w-full h-8" />
        <Skeleton className="w-full h-64" />
      </div>
    );
  }

  if (error || !expense) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="bg-red-50 text-red-700 p-4 rounded-md flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error || 'Expense not found'}</span>
        </div>
        <button onClick={() => navigate(-1)} className="mt-4 inline-flex items-center text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300">
          <ChevronLeft className="w-4 h-4 mr-1" /> Back
        </button>
      </div>
    );
  }

  const p = expense.input_payload;

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <button onClick={() => navigate(-1)} className="inline-flex items-center text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 mb-4 transition-colors">
          <ChevronLeft className="w-4 h-4 mr-1" /> Back
        </button>
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Expense {expense.expense_id.substring(0, 8)}</h1>
              <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', STATUS_COLORS[expense.status] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
                {humanizeStatus(expense.status)}
              </span>
              <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium flex items-center gap-1', RISK_COLORS[expense.risk_level ?? ''] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200')}>
                <Shield className="w-3 h-3" />
                {expense.risk_level || 'N/A'}
              </span>
            </div>
            <p className="text-gray-500 dark:text-gray-400">
              Submitted by <span className="font-medium text-gray-700 dark:text-gray-300">{p.employee_name}</span> on {formatDate(p.transaction_date)}
            </p>
          </div>
          <div className="text-left md:text-right">
            <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">{formatCurrency(p.amount)}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">{p.merchant} • {p.category}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('overview')}
            className={cn(
              'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2',
              activeTab === 'overview'
                ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
            )}
          >
            <FileText className="w-4 h-4" /> Overview & Explanation
          </button>
          <button
            onClick={() => setActiveTab('lineage')}
            className={cn(
              'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2',
              activeTab === 'lineage'
                ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
            )}
          >
            <Activity className="w-4 h-4" /> Lineage Timeline
          </button>
          <button
            onClick={() => setActiveTab('provenance')}
            className={cn(
              'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2',
              activeTab === 'provenance'
                ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
            )}
          >
            <Server className="w-4 h-4" /> Decision Provenance
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm p-6">
        {activeTab === 'overview' && <OverviewTab id={id!} expense={expense} />}
        {activeTab === 'lineage' && <LineageTab id={id!} />}
        {activeTab === 'provenance' && <ProvenanceTab id={id!} />}
      </div>
    </div>
  );
}

function OverviewTab({ id, expense }: { id: string, expense: ExpenseState }) {
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExplanation(id).then(setExplanation).finally(() => setLoading(false));
  }, [id]);

  const p = expense.input_payload;
  const result = expense.result;
  const anomaly = result?.anomaly;
  const decision = result?.decision;

  return (
    <div className="space-y-8">
      {/* Payload Info */}
      <section>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4 border-b border-gray-200 dark:border-gray-800 pb-2">Expense Details</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
          <div className="grid grid-cols-3">
            <span className="text-gray-500 dark:text-gray-400 font-medium">Employee ID:</span>
            <span className="col-span-2 text-gray-900 dark:text-gray-100">{p.employee_id}</span>
          </div>
          <div className="grid grid-cols-3">
            <span className="text-gray-500 dark:text-gray-400 font-medium">Department:</span>
            <span className="col-span-2 text-gray-900 dark:text-gray-100">{p.department}</span>
          </div>
          <div className="grid grid-cols-3">
            <span className="text-gray-500 dark:text-gray-400 font-medium">Payment Method:</span>
            <span className="col-span-2 text-gray-900 dark:text-gray-100">{p.payment_method}</span>
          </div>
          <div className="grid grid-cols-3">
            <span className="text-gray-500 dark:text-gray-400 font-medium">Receipt:</span>
            <span className="col-span-2 text-gray-900 dark:text-gray-100">{p.receipt_attached ? 'Attached' : 'Missing'}</span>
          </div>
          <div className="grid grid-cols-3 md:col-span-2">
            <span className="text-gray-500 dark:text-gray-400 font-medium">Description:</span>
            <span className="col-span-2 text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-800/50 p-2 rounded">{p.description || 'N/A'}</span>
          </div>
        </div>
      </section>

      {/* AI Analysis */}
      <section>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4 border-b border-gray-200 dark:border-gray-800 pb-2">Risk & Anomalies</h3>
        {anomaly ? (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="w-32 text-sm text-gray-500 dark:text-gray-400 font-medium">Risk Score</div>
              <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full",
                    anomaly.confidence_score > 0.8 ? "bg-red-500" :
                    anomaly.confidence_score > 0.5 ? "bg-orange-400" :
                    "bg-green-500"
                  )}
                  style={{ width: `${Math.min(100, Math.max(0, anomaly.confidence_score * 100))}%` }}
                />
              </div>
              <div className="w-12 text-right text-sm font-medium dark:text-gray-200">{Math.round(anomaly.confidence_score * 100)}%</div>
            </div>

            {anomaly.flags && anomaly.flags.length > 0 ? (
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400 font-medium mb-2">Detected Anomalies:</div>
                <div className="flex flex-wrap gap-2">
                  {anomaly.flags.map((flag, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-100 dark:border-red-800">
                      <AlertTriangle className="w-4 h-4" /> {flag}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 p-2 rounded">
                <CheckCircle className="w-4 h-4" /> No anomalies detected
              </div>
            )}
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400 text-sm">Analysis data not available.</p>
        )}
      </section>

      {/* Decision Info */}
      <section>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4 border-b border-gray-200 dark:border-gray-800 pb-2">Routing & Decision</h3>
        {decision && (
          <div className="bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border border-gray-200 dark:border-gray-800 text-sm space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <span className="text-gray-500 dark:text-gray-400 block mb-1">Assigned Approver Role</span>
                <span className="font-medium flex items-center gap-2 text-gray-900 dark:text-gray-100">
                  <Shield className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
                  {decision.approver_role} (Level {decision.approver_level})
                </span>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400 block mb-1">Routing Reason</span>
                <span className="text-gray-900 dark:text-gray-100">{decision.reason}</span>
              </div>
            </div>

            {expense.decided_by && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <span className="text-gray-500 dark:text-gray-400 block mb-1">Final Decision</span>
                  <span className={cn(
                    "inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium",
                    expense.decision === 'approve' ? "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300" : "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300"
                  )}>
                    {expense.decision?.toUpperCase()}
                  </span>
                  <span className="ml-2 text-gray-600 dark:text-gray-400">by {expense.decided_by}</span>
                </div>
                {expense.decision_comment && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400 block mb-1">Reviewer Comment</span>
                    <span className="text-gray-900 dark:text-gray-100 italic">"{expense.decision_comment}"</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Warnings */}
      {result?.validation?.warnings && result.validation.warnings.length > 0 && (
        <section>
          <h3 className="text-lg font-medium text-amber-900 dark:text-amber-500 mb-2">Validation Warnings</h3>
          <ul className="list-disc pl-5 text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30 p-4 rounded-md border border-amber-100 dark:border-amber-800">
            {result.validation.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </section>
      )}

      {/* Provenance Summary from explanation endpoint */}
      {!loading && explanation && explanation.provenance_id && (
        <section>
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4 border-b border-gray-200 dark:border-gray-800 pb-2">Provenance Summary</h3>
          <div className="bg-indigo-50 dark:bg-indigo-900/30 p-4 rounded-lg border border-indigo-100 dark:border-indigo-800 text-sm space-y-2">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              <span className="text-gray-600 dark:text-gray-400">Provenance ID:</span>
              <span className="font-mono text-gray-900 dark:text-gray-100">{explanation.provenance_id}</span>
            </div>
            {explanation.provenance_hash && (
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                <span className="text-gray-600 dark:text-gray-400">Hash:</span>
                <span className="font-mono text-gray-900 dark:text-gray-100">{explanation.provenance_hash.substring(0, 24)}...</span>
              </div>
            )}
            {explanation.evidence_verified !== null && (
              <div className="flex items-center gap-2">
                {explanation.evidence_verified ? (
                  <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-500" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                )}
                <span className="text-gray-600 dark:text-gray-400">Evidence Verified:</span>
                <span className={explanation.evidence_verified ? "text-green-700 dark:text-green-400 font-medium" : "text-amber-700 dark:text-amber-400 font-medium"}>
                  {explanation.evidence_verified ? 'Yes' : 'Pending'}
                </span>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function LineageTab({ id }: { id: string }) {
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getLineage(id).then(setLineage).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="text-gray-500 dark:text-gray-400 py-4 text-center">Loading timeline...</div>;
  if (!lineage || !lineage.events.length) return <div className="text-gray-500 dark:text-gray-400 py-4 text-center">No timeline events found.</div>;

  return (
    <div className="py-4">
      <div className="flow-root">
        <ul role="list" className="-mb-8">
          {lineage.events.map((event, eventIdx) => (
            <li key={eventIdx}>
              <div className="relative pb-8">
                {eventIdx !== lineage.events.length - 1 ? (
                  <span className="absolute left-4 top-4 -ml-px h-full w-0.5 bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
                ) : null}
                <div className="relative flex space-x-3">
                  <div>
                    <span className={cn(
                      "h-8 w-8 rounded-full flex items-center justify-center ring-8 ring-white dark:ring-gray-900",
                      event.status === 'SUCCESS' || event.status === 'COMPLETED' ? "bg-green-500" :
                      event.status === 'FAILED' ? "bg-red-500" :
                      "bg-blue-500"
                    )}>
                      {event.status === 'SUCCESS' || event.status === 'COMPLETED' ? (
                        <CheckCircle className="h-4 w-4 text-white" aria-hidden="true" />
                      ) : event.status === 'FAILED' ? (
                        <XCircle className="h-4 w-4 text-white" aria-hidden="true" />
                      ) : (
                        <Activity className="h-4 w-4 text-white" aria-hidden="true" />
                      )}
                    </span>
                  </div>
                  <div className="flex min-w-0 flex-1 justify-between space-x-4 pt-1.5">
                    <div>
                      <p className="text-sm text-gray-900 dark:text-gray-100 font-medium">
                        {event.event_type.replace(/_/g, ' ')}
                        <span className="ml-2 px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 font-normal">
                          {event.source}
                        </span>
                      </p>
                    </div>
                    <div className="whitespace-nowrap text-right text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDateTime(event.timestamp)}
                    </div>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ProvenanceTab({ id }: { id: string }) {
  const [provenance, setProvenance] = useState<ProvenanceView | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getProvenance(id).then(setProvenance).catch(()=>{}).finally(() => setLoading(false));
  }, [id]);

  const handleVerify = async () => {
    if (!provenance) return;
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await verifyProvenance(provenance.provenance_id);
      setVerifyResult(res);
      if (res.status === 'PASS') {
        toast.success('Integrity verified: PASS');
      } else {
        toast.error('Integrity check FAILED');
      }
    } catch (err: any) {
      toast.error('Integrity check FAILED');
      setVerifyResult({
        provenance_id: provenance.provenance_id,
        status: 'FAIL',
        stored_hash: provenance.provenance_hash,
        recomputed_hash: 'error',
        failures: [err.message || 'Verification request failed']
      });
    } finally {
      setVerifying(false);
    }
  };

  const copyHash = () => {
    if (provenance?.provenance_hash) {
      navigator.clipboard.writeText(provenance.provenance_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading) return <div className="text-gray-500 dark:text-gray-400 py-4 text-center">Loading provenance...</div>;
  if (!provenance) return <div className="text-gray-500 dark:text-gray-400 py-4 text-center">Provenance record not found. It may not be generated yet.</div>;

  return (
    <div className="space-y-8">
      {/* Verification Status Banner */}
      {verifyResult && (
        <div className={cn(
          "p-4 rounded-md border flex items-start gap-3",
          verifyResult.status === 'PASS' ? "bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300" : "bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-800 dark:text-red-300"
        )}>
          {verifyResult.status === 'PASS' ? <CheckCircle className="w-6 h-6 mt-0.5" /> : <XCircle className="w-6 h-6 mt-0.5" />}
          <div>
            <h4 className="font-bold text-lg mb-1">
              {verifyResult.status === 'PASS' ? 'Integrity Verified ✓' : 'Integrity Verification Failed ✗'}
            </h4>
            <p className="text-sm opacity-90 mb-2">
              {verifyResult.status === 'PASS'
                ? 'The cryptographic hash matches the original computation. No tampering detected.'
                : 'The recomputed hash does not match the stored hash. The record may have been tampered with or is missing data.'}
            </p>
            <div className="text-xs font-mono bg-white dark:bg-gray-950 bg-opacity-50 p-2 rounded">
              <div>Stored: {verifyResult.stored_hash}</div>
              <div>Recomputed: {verifyResult.recomputed_hash}</div>
            </div>
            {verifyResult.failures && verifyResult.failures.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm font-medium">
                {verifyResult.failures.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Meta */}
      <section className="bg-gray-50 dark:bg-gray-800/50 p-5 rounded-lg border border-gray-200 dark:border-gray-800">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Provenance Record</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono mt-1">ID: {provenance.provenance_id}</p>
          </div>
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 shadow-sm text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors"
          >
            {verifying ? <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-600 dark:border-indigo-400" /> : <Shield className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />}
            Verify Integrity
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <div>
            <span className="text-gray-500 dark:text-gray-400 block">Context As Of</span>
            <span className="font-medium text-gray-900 dark:text-gray-100">{formatDateTime(provenance.context_as_of)}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400 block">Context Trust State</span>
            <span className="font-medium text-gray-900 dark:text-gray-100">{provenance.context_trust_state}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400 block">Engine Versions</span>
            <span className="font-medium text-gray-900 dark:text-gray-100">Decision: {provenance.decision_engine_version} | Risk: {provenance.risk_engine_version}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400 block">Cryptographic Hash</span>
            <div className="flex items-center gap-2">
              <span className="font-mono bg-white dark:bg-gray-950 px-2 py-1 border dark:border-gray-700 rounded truncate w-48 text-gray-900 dark:text-gray-100" title={provenance.provenance_hash}>
                {provenance.provenance_hash.substring(0, 16)}...
              </span>
              <button onClick={copyHash} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 bg-white dark:bg-gray-800 border dark:border-gray-700 rounded transition-colors">
                {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Evidence Summary */}
      <section>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Evidence Gathered</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <EvidenceCard title="Policy Evidence" count={provenance.policies.length} />
          <EvidenceCard title="Term Evidence" count={provenance.terms.length} />
          <EvidenceCard title="Rule Evidence" count={provenance.rules.length} />
          <EvidenceCard title="Trust Evidence" count={provenance.trust.length} />
          <EvidenceCard title="Risk Evidence" count={provenance.risk.length} />
          <EvidenceCard title="Human Evidence" count={provenance.human_decisions.length} />
        </div>
      </section>
    </div>
  );
}

function EvidenceCard({ title, count }: { title: string, count: number }) {
  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded p-4 text-center flex flex-col items-center justify-center bg-white dark:bg-gray-900 shadow-sm">
      <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">{count}</span>
      <span className="text-sm text-gray-500 dark:text-gray-400 font-medium">{title}</span>
    </div>
  );
}
