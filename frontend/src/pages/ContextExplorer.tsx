import React, { useEffect, useState } from 'react';
import { getPolicies, getPolicyVersions, getTerms, getTermVersions } from '../lib/api';
import { PolicySummary, PolicyVersion, TermSummary, TermVersion } from '../types';
import { formatDate } from '../lib/utils';
import {
  BookOpen,
  FileText,
  Shield,
  ChevronDown,
  ChevronUp,
  Hash,
  Calendar,
  User,
} from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorAlert } from '@/components/ui/error-alert';

const StatusBadge = ({ status }: { status: string }) => {
  const colors = {
    DRAFT: 'bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700',
    CERTIFIED: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
    RETIRED: 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800',
  };
  const color = colors[status as keyof typeof colors] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300';

  return (
    <span className={`px-2 py-1 text-xs font-medium border rounded-full ${color}`}>
      {status}
    </span>
  );
};

export default function ContextExplorer() {
  const [activeTab, setActiveTab] = useState<'policies' | 'terms'>('policies');
  const [policies, setPolicies] = useState<PolicySummary[]>([]);
  const [terms, setTerms] = useState<TermSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedPolicy, setExpandedPolicy] = useState<string | null>(null);
  const [policyVersions, setPolicyVersions] = useState<Record<string, PolicyVersion[]>>({});

  const [expandedTerm, setExpandedTerm] = useState<string | null>(null);
  const [termVersions, setTermVersions] = useState<Record<string, TermVersion[]>>({});

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, t] = await Promise.all([getPolicies(), getTerms()]);
      setPolicies(p);
      setTerms(t);
    } catch (e: any) {
      console.error('Error fetching context:', e);
      setError(e.message || 'Failed to load context');
    }
    setLoading(false);
  }

  useEffect(() => {
    fetchData();
  }, []);

  const togglePolicy = async (key: string) => {
    if (expandedPolicy === key) {
      setExpandedPolicy(null);
      return;
    }
    setExpandedPolicy(key);
    if (!policyVersions[key]) {
      try {
        const versions = await getPolicyVersions(key);
        setPolicyVersions(prev => ({ ...prev, [key]: versions }));
      } catch (e) {
        console.error(e);
      }
    }
  };

  const toggleTerm = async (key: string) => {
    if (expandedTerm === key) {
      setExpandedTerm(null);
      return;
    }
    setExpandedTerm(key);
    if (!termVersions[key]) {
      try {
        const versions = await getTermVersions(key);
        setTermVersions(prev => ({ ...prev, [key]: versions }));
      } catch (e) {
        console.error(e);
      }
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 flex items-center">
          <BookOpen className="mr-3 h-8 w-8 text-indigo-600 dark:text-indigo-400" />
          Governed Context Explorer
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Browse policies and business terms governing the deterministic rules engine.
        </p>
      </div>

      {error && <ErrorAlert message={error} onRetry={fetchData} />}

      <div className="border-b border-gray-200 dark:border-gray-800 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('policies')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center ${
              activeTab === 'policies'
                ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
            }`}
          >
            <Shield className="mr-2 h-5 w-5" />
            Policies
          </button>
          <button
            onClick={() => setActiveTab('terms')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center ${
              activeTab === 'terms'
                ? 'border-indigo-500 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
            }`}
          >
            <FileText className="mr-2 h-5 w-5" />
            Business Terms
          </button>
        </nav>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          {activeTab === 'policies' && policies.map(policy => (
            <div key={policy.policy_key} className="bg-white dark:bg-gray-900 rounded-lg shadow border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div
                className="p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center justify-between transition-colors"
                onClick={() => togglePolicy(policy.policy_key)}
              >
                <div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">{policy.policy_name}</h3>
                  <div className="mt-1 flex items-center space-x-4 text-sm text-gray-500 dark:text-gray-400">
                    <span className="font-mono bg-gray-100 dark:bg-gray-800 px-1 rounded">{policy.policy_key}</span>
                    <span>Domain: {policy.domain}</span>
                    <span className="flex items-center"><User className="h-4 w-4 mr-1" /> {policy.owner.display_name}</span>
                    <span>{policy.version_count} versions</span>
                  </div>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{policy.description}</p>
                </div>
                <div>
                  {expandedPolicy === policy.policy_key ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
                </div>
              </div>

              {expandedPolicy === policy.policy_key && (
                <div className="bg-gray-50 dark:bg-gray-800/30 p-4 border-t border-gray-200 dark:border-gray-800">
                  {!policyVersions[policy.policy_key] ? (
                    <div className="text-center text-sm text-gray-500 dark:text-gray-400"><Skeleton className="h-32 w-full" /></div>
                  ) : (
                    <div className="space-y-6">
                      {policyVersions[policy.policy_key].map(version => (
                        <div key={version.policy_version_id} className="bg-white dark:bg-gray-900 p-4 rounded border border-gray-200 dark:border-gray-800 shadow-sm">
                          <div className="flex justify-between items-start mb-4">
                            <div>
                              <div className="flex items-center space-x-3">
                                <h4 className="text-md font-semibold text-gray-900 dark:text-gray-100">Version {version.version_number}</h4>
                                <StatusBadge status={version.status} />
                              </div>
                              <div className="mt-2 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                                <div className="flex items-center">
                                  <Calendar className="h-3 w-3 mr-1" />
                                  Effective: {formatDate(version.effective_from)} {version.effective_to ? `- ${formatDate(version.effective_to)}` : '- Present'}
                                </div>
                                <div className="flex items-center">
                                  <Hash className="h-3 w-3 mr-1" />
                                  Hash: <span className="font-mono ml-1">{version.content_hash.substring(0, 12)}...</span>
                                </div>
                                {version.certified_at && (
                                  <div className="text-indigo-600 dark:text-indigo-400">
                                    Certified {formatDate(version.certified_at)}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="mt-4">
                            <h5 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2 border-b border-gray-200 dark:border-gray-700 pb-1">Rules</h5>
                            <div className="space-y-3">
                              {version.rules.map(rule => (
                                <div key={rule.policy_rule_id} className="bg-gray-50 dark:bg-gray-800/50 rounded p-3 text-sm">
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="font-semibold text-gray-800 dark:text-gray-200">{rule.rule_name}</span>
                                    <span className="font-mono text-xs text-gray-500 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 px-1 rounded">{rule.rule_key}</span>
                                  </div>
                                  <p className="text-gray-600 dark:text-gray-300 mb-2">{rule.description}</p>
                                  <div className="bg-gray-900 rounded p-2 overflow-x-auto">
                                    <pre className="text-xs text-green-400">
                                      {JSON.stringify(rule.parameters, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {activeTab === 'terms' && terms.map(term => (
            <div key={term.term_key} className="bg-white dark:bg-gray-900 rounded-lg shadow border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div
                className="p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center justify-between transition-colors"
                onClick={() => toggleTerm(term.term_key)}
              >
                <div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">{term.canonical_name}</h3>
                  <div className="mt-1 flex items-center space-x-4 text-sm text-gray-500 dark:text-gray-400">
                    <span className="font-mono bg-gray-100 dark:bg-gray-800 px-1 rounded">{term.term_key}</span>
                    <span>Domain: {term.domain}</span>
                    <span className="flex items-center"><User className="h-4 w-4 mr-1" /> {term.owner.display_name}</span>
                    <span>{term.version_count} versions</span>
                  </div>
                </div>
                <div>
                  {expandedTerm === term.term_key ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
                </div>
              </div>

              {expandedTerm === term.term_key && (
                <div className="bg-gray-50 dark:bg-gray-800/30 p-4 border-t border-gray-200 dark:border-gray-800">
                  {!termVersions[term.term_key] ? (
                    <div className="text-center text-sm text-gray-500 dark:text-gray-400"><Skeleton className="h-32 w-full" /></div>
                  ) : (
                    <div className="space-y-4">
                      {termVersions[term.term_key].map(version => (
                        <div key={version.term_version_id} className="bg-white dark:bg-gray-900 p-4 rounded border border-gray-200 dark:border-gray-800 shadow-sm">
                          <div className="flex justify-between items-start mb-3">
                            <div className="flex items-center space-x-3">
                              <h4 className="text-md font-semibold text-gray-900 dark:text-gray-100">Version {version.version_number}</h4>
                              <StatusBadge status={version.status} />
                            </div>
                          </div>
                          <div className="prose prose-sm text-gray-700 dark:text-gray-300 max-w-none mb-3 bg-gray-50 dark:bg-gray-800/50 p-3 rounded">
                            {version.definition}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 flex flex-wrap gap-4">
                            <span className="flex items-center">
                              <Calendar className="h-3 w-3 mr-1" />
                              Effective: {formatDate(version.effective_from)} {version.effective_to ? `- ${formatDate(version.effective_to)}` : ''}
                            </span>
                            <span className="flex items-center">
                              <Hash className="h-3 w-3 mr-1" />
                              {version.content_hash.substring(0, 12)}...
                            </span>
                            {version.certified_at && (
                              <span className="text-indigo-600 dark:text-indigo-400 font-medium">
                                Certified {formatDate(version.certified_at)}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
