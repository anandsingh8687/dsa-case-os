import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  FileText,
  CheckSquare,
  User,
  TrendingUp,
  FileDown,
  Download,
  Play,
} from 'lucide-react';
import {
  getCase,
  getCaseDocuments,
  updateCase,
  getDocumentChecklist,
  getFeatureVector,
  getEligibilityResults,
  runExtraction,
  runScoring,
  generateReport,
  getReportPdf,
  getCaseReport,
  getWhatsAppSummary,
  getNarrativeComprehensiveReport,
} from '../api/services';
import { Card, Button, Badge, Loading, ProgressBar, Modal } from '../components/ui';
import { formatPercentage, formatCurrency, formatDate } from '../utils/format';

const CaseDetail = () => {
  const { caseId } = useParams();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('documents');
  const [selectedProgram, setSelectedProgram] = useState('banking');
  const [selectedLender, setSelectedLender] = useState(null);
  const [manualCibil, setManualCibil] = useState('');

  const { data: caseData, isLoading: caseLoading } = useQuery({
    queryKey: ['case', caseId],
    queryFn: () => getCase(caseId),
  });

  const { data: checklistData } = useQuery({
    queryKey: ['checklist', caseId, selectedProgram],
    queryFn: () => getDocumentChecklist(caseId, selectedProgram),
    enabled: activeTab === 'checklist',
  });

  const { data: documentsData } = useQuery({
    queryKey: ['case-documents', caseId],
    queryFn: () => getCaseDocuments(caseId),
    enabled: !!caseId,
  });

  const { data: featuresData } = useQuery({
    queryKey: ['features', caseId],
    queryFn: () => getFeatureVector(caseId),
    enabled: activeTab === 'profile',
  });

  const { data: eligibilityData } = useQuery({
    queryKey: ['eligibility', caseId],
    queryFn: () => getEligibilityResults(caseId),
    enabled: activeTab === 'eligibility',
  });

  const { data: caseReportData } = useQuery({
    queryKey: ['case-report', caseId],
    queryFn: () => getCaseReport(caseId),
    enabled: activeTab === 'report' && !!caseId,
    retry: 1,
  });

  const { data: whatsappSummaryData } = useQuery({
    queryKey: ['report-whatsapp', caseId],
    queryFn: () => getWhatsAppSummary(caseId),
    enabled: activeTab === 'report' && !!caseId,
    retry: 1,
  });

  const { data: comprehensiveNarrativeData } = useQuery({
    queryKey: ['report-narrative-comprehensive', caseId],
    queryFn: () => getNarrativeComprehensiveReport(caseId),
    enabled: activeTab === 'report' && !!caseId,
    retry: 1,
  });

  const runScoringMutation = useMutation({
    mutationFn: () => runScoring(caseId),
    onSuccess: () => {
      toast.success('Scoring completed!');
      queryClient.invalidateQueries({ queryKey: ['eligibility', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Scoring failed');
    },
  });

  const generateReportMutation = useMutation({
    mutationFn: () => generateReport(caseId),
    onSuccess: () => {
      toast.success('Report generated!');
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-report', caseId] });
      queryClient.invalidateQueries({ queryKey: ['report-whatsapp', caseId] });
      queryClient.invalidateQueries({ queryKey: ['report-narrative-comprehensive', caseId] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Report generation failed');
    },
  });

  const downloadPdfMutation = useMutation({
    mutationFn: () => getReportPdf(caseId),
    onSuccess: (response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `case_${caseId}_report.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Report downloaded!');
    },
    onError: () => {
      toast.error('Failed to download report');
    },
  });

  const caseInfo = caseData?.data;
  const documents = Array.isArray(documentsData?.data) ? documentsData.data : [];
  const checklist = checklistData?.data || {};
  const features = featuresData?.data || {};
  const eligibility = eligibilityData?.data || {};
  const caseReport = caseReportData?.data || null;
  const whatsappSummary = typeof whatsappSummaryData?.data === 'string' ? whatsappSummaryData.data : '';
  const comprehensiveNarrative = comprehensiveNarrativeData?.data || null;
  const matchingEligibilityResults = Array.isArray(eligibility?.results)
    ? eligibility.results.filter((result) => result.hard_filter_status === 'pass')
    : [];
  const rejectedEligibilityResults = Array.isArray(eligibility?.results)
    ? eligibility.results.filter((result) => result.hard_filter_status === 'fail')
    : [];

  const runFullPipelineMutation = useMutation({
    mutationFn: async () => {
      await runExtraction(caseId);
      await runScoring(caseId);
      await generateReport(caseId);
    },
    onSuccess: () => {
      toast.success('All processing stages completed.');
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-documents', caseId] });
      queryClient.invalidateQueries({ queryKey: ['features', caseId] });
      queryClient.invalidateQueries({ queryKey: ['eligibility', caseId] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Full processing failed');
    },
  });

  const saveManualCibilMutation = useMutation({
    mutationFn: (value) =>
      updateCase(caseId, {
        cibil_score_manual: value,
      }),
    onSuccess: () => {
      toast.success('Manual CIBIL score saved.');
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
      queryClient.invalidateQueries({ queryKey: ['features', caseId] });
      queryClient.invalidateQueries({ queryKey: ['checklist', caseId] });
      queryClient.invalidateQueries({ queryKey: ['eligibility', caseId] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to save CIBIL score');
    },
  });

  useEffect(() => {
    if (caseInfo?.program_type) {
      setSelectedProgram(String(caseInfo.program_type).toLowerCase());
    }
  }, [caseInfo?.program_type]);

  useEffect(() => {
    const initialCibil =
      features?.cibil_score ??
      caseInfo?.cibil_score_manual ??
      '';
    setManualCibil(initialCibil === null || initialCibil === undefined ? '' : String(initialCibil));
  }, [features?.cibil_score, caseInfo?.cibil_score_manual]);

  const tabs = [
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'checklist', label: 'Checklist', icon: CheckSquare },
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'eligibility', label: 'Eligibility', icon: TrendingUp },
    { id: 'report', label: 'Report', icon: FileDown },
  ];

  if (caseLoading) {
    return <Loading size="lg" text="Loading case..." />;
  }

  return (
    <div>
      {/* Case Header */}
      <Card className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {caseInfo?.borrower_name || 'Unnamed Case'}
            </h1>
            <p className="text-sm text-gray-600 mt-1">{caseId}</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm text-gray-600">Completeness</div>
              <div className="text-2xl font-bold text-primary">
                {formatPercentage(caseInfo?.completeness_score)}
              </div>
            </div>
            <Badge variant="primary">{caseInfo?.status}</Badge>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-600">Entity:</span>
            <span className="ml-2 font-medium">{caseInfo?.entity_type}</span>
          </div>
          <div>
            <span className="text-gray-600">Program:</span>
            <span className="ml-2 font-medium">{caseInfo?.program_type}</span>
          </div>
          <div>
            <span className="text-gray-600">Industry:</span>
            <span className="ml-2 font-medium">{caseInfo?.industry_type || 'N/A'}</span>
          </div>
          <div>
            <span className="text-gray-600">Created:</span>
            <span className="ml-2 font-medium">{formatDate(caseInfo?.created_at)}</span>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <div className="mb-6">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-primary text-primary'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'documents' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Uploaded Documents</h2>
          {documents.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No documents uploaded</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Filename
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Confidence
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {doc.original_filename}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Badge variant="info">{doc.doc_type || 'Unknown'}</Badge>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatPercentage(doc.classification_confidence)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Badge variant={doc.status === 'classified' ? 'success' : 'warning'}>
                          {doc.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {activeTab === 'checklist' && (
        <div className="space-y-6">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Document Checklist</h2>
              <select
                value={selectedProgram}
                onChange={(e) => setSelectedProgram(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-lg"
              >
                {[
                  { value: 'banking', label: 'Banking' },
                  { value: 'income', label: 'Income' },
                  { value: 'hybrid', label: 'Hybrid' },
                ].map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <ProgressBar value={checklist?.completeness_score || caseInfo?.completeness_score || 0} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                <h3 className="font-semibold text-green-700 mb-2">
                  Available ({Array.isArray(checklist?.available) ? checklist.available.length : 0})
                </h3>
                {(checklist?.available || []).length === 0 ? (
                  <p className="text-gray-500">No required documents detected yet.</p>
                ) : (
                  <ul className="space-y-1 text-green-800">
                    {(checklist.available || []).map((docType) => (
                      <li key={`available-${docType}`}>• {docType}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <h3 className="font-semibold text-red-700 mb-2">
                  Missing ({Array.isArray(checklist?.missing) ? checklist.missing.length : 0})
                </h3>
                {(checklist?.missing || []).length === 0 ? (
                  <p className="text-gray-500">No missing required documents.</p>
                ) : (
                  <ul className="space-y-1 text-red-800">
                    {(checklist.missing || []).map((docType) => (
                      <li key={`missing-${docType}`}>• {docType}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 md:col-span-2">
                <h3 className="font-semibold text-blue-700 mb-2">
                  Unreadable Files ({Array.isArray(checklist?.unreadable) ? checklist.unreadable.length : 0})
                </h3>
                {(checklist?.unreadable || []).length === 0 ? (
                  <p className="text-gray-500">No unreadable files detected.</p>
                ) : (
                  <ul className="space-y-1 text-blue-800">
                    {(checklist.unreadable || []).map((name) => (
                      <li key={`unreadable-${name}`}>• {name}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="mt-4">
              <Button
                onClick={() => runFullPipelineMutation.mutate()}
                disabled={runFullPipelineMutation.isPending}
                className="flex items-center gap-2"
              >
                <Play className="w-4 h-4" />
                {runFullPipelineMutation.isPending ? 'Processing...' : 'Run Full Pipeline'}
              </Button>
              <p className="text-xs text-gray-500 mt-2">
                Runs extraction, eligibility scoring, and report generation sequentially.
              </p>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'profile' && (
        <Card>
          <h2 className="text-xl font-semibold mb-6">Borrower Profile</h2>
          {Object.keys(features).length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              No features extracted yet. Upload documents and run extraction.
            </p>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* IDENTITY Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-primary border-b pb-2">Identity</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Full Name</span>
                    <span className="font-medium text-right">{features.full_name || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">PAN Number</span>
                    <span className="font-medium text-right">{features.pan_number || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Aadhaar Number</span>
                    <span className="font-medium text-right">
                      {features.aadhaar_number ? `****${features.aadhaar_number.slice(-4)}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Date of Birth</span>
                    <span className="font-medium text-right">{features.dob || 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* BUSINESS Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-primary border-b pb-2">Business</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Entity Type</span>
                    <span className="font-medium text-right capitalize">{features.entity_type || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Business Vintage</span>
                    <span className="font-medium text-right">
                      {features.business_vintage_years ? `${features.business_vintage_years} years` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">GSTIN</span>
                    <span className="font-medium text-right">{features.gstin || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Industry</span>
                    <span className="font-medium text-right">{features.industry_type || caseInfo?.industry_type || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Pincode</span>
                    <span className="font-medium text-right">{features.pincode || caseInfo?.pincode || 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* FINANCIAL Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-primary border-b pb-2">Financial</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Annual Turnover</span>
                    <span className="font-medium text-right">
                      {features.annual_turnover ? `₹${Number(features.annual_turnover).toLocaleString('en-IN')} L` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Monthly Turnover</span>
                    <div className="text-right">
                      <span className="font-medium">
                        {features.monthly_turnover ? `₹${Number(features.monthly_turnover).toLocaleString('en-IN')}` : 'N/A'}
                      </span>
                      {features.monthly_turnover && (
                        <span className="ml-2 text-xs text-blue-600">from bank</span>
                      )}
                    </div>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Avg Monthly Balance</span>
                    <span className="font-medium text-right">
                      {features.avg_monthly_balance ? `₹${Number(features.avg_monthly_balance).toLocaleString('en-IN')}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Monthly Credits (Avg)</span>
                    <span className="font-medium text-right">
                      {features.monthly_credit_avg ? `₹${Number(features.monthly_credit_avg).toLocaleString('en-IN')}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">EMI Outflow (Monthly)</span>
                    <span className="font-medium text-right">
                      {features.emi_outflow_monthly ? `₹${Number(features.emi_outflow_monthly).toLocaleString('en-IN')}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Bounce Count (12M)</span>
                    <span className={`font-medium text-right ${
                      features.bounce_count_12m > 0 ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {features.bounce_count_12m !== null && features.bounce_count_12m !== undefined ? features.bounce_count_12m : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Cash Deposit Ratio</span>
                    <span className="font-medium text-right">
                      {features.cash_deposit_ratio ? `${(features.cash_deposit_ratio * 100).toFixed(1)}%` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">ITR Total Income</span>
                    <span className="font-medium text-right">
                      {features.itr_total_income ? `₹${Number(features.itr_total_income).toLocaleString('en-IN')} L` : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* CREDIT Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-primary border-b pb-2">Credit</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">CIBIL Score</span>
                    <span className={`text-2xl font-bold text-right ${
                      features.cibil_score >= 750 ? 'text-green-600' :
                      features.cibil_score >= 650 ? 'text-yellow-600' :
                      features.cibil_score ? 'text-red-600' : 'text-gray-400'
                    }`}>
                      {features.cibil_score || caseInfo?.cibil_score_manual || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Active Loan Count</span>
                    <span className="font-medium text-right">{features.active_loan_count || '0'}</span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Overdue Count</span>
                    <span className={`font-medium text-right ${
                      features.overdue_count > 0 ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {features.overdue_count !== null && features.overdue_count !== undefined ? features.overdue_count : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start">
                    <span className="text-sm text-gray-600">Enquiries (6M)</span>
                    <span className={`font-medium text-right ${
                      features.enquiry_count_6m > 3 ? 'text-yellow-600' : 'text-gray-900'
                    }`}>
                      {features.enquiry_count_6m !== null && features.enquiry_count_6m !== undefined ? features.enquiry_count_6m : 'N/A'}
                    </span>
                  </div>

                  <div className="pt-3 mt-3 border-t border-gray-100">
                    <label className="block text-sm text-gray-600 mb-2">
                      Manual CIBIL (if report unavailable)
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min="300"
                        max="900"
                        value={manualCibil}
                        onChange={(e) => setManualCibil(e.target.value)}
                        placeholder="Enter tentative CIBIL"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      <Button
                        variant="outline"
                        onClick={() => {
                          const parsed = Number(manualCibil);
                          if (!Number.isFinite(parsed) || parsed < 300 || parsed > 900) {
                            toast.error('Enter a valid CIBIL score between 300 and 900');
                            return;
                          }
                          saveManualCibilMutation.mutate(parsed);
                        }}
                        disabled={saveManualCibilMutation.isPending}
                      >
                        {saveManualCibilMutation.isPending ? 'Saving...' : 'Save'}
                      </Button>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      This value is used for scoring when CIBIL document is missing.
                    </p>
                  </div>
                </div>

                {/* Feature Completeness */}
                <div className="mt-6 pt-4 border-t">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-medium text-gray-600">Data Completeness</span>
                    <span className="text-sm font-semibold">
                      {features.feature_completeness ? `${features.feature_completeness.toFixed(0)}%` : '0%'}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary h-2 rounded-full transition-all"
                      style={{ width: `${features.feature_completeness || 0}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>
      )}

      {activeTab === 'eligibility' && (
        <div className="space-y-6">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Eligibility Results</h2>
              <Button
                onClick={() => runScoringMutation.mutate()}
                disabled={runScoringMutation.isPending}
                className="flex items-center gap-2"
              >
                <Play className="w-4 h-4" />
                {runScoringMutation.isPending ? 'Scoring...' : 'Run Scoring'}
              </Button>
            </div>

            {Array.isArray(eligibility?.results) && eligibility.results.length > 0 ? (
              <>
                {/* Rejection Analysis (when all lenders fail) */}
                {eligibility.lenders_passed === 0 && eligibility.rejection_reasons && eligibility.rejection_reasons.length > 0 && (
                  <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-6">
                    <h4 className="font-semibold text-red-800 mb-4 text-lg">Why No Lenders Matched</h4>

                    <div className="space-y-2 mb-6">
                      {eligibility.rejection_reasons.map((reason, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                          <span className="text-red-600 mt-0.5">✗</span>
                          <span className="text-sm text-red-700">{reason}</span>
                        </div>
                      ))}
                    </div>

                    <h5 className="font-semibold text-gray-800 mb-3">Suggested Actions to Improve Eligibility:</h5>
                    <div className="space-y-2 bg-white rounded-lg p-4">
                      {(eligibility.suggested_actions || []).map((action, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                          <span className="text-blue-600 mt-0.5">→</span>
                          <span className="text-sm text-gray-700">{action}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dynamic Recommendations */}
                {Array.isArray(eligibility.dynamic_recommendations) && eligibility.dynamic_recommendations.length > 0 && (
                  <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-6">
                    <h4 className="font-semibold text-blue-900 mb-3">Top Improvement Recommendations</h4>
                    <div className="space-y-2 text-sm">
                      {eligibility.dynamic_recommendations.slice(0, 4).map((rec, idx) => (
                        <div key={`rec-${idx}`} className="bg-white border border-blue-100 rounded-md p-3">
                          <div className="font-medium text-blue-900">{rec.title || rec.recommendation || 'Recommendation'}</div>
                          {rec.impact && (
                            <div className="text-blue-700 mt-1">Impact: {rec.impact}</div>
                          )}
                          {rec.detail && (
                            <div className="text-gray-600 mt-1">{rec.detail}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className={`mb-4 text-sm ${
                  eligibility.lenders_passed === 0 ? 'text-red-600 font-medium' : 'text-gray-600'
                }`}>
                  {eligibility.lenders_passed} of {eligibility.total_lenders_evaluated} lenders matched
                  {eligibility.lenders_passed === 0 && ' - See analysis above for improvement suggestions'}
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Rank
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Lender
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Score
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Probability
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Max Ticket
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Why This Score
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {matchingEligibilityResults.map((result, index) => {
                        const probability = String(result.approval_probability || '').toUpperCase();
                        const scoreBreakdown = result?.hard_filter_details?.score_breakdown || [];
                        return (
                          <tr
                            key={`${result.lender_name}-${result.product_name}`}
                            className="cursor-pointer hover:bg-gray-50"
                            onClick={() => setSelectedLender(result)}
                          >
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                              #{result.rank || index + 1}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap font-medium">
                              {result.lender_name}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className="text-lg font-bold text-primary">
                                {Math.round(result.eligibility_score || 0)}/100
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <Badge
                                variant={
                                  probability === 'HIGH'
                                    ? 'success'
                                    : probability === 'MEDIUM'
                                    ? 'warning'
                                    : 'danger'
                                }
                              >
                                {probability || 'N/A'}
                              </Badge>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap font-medium">
                              {formatCurrency(result.expected_ticket_max)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-600">
                              {scoreBreakdown.length > 0
                                ? `${scoreBreakdown.length} components`
                                : 'Click to view scoring details'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Non-matching lenders */}
                <div className="mt-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">
                    Why Other Lenders Did Not Match ({rejectedEligibilityResults.length})
                  </h3>
                  {rejectedEligibilityResults.length === 0 ? (
                    <p className="text-sm text-gray-500">All evaluated lenders matched current hard filters.</p>
                  ) : (
                    <div className="overflow-x-auto border border-gray-200 rounded-lg">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Product</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Primary Reason</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {rejectedEligibilityResults.map((result, idx) => {
                            const reasons = Object.values(result.hard_filter_details || {});
                            return (
                              <tr
                                key={`reject-${result.lender_name}-${result.product_name}-${idx}`}
                                className="hover:bg-gray-50 cursor-pointer"
                                onClick={() => setSelectedLender(result)}
                              >
                                <td className="px-4 py-3 text-sm font-medium text-gray-900">{result.lender_name}</td>
                                <td className="px-4 py-3 text-sm text-gray-700">{result.product_name}</td>
                                <td className="px-4 py-3 text-sm text-red-700">{reasons[0] || 'Hard filter not met'}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <p className="text-xs text-gray-500 mt-2">
                    Click any lender row to view complete acceptance/rejection logic.
                  </p>
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-center py-8">
                No eligibility results yet. Click "Run Scoring" to generate results.
              </p>
            )}
          </Card>
        </div>
      )}

      {activeTab === 'report' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Report</h2>
          <div className="space-y-4">
            <div className="flex gap-3">
              <Button
                onClick={() => generateReportMutation.mutate()}
                disabled={generateReportMutation.isPending}
                variant="primary"
              >
                {generateReportMutation.isPending
                  ? 'Generating...'
                  : 'Generate Report'}
              </Button>
              <Button
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ['case-report', caseId] });
                  queryClient.invalidateQueries({ queryKey: ['report-whatsapp', caseId] });
                  queryClient.invalidateQueries({ queryKey: ['report-narrative-comprehensive', caseId] });
                }}
                variant="outline"
              >
                Refresh Summary
              </Button>
              <Button
                onClick={() => downloadPdfMutation.mutate()}
                disabled={downloadPdfMutation.isPending}
                variant="success"
                className="flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                {downloadPdfMutation.isPending ? 'Downloading...' : 'Download PDF'}
              </Button>
            </div>

            {caseInfo?.status === 'report_generated' && (
              <div className="space-y-4">
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <h3 className="font-semibold text-green-800 mb-1">Report Preview</h3>
                  <p className="text-sm text-green-700">
                    Report is generated. Download PDF for lender-ready document.
                  </p>
                </div>

                {caseReport && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="p-4 rounded-lg border border-gray-200 bg-gray-50">
                      <h4 className="font-semibold mb-2">Strengths</h4>
                      {(caseReport.strengths || []).length === 0 ? (
                        <p className="text-sm text-gray-500">No strengths captured yet.</p>
                      ) : (
                        <ul className="text-sm text-gray-700 space-y-1">
                          {(caseReport.strengths || []).map((item, idx) => (
                            <li key={`str-${idx}`}>• {item}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="p-4 rounded-lg border border-gray-200 bg-gray-50">
                      <h4 className="font-semibold mb-2">Risk Flags</h4>
                      {(caseReport.risk_flags || []).length === 0 ? (
                        <p className="text-sm text-gray-500">No major risks flagged.</p>
                      ) : (
                        <ul className="text-sm text-gray-700 space-y-1">
                          {(caseReport.risk_flags || []).map((item, idx) => (
                            <li key={`risk-${idx}`}>• {item}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="p-4 rounded-lg border border-gray-200 bg-gray-50 lg:col-span-2">
                      <h4 className="font-semibold mb-2">Submission Strategy</h4>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap">
                        {caseReport.submission_strategy || 'No strategy generated yet.'}
                      </p>
                    </div>
                  </div>
                )}

                {comprehensiveNarrative?.success && (
                  <div className="p-4 rounded-lg border border-blue-200 bg-blue-50">
                    <h4 className="font-semibold text-blue-900 mb-2">LLM Summary Journey</h4>
                    <p className="text-sm text-blue-900 whitespace-pre-wrap">
                      {comprehensiveNarrative?.sections?.executive_summary ||
                        comprehensiveNarrative?.narrative ||
                        'Narrative summary unavailable.'}
                    </p>
                  </div>
                )}

                {whatsappSummary && (
                  <div className="p-4 rounded-lg border border-gray-200 bg-white">
                    <h4 className="font-semibold mb-2">Quick Share Summary</h4>
                    <textarea
                      readOnly
                      value={whatsappSummary}
                      rows={8}
                      className="w-full border border-gray-300 rounded-lg p-3 text-sm text-gray-700 bg-gray-50"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      <Modal
        isOpen={!!selectedLender}
        onClose={() => setSelectedLender(null)}
        title={
          selectedLender
            ? `${selectedLender.lender_name} • ${selectedLender.product_name}`
            : 'Lender Details'
        }
        size="lg"
      >
        {!selectedLender ? null : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Status:</span>{' '}
                <span className={`font-medium ${selectedLender.hard_filter_status === 'pass' ? 'text-green-700' : 'text-red-700'}`}>
                  {selectedLender.hard_filter_status === 'pass' ? 'Matched' : 'Not Matched'}
                </span>
              </div>
              <div>
                <span className="text-gray-500">Score:</span>{' '}
                <span className="font-medium">
                  {selectedLender.eligibility_score !== null && selectedLender.eligibility_score !== undefined
                    ? `${Math.round(selectedLender.eligibility_score)}/100`
                    : 'N/A'}
                </span>
              </div>
            </div>

            {selectedLender.hard_filter_status === 'pass' ? (
              <>
                <div className="rounded-lg border border-green-200 bg-green-50 p-3">
                  <h4 className="font-semibold text-green-900 mb-1">Why this lender matched</h4>
                  <ul className="text-sm text-green-900 space-y-1">
                    {(selectedLender?.hard_filter_details?.matched_signals || []).map((signal, idx) => (
                      <li key={`signal-${idx}`}>• {signal}</li>
                    ))}
                  </ul>
                </div>

                <div>
                  <h4 className="font-semibold mb-2">Score Breakdown</h4>
                  {(selectedLender?.hard_filter_details?.score_breakdown || []).length === 0 ? (
                    <p className="text-sm text-gray-500">No component-level breakdown available yet.</p>
                  ) : (
                    <div className="overflow-x-auto border border-gray-200 rounded-lg">
                      <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Component</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Weight</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Contribution</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {(selectedLender.hard_filter_details.score_breakdown || []).map((item, idx) => (
                            <tr key={`score-part-${idx}`}>
                              <td className="px-3 py-2">{item.label || item.component}</td>
                              <td className="px-3 py-2">{item.weight}%</td>
                              <td className="px-3 py-2">{Math.round(item.score || 0)}</td>
                              <td className="px-3 py-2">{item.weighted_contribution || 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                <h4 className="font-semibold text-red-900 mb-2">Why this lender did not match</h4>
                <ul className="text-sm text-red-900 space-y-1">
                  {Object.entries(selectedLender?.hard_filter_details || {}).map(([key, reason]) => (
                    <li key={`reason-${key}`}>• {String(reason)}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default CaseDetail;
