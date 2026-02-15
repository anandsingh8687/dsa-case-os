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
  Calculator,
  BarChart3,
} from 'lucide-react';
import {
  getCase,
  getCaseDocuments,
  updateCase,
  getDocumentChecklist,
  getFeatureVector,
  getEligibilityResults,
  getEligibilityExplanation,
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
import { getUser } from '../utils/auth';

const lakhToRupees = (valueInLakhs) => {
  if (valueInLakhs === null || valueInLakhs === undefined || Number.isNaN(Number(valueInLakhs))) {
    return null;
  }
  return Number(valueInLakhs) * 100000;
};

const formatLakhAmount = (valueInLakhs) => {
  const rupees = lakhToRupees(valueInLakhs);
  return formatCurrency(rupees);
};

const parseInterestRange = (rawRange) => {
  if (!rawRange || typeof rawRange !== 'string') return null;
  const nums = rawRange.match(/\\d+(?:\\.\\d+)?/g);
  if (!nums || nums.length === 0) return null;
  const values = nums.map((n) => Number(n)).filter((n) => Number.isFinite(n));
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { min, max, midpoint: (min + max) / 2 };
};

const calculateEmi = (principal, annualRatePct, tenureMonths) => {
  if (!principal || !annualRatePct || !tenureMonths) return null;
  const monthlyRate = annualRatePct / 12 / 100;
  if (monthlyRate === 0) return principal / tenureMonths;
  const factor = Math.pow(1 + monthlyRate, tenureMonths);
  return (principal * monthlyRate * factor) / (factor - 1);
};

const buildRpsSchedule = (principal, annualRatePct, tenureMonths, rows = 12) => {
  const emi = calculateEmi(principal, annualRatePct, tenureMonths);
  if (!emi) return [];
  const monthlyRate = annualRatePct / 12 / 100;
  const schedule = [];
  let opening = principal;
  for (let month = 1; month <= tenureMonths; month += 1) {
    const interest = opening * monthlyRate;
    const principalPart = emi - interest;
    const closing = Math.max(0, opening - principalPart);
    if (month <= rows) {
      schedule.push({
        month,
        opening,
        emi,
        principal: principalPart,
        interest,
        closing,
      });
    }
    opening = closing;
  }
  return schedule;
};

const buildMatchedSignalsForModal = (selectedLender, features) => {
  const signals = selectedLender?.hard_filter_details?.matched_signals;
  if (Array.isArray(signals) && signals.length > 0) {
    return signals;
  }

  const fallbacks = [];
  const entityType = features?.entity_type || features?.entityType;
  const cibil = features?.cibil_score ?? features?.cibilScore;
  const vintage = features?.business_vintage_years ?? features?.businessVintageYears;
  const turnover = features?.annual_turnover ?? features?.annualTurnover;
  const pincode = features?.pincode;
  const score = selectedLender?.eligibility_score;

  if (entityType) fallbacks.push(`Entity type accepted: ${entityType}`);
  if (cibil !== null && cibil !== undefined) fallbacks.push(`CIBIL considered: ${cibil}`);
  if (vintage !== null && vintage !== undefined) {
    fallbacks.push(`Business vintage considered: ${vintage} years`);
  }
  if (turnover !== null && turnover !== undefined) {
    fallbacks.push(`Annual turnover considered: ₹${turnover}L`);
  }
  if (pincode) fallbacks.push(`Pincode serviceability passed: ${pincode}`);
  if (score !== null && score !== undefined) {
    fallbacks.push(`Composite eligibility score: ${Math.round(score)}/100`);
  }

  return fallbacks.length > 0 ? fallbacks : ['Hard filters passed for this lender profile.'];
};

const DOCUMENTATION_FRAMEWORK_2026 = {
  commonKyc: [
    'PAN Card',
    'Aadhaar Card (or Passport/Voter ID)',
    'Address proof (utility bill/rent agreement/Voter ID)',
    'Recent passport-size photographs',
  ],
  banking: {
    title: 'Business / Banking Flow',
    sections: [
      {
        label: 'Core Business Proof',
        docs: [
          '12 months bank statements',
          'GST certificate + latest GST returns',
          'PAN (personal/business) + Aadhaar',
          'Optional strengtheners: Udyam, property papers, financial statements',
        ],
      },
    ],
  },
  income: {
    title: 'Personal Loan Flow',
    sections: [
      {
        label: 'Salaried',
        docs: [
          'Last 3-6 salary slips',
          'Form 16 (2 years)',
          '6 months salary-credit bank statements',
          'Employment proof (if requested by lender)',
        ],
      },
      {
        label: 'Self-Employed',
        docs: [
          'ITR with computation (2-3 years)',
          'Audited P&L and balance sheet',
          'Business registration proof (GST/Trade License)',
          '6-12 months business bank statements',
        ],
      },
      {
        label: 'Purpose-based add-ons',
        docs: [
          'Wedding loan: invitation card (some lenders)',
          'Medical loan: hospital estimate/bills',
          'Education PL: admission letter + fee structure',
        ],
      },
    ],
  },
  hybrid: {
    title: 'Home / Secured Loan Flow',
    sections: [
      {
        label: 'Home Purchase',
        docs: [
          'Agreement to Sale + Sale Deed',
          'Title/Mother deed chain',
          'Encumbrance Certificate (13-30 years)',
          'Approved building plan',
        ],
      },
      {
        label: 'Construction / Renovation / Plot',
        docs: [
          'Approved architectural plan + building permit',
          'Engineer/architect cost estimate',
          'Renovation quotation + ownership proof',
          'Plot NA conversion certificate (where applicable)',
        ],
      },
      {
        label: 'NRI / Balance Transfer',
        docs: [
          'Passport/Visa/OCI + overseas employment proof',
          'NRE/NRO statements (6 months)',
          'POA (if applicable)',
          'Foreclosure letter + LOD + repayment track for BT',
        ],
      },
    ],
  },
};

const CaseDetail = () => {
  const { caseId } = useParams();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('documents');
  const [selectedProgram, setSelectedProgram] = useState('banking');
  const [selectedLender, setSelectedLender] = useState(null);
  const [manualCibil, setManualCibil] = useState('');
  const [emiLoanAmountLakhs, setEmiLoanAmountLakhs] = useState(10);
  const [emiTenureMonths, setEmiTenureMonths] = useState(36);
  const [rpsPreview, setRpsPreview] = useState(null);
  const [emailLenderKey, setEmailLenderKey] = useState('');
  const [rmEmail, setRmEmail] = useState('');

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
    enabled: activeTab === 'profile' || activeTab === 'eligibility',
  });

  const { data: eligibilityData } = useQuery({
    queryKey: ['eligibility', caseId],
    queryFn: () => getEligibilityResults(caseId),
    enabled: activeTab === 'eligibility',
  });

  const { data: eligibilityExplainData } = useQuery({
    queryKey: ['eligibility-explain', caseId],
    queryFn: () => getEligibilityExplanation(caseId),
    enabled: activeTab === 'eligibility',
    retry: 1,
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
  const eligibilityExplain = eligibilityExplainData?.data || null;
  const caseReport = caseReportData?.data || null;
  const whatsappSummary = typeof whatsappSummaryData?.data === 'string' ? whatsappSummaryData.data : '';
  const comprehensiveNarrative = comprehensiveNarrativeData?.data || null;
  const matchingEligibilityResults = Array.isArray(eligibility?.results)
    ? eligibility.results.filter((result) => result.hard_filter_status === 'pass')
    : [];
  const rejectedEligibilityResults = Array.isArray(eligibility?.results)
    ? eligibility.results.filter((result) => result.hard_filter_status === 'fail')
    : [];
  const firstMatchTicket = matchingEligibilityResults[0]?.expected_ticket_max;

  const emiLoanAmountRupees = lakhToRupees(emiLoanAmountLakhs);
  const selectedEmailLender = matchingEligibilityResults.find(
    (item) => `${item.lender_name}::${item.product_name}` === emailLenderKey
  ) || null;
  const selectedLenderSignals = buildMatchedSignalsForModal(selectedLender, features);
  const docFramework =
    DOCUMENTATION_FRAMEWORK_2026[selectedProgram] || DOCUMENTATION_FRAMEWORK_2026.banking;

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

  useEffect(() => {
    const requested = Number(caseInfo?.loan_amount_requested);
    if (Number.isFinite(requested) && requested > 0) {
      setEmiLoanAmountLakhs(requested);
      return;
    }

    const suggested = Number(firstMatchTicket);
    if (Number.isFinite(suggested) && suggested > 0) {
      setEmiLoanAmountLakhs(suggested);
    }
  }, [caseInfo?.loan_amount_requested, firstMatchTicket]);

  useEffect(() => {
    if (!matchingEligibilityResults.length) return;
    if (!emailLenderKey) {
      const first = matchingEligibilityResults[0];
      setEmailLenderKey(`${first.lender_name}::${first.product_name}`);
    }
  }, [matchingEligibilityResults.length, emailLenderKey]);

  const tabs = [
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'checklist', label: 'Checklist', icon: CheckSquare },
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'eligibility', label: 'Eligibility', icon: TrendingUp },
    { id: 'report', label: 'Report', icon: FileDown },
  ];

  const openMailtoDraft = () => {
    if (!selectedEmailLender) {
      toast.error('Select a lender first');
      return;
    }
    if (!rmEmail) {
      toast.error('Enter lender RM email');
      return;
    }

    const loggedInUser = getUser();
    const ticketText = formatLakhAmount(selectedEmailLender.expected_ticket_max);
    const strengths = (caseReport?.strengths || []).slice(0, 3).join('; ') || 'Clean basic profile';
    const docNames = documents.map((doc) => doc.original_filename).filter(Boolean).slice(0, 8).join(', ') || 'Available in case folder';
    const subject = `[Credilo] ${selectedEmailLender.product_name} Case Submission - ${caseInfo?.borrower_name || caseId} (${caseId})`;
    const body = [
      `Dear Team ${selectedEmailLender.lender_name},`,
      '',
      `Please find below a new ${selectedEmailLender.product_name} opportunity for your review:`,
      `- Borrower: ${caseInfo?.borrower_name || 'N/A'}`,
      `- Entity: ${caseInfo?.entity_type || 'N/A'}`,
      `- CIBIL: ${features?.cibil_score || caseInfo?.cibil_score_manual || 'N/A'}`,
      `- Business Vintage: ${features?.business_vintage_years || caseInfo?.business_vintage_years || 'N/A'} years`,
      `- Requested Loan: ${formatLakhAmount(caseInfo?.loan_amount_requested)}`,
      `- Indicative Eligible Ticket: ${ticketText}`,
      `- Pincode: ${features?.pincode || caseInfo?.pincode || 'N/A'}`,
      '',
      `Key strengths: ${strengths}`,
      `Documents available: ${docNames}`,
      '',
      `Please share eligibility feedback and next steps.`,
      '',
      'Regards,',
      `${loggedInUser?.full_name || 'DSA Team'}`,
      'Credilo',
    ].join('\\n');

    const mailto = `mailto:${encodeURIComponent(rmEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.location.href = mailto;
  };

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

            <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
              <h3 className="font-semibold text-gray-900 mb-2">
                Standardized Documentation Framework (2026)
              </h3>
              <p className="text-xs text-gray-600 mb-3">
                Guidance checklist to reduce back-and-forth with borrowers and improve first-pass lender submissions.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div className="rounded-md border border-gray-200 bg-white p-3">
                  <div className="font-medium text-gray-900 mb-2">Core Mandatory KYC (All Loans)</div>
                  <ul className="space-y-1 text-gray-700">
                    {DOCUMENTATION_FRAMEWORK_2026.commonKyc.map((item) => (
                      <li key={`kyc-${item}`}>• {item}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-md border border-gray-200 bg-white p-3">
                  <div className="font-medium text-gray-900 mb-2">{docFramework.title}</div>
                  <div className="space-y-3">
                    {(docFramework.sections || []).map((section) => (
                      <div key={section.label}>
                        <div className="font-medium text-gray-800">{section.label}</div>
                        <ul className="space-y-1 text-gray-700 mt-1">
                          {section.docs.map((docLine) => (
                            <li key={`${section.label}-${docLine}`}>• {docLine}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
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
                {eligibilityExplain?.executive_summary && (
                  <div className="mb-6 bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                    <h4 className="font-semibold text-indigo-900 mb-2">BRE Summary</h4>
                    <p className="text-sm text-indigo-900">{eligibilityExplain.executive_summary}</p>
                  </div>
                )}

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
                              {formatLakhAmount(result.expected_ticket_max)}
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

                {/* EMI Comparison + RPS (Feature 5) */}
                {matchingEligibilityResults.length > 0 && (
                  <div className="mt-8 rounded-lg border border-gray-200 p-4">
                    <div className="flex items-center gap-2 mb-4">
                      <Calculator className="w-5 h-5 text-primary" />
                      <h3 className="text-lg font-semibold text-gray-900">EMI Comparison & Repayment Schedule</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                      <div>
                        <label className="block text-xs text-gray-600 mb-1">Loan Amount (Lakhs)</label>
                        <input
                          type="number"
                          min="1"
                          step="0.5"
                          value={emiLoanAmountLakhs}
                          onChange={(e) => setEmiLoanAmountLakhs(Number(e.target.value || 0))}
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 mb-1">Tenure (Months)</label>
                        <input
                          type="number"
                          min="6"
                          max="120"
                          value={emiTenureMonths}
                          onChange={(e) => setEmiTenureMonths(Number(e.target.value || 0))}
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                      </div>
                      <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2 text-sm">
                        <div className="text-gray-600">Affordability Headroom</div>
                        <div className="font-semibold text-gray-900 mt-1">
                          {(() => {
                            const monthlyInflow = Number(features.monthly_credit_avg || 0);
                            const existingEmi = Number(features.emi_outflow_monthly || 0);
                            if (!monthlyInflow) return 'N/A';
                            const capacity = Math.max(0, monthlyInflow * 0.5 - existingEmi);
                            return `${formatCurrency(capacity)} / month`;
                          })()}
                        </div>
                      </div>
                    </div>

                    <div className="overflow-x-auto border border-gray-200 rounded-lg">
                      <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rate</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Monthly EMI</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Total Cost</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Processing Fee</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">RPS</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {matchingEligibilityResults.map((result, idx) => {
                            const lenderTerms = result?.hard_filter_details?.lender_terms || {};
                            const rateRange = parseInterestRange(lenderTerms.interest_rate_range);
                            const annualRate = rateRange?.midpoint || 18;
                            const emi = calculateEmi(emiLoanAmountRupees, annualRate, emiTenureMonths);
                            const totalCost = emi ? emi * emiTenureMonths : null;
                            const processingFeePct = Number(lenderTerms.processing_fee_pct || 0);
                            const processingFeeAmount = emiLoanAmountRupees
                              ? (emiLoanAmountRupees * processingFeePct) / 100
                              : null;
                            return (
                              <tr key={`emi-${result.lender_name}-${idx}`}>
                                <td className="px-4 py-3 font-medium text-gray-900">
                                  {result.lender_name}
                                  <div className="text-xs text-gray-500">{result.product_name}</div>
                                </td>
                                <td className="px-4 py-3 text-gray-700">
                                  {lenderTerms.interest_rate_range || `${annualRate.toFixed(1)}% (assumed)`}
                                </td>
                                <td className="px-4 py-3 font-semibold text-gray-900">{formatCurrency(emi)}</td>
                                <td className="px-4 py-3 text-gray-700">{formatCurrency(totalCost)}</td>
                                <td className="px-4 py-3 text-gray-700">
                                  {processingFeePct > 0
                                    ? `${processingFeePct}% (${formatCurrency(processingFeeAmount)})`
                                    : 'N/A'}
                                </td>
                                <td className="px-4 py-3">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="flex items-center gap-1"
                                    onClick={() =>
                                      setRpsPreview({
                                        lender: result.lender_name,
                                        annualRate,
                                        schedule: buildRpsSchedule(emiLoanAmountRupees, annualRate, emiTenureMonths, 18),
                                      })
                                    }
                                  >
                                    <BarChart3 className="w-3.5 h-3.5" />
                                    View RPS
                                  </Button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

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

                {/* Dynamic Recommendations - moved to end per UX request */}
                {Array.isArray(eligibility.dynamic_recommendations) && eligibility.dynamic_recommendations.length > 0 && (
                  <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
                    <h4 className="font-semibold text-blue-900 mb-3">Top Improvement Recommendations</h4>
                    <div className="space-y-3 text-sm">
                      {eligibility.dynamic_recommendations.slice(0, 5).map((rec, idx) => {
                        const title = rec.issue || rec.title || rec.action || null;
                        const action = rec.action || rec.detail || null;
                        const impact = rec.impact || null;
                        const current = rec.current || null;
                        const target = rec.target || null;
                        const lendersAffected = Array.isArray(rec.lenders_affected) ? rec.lenders_affected : [];

                        return (
                          <div key={`rec-end-${idx}`} className="bg-white border border-blue-100 rounded-md p-4">
                            {title && <div className="font-semibold text-blue-900">{title}</div>}
                            {action && <div className="text-gray-700 mt-1">{action}</div>}
                            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                              {impact && <div className="text-blue-700">Impact: {impact}</div>}
                              {(current || target) && (
                                <div className="text-gray-600">
                                  {current ? `Current: ${current}` : ''}
                                  {current && target ? ' | ' : ''}
                                  {target ? `Target: ${target}` : ''}
                                </div>
                              )}
                            </div>
                            {lendersAffected.length > 0 && (
                              <div className="text-xs text-gray-500 mt-2">
                                Affects: {lendersAffected.slice(0, 5).join(', ')}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {Array.isArray(eligibilityExplain?.top_actions) && eligibilityExplain.top_actions.length > 0 && (
                      <div className="mt-4 pt-4 border-t border-blue-100">
                        <h5 className="font-medium text-blue-900 mb-2">Immediate Actions</h5>
                        <ul className="space-y-1 text-sm text-blue-900">
                          {eligibilityExplain.top_actions.slice(0, 4).map((action, idx) => (
                            <li key={`top-action-end-${idx}`}>• {action}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
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

                {matchingEligibilityResults.length > 0 && (
                  <div className="p-4 rounded-lg border border-gray-200 bg-white">
                    <h4 className="font-semibold mb-3">Email Collaboration (Lender RM)</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="md:col-span-1">
                        <label className="block text-xs text-gray-600 mb-1">Lender</label>
                        <select
                          value={emailLenderKey}
                          onChange={(e) => setEmailLenderKey(e.target.value)}
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        >
                          {matchingEligibilityResults.map((lender) => (
                            <option
                              key={`mail-lender-${lender.lender_name}-${lender.product_name}`}
                              value={`${lender.lender_name}::${lender.product_name}`}
                            >
                              {lender.lender_name} • {lender.product_name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="md:col-span-1">
                        <label className="block text-xs text-gray-600 mb-1">RM Email</label>
                        <input
                          type="email"
                          value={rmEmail}
                          onChange={(e) => setRmEmail(e.target.value)}
                          placeholder="rm@lender.com"
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                      </div>
                      <div className="md:col-span-1 flex items-end">
                        <Button className="w-full" onClick={openMailtoDraft}>
                          Open Email Draft
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      Opens your email client with prefilled case summary, strengths, and document list.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      <Modal
        isOpen={!!rpsPreview}
        onClose={() => setRpsPreview(null)}
        title={rpsPreview ? `Repayment Schedule • ${rpsPreview.lender}` : 'Repayment Schedule'}
        size="lg"
      >
        {!rpsPreview ? null : (
          <div>
            <div className="text-sm text-gray-600 mb-3">
              Estimated at {rpsPreview.annualRate.toFixed(2)}% annual interest.
            </div>
            <div className="overflow-x-auto border border-gray-200 rounded-lg">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Month</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Opening</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">EMI</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Principal</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Interest</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Closing</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {rpsPreview.schedule.map((row) => (
                    <tr key={`rps-${row.month}`}>
                      <td className="px-3 py-2">{row.month}</td>
                      <td className="px-3 py-2">{formatCurrency(row.opening)}</td>
                      <td className="px-3 py-2">{formatCurrency(row.emi)}</td>
                      <td className="px-3 py-2">{formatCurrency(row.principal)}</td>
                      <td className="px-3 py-2">{formatCurrency(row.interest)}</td>
                      <td className="px-3 py-2">{formatCurrency(row.closing)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Preview shows first {rpsPreview.schedule.length} months for quick discussion during lender/customer calls.
            </p>
          </div>
        )}
      </Modal>

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
                    {selectedLenderSignals.map((signal, idx) => (
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

                {selectedLender?.hard_filter_details?.lender_terms && (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <h4 className="font-semibold text-gray-900 mb-2">Lender Commercial Terms</h4>
                    <div className="grid grid-cols-2 gap-3 text-sm text-gray-700">
                      <div>
                        <span className="text-gray-500">Interest Range:</span>{' '}
                        <span className="font-medium">
                          {selectedLender.hard_filter_details.lender_terms.interest_rate_range || 'N/A'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Processing Fee:</span>{' '}
                        <span className="font-medium">
                          {selectedLender.hard_filter_details.lender_terms.processing_fee_pct !== null &&
                          selectedLender.hard_filter_details.lender_terms.processing_fee_pct !== undefined
                            ? `${selectedLender.hard_filter_details.lender_terms.processing_fee_pct}%`
                            : 'N/A'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Tenure:</span>{' '}
                        <span className="font-medium">
                          {selectedLender.hard_filter_details.lender_terms.tenor_min_months || 'N/A'} -{' '}
                          {selectedLender.hard_filter_details.lender_terms.tenor_max_months || 'N/A'} months
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Expected TAT:</span>{' '}
                        <span className="font-medium">
                          {selectedLender.hard_filter_details.lender_terms.expected_tat_days
                            ? `${selectedLender.hard_filter_details.lender_terms.expected_tat_days} days`
                            : 'N/A'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
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
