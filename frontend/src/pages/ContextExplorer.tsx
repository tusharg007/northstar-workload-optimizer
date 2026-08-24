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

const StatusBadge = ({ status }: { status: string }) => {
  const colors = {
    DRAFT: 'bg-gray-100 text-gray-800 border-gray-200',
    CERTIFIED: 'bg-green-100 text-green-800 border-green-200',
    RETIRED: 'bg-amber-100 text-amber-800 border-amber-200',
  };
  const color = colors[status as keyof typeof colors] || 'bg-gray-100 text-gray-800';
  
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

  const [expandedPolicy, setExpandedPolicy] = useState<string | null>(null);
  const [policyVersions, setPolicyVersions] = useState<Record<string, PolicyVersion[]>>({});
  
  const [expandedTerm, setExpandedTerm] = useState<string | null>(null);
  const [termVersions, setTermVersions] = useState<Record<string, TermVersion[]>>({});

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const [p, t] = await Promise.all([getPolicies(), getTerms()]);
        setPolicies(p);
        setTerms(t);
      } catch (e) {
        console.error('Error fetching context:', e);
      }
      setLoading(false);
    }
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

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading context...</div>;
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 flex items-center">
          <BookOpen className="mr-3 h-8 w-8 text-indigo-600" />
          Governed Context Explorer
        </h1>
        <p className="mt-2 text-gray-600">
          Browse policies and business terms governing the deterministic rules engine.
        </p>
      </div>

      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('policies')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center ${
              activeTab === 'policies'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Shield className="mr-2 h-5 w-5" />
            Policies
          </button>
          <button
            onClick={() => setActiveTab('terms')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center ${
              activeTab === 'terms'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <FileText className="mr-2 h-5 w-5" />
            Business Terms
          </button>
        </nav>
      </div>

      <div className="space-y-4">
        {activeTab === 'policies' && policies.map(policy => (
          <div key={policy.policy_key} className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
            <div 
              className="p-4 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
              onClick={() => togglePolicy(policy.policy_key)}
            >
              <div>
                <h3 className="text-lg font-medium text-gray-900">{policy.policy_name}</h3>
                <div className="mt-1 flex items-center space-x-4 text-sm text-gray-500">
                  <span className="font-mono bg-gray-100 px-1 rounded">{policy.policy_key}</span>
                  <span>Domain: {policy.domain}</span>
                  <span className="flex items-center"><User className="h-4 w-4 mr-1" /> {policy.owner.display_name}</span>
                  <span>{policy.version_count} versions</span>
                </div>
                <p className="mt-2 text-sm text-gray-600">{policy.description}</p>
              </div>
              <div>
                {expandedPolicy === policy.policy_key ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
              </div>
            </div>

            {expandedPolicy === policy.policy_key && (
              <div className="bg-gray-50 p-4 border-t border-gray-200">
                {!policyVersions[policy.policy_key] ? (
                  <div className="text-center text-sm text-gray-500">Loading versions...</div>
                ) : (
                  <div className="space-y-6">
                    {policyVersions[policy.policy_key].map(version => (
                      <div key={version.policy_version_id} className="bg-white p-4 rounded border border-gray-200 shadow-sm">
                        <div className="flex justify-between items-start mb-4">
                          <div>
                            <div className="flex items-center space-x-3">
                              <h4 className="text-md font-semibold text-gray-900">Version {version.version_number}</h4>
                              <StatusBadge status={version.status} />
                            </div>
                            <div className="mt-2 text-xs text-gray-500 space-y-1">
                              <div className="flex items-center">
                                <Calendar className="h-3 w-3 mr-1" />
                                Effective: {formatDate(version.effective_from)} {version.effective_to ? `- ${formatDate(version.effective_to)}` : '- Present'}
                              </div>
                              <div className="flex items-center">
                                <Hash className="h-3 w-3 mr-1" />
                                Hash: <span className="font-mono ml-1">{version.content_hash.substring(0, 12)}...</span>
                              </div>
                              {version.certified_at && (
                                <div className="text-indigo-600">
                                  Certified {formatDate(version.certified_at)}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                        
                        <div className="mt-4">
                          <h5 className="text-sm font-medium text-gray-900 mb-2 border-b pb-1">Rules</h5>
                          <div className="space-y-3">
                            {version.rules.map(rule => (
                              <div key={rule.policy_rule_id} className="bg-gray-50 rounded p-3 text-sm">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="font-semibold text-gray-800">{rule.rule_name}</span>
                                  <span className="font-mono text-xs text-gray-500 bg-gray-200 px-1 rounded">{rule.rule_key}</span>
                                </div>
                                <p className="text-gray-600 mb-2">{rule.description}</p>
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
          <div key={term.term_key} className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
            <div 
              className="p-4 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
              onClick={() => toggleTerm(term.term_key)}
            >
              <div>
                <h3 className="text-lg font-medium text-gray-900">{term.canonical_name}</h3>
                <div className="mt-1 flex items-center space-x-4 text-sm text-gray-500">
                  <span className="font-mono bg-gray-100 px-1 rounded">{term.term_key}</span>
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
              <div className="bg-gray-50 p-4 border-t border-gray-200">
                {!termVersions[term.term_key] ? (
                  <div className="text-center text-sm text-gray-500">Loading versions...</div>
                ) : (
                  <div className="space-y-4">
                    {termVersions[term.term_key].map(version => (
                      <div key={version.term_version_id} className="bg-white p-4 rounded border border-gray-200 shadow-sm">
                        <div className="flex justify-between items-start mb-3">
                          <div className="flex items-center space-x-3">
                            <h4 className="text-md font-semibold text-gray-900">Version {version.version_number}</h4>
                            <StatusBadge status={version.status} />
                          </div>
                        </div>
                        <div className="prose prose-sm text-gray-700 max-w-none mb-3 bg-gray-50 p-3 rounded">
                          {version.definition}
                        </div>
                        <div className="text-xs text-gray-500 flex flex-wrap gap-4">
                          <span className="flex items-center">
                            <Calendar className="h-3 w-3 mr-1" />
                            Effective: {formatDate(version.effective_from)} {version.effective_to ? `- ${formatDate(version.effective_to)}` : ''}
                          </span>
                          <span className="flex items-center">
                            <Hash className="h-3 w-3 mr-1" />
                            {version.content_hash.substring(0, 12)}...
                          </span>
                          {version.certified_at && (
                            <span className="text-indigo-600 font-medium">
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
    </div>
  );
}
