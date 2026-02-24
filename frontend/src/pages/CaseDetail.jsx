import React, { useEffect, useMemo, useState } from 'react';
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
  getCaseDocumentPreview,
  createCaseDocumentsShareLink,
  updateCase,
  uploadDocuments,
  getCaseStatus,
  triggerCasePipeline,
  getDocumentChecklist,
  getExtractedFields,
  getFeatureVector,
  getEligibilityResults,
  getEligibilityExplanation,
  runScoring,
  generateReport,
  getReportPdf,
  getCaseReport,
  getWhatsAppSummary,
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

const formatInThousands = (rawValue) => {
  if (rawValue === null || rawValue === undefined || Number.isNaN(Number(rawValue))) {
    return 'N/A';
  }
  return `₹${(Number(rawValue) / 1000).toLocaleString('en-IN', {
    maximumFractionDigits: 2,
  })}K`;
};

const normalizeEmailText = (value) => {
  if (!value) return '';
  return String(value)
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
};

const normalizeToken = (value) => String(value || '').trim().toLowerCase();

const PRODUCT_NAME_OPTIONS = [
  'BL',
  'STBL',
  'HTBL',
  'MTBL',
  'SBL',
  'PL',
  'HL',
  'LAP',
  'OD',
  'CC',
  'Digital',
  'Direct',
];

const inferMimeFromFilename = (filename = '') => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.pdf')) return 'application/pdf';
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.tiff') || lower.endsWith('.tif')) return 'image/tiff';
  return 'application/octet-stream';
};

const extractBlobErrorMessage = async (error, fallback) => {
  const responseData = error?.response?.data;
  if (!responseData) return fallback;
  if (typeof responseData?.detail === 'string') return responseData.detail;
  if (responseData instanceof Blob) {
    try {
      const text = await responseData.text();
      const parsed = JSON.parse(text);
      return parsed?.detail || fallback;
    } catch {
      return fallback;
    }
  }
  return fallback;
};

const extractApiErrorMessage = (error, fallback = 'Request failed') => {
  const payload = error?.response?.data;
  if (!payload) {
    if (typeof error?.message === 'string' && error.message.trim()) {
      return error.message;
    }
    return fallback;
  }
  if (typeof payload === 'string') return payload.slice(0, 300);
  if (typeof payload?.detail === 'string') return payload.detail;
  if (typeof payload?.message === 'string') return payload.message;
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message;
  }
  return fallback;
};

const toFiniteNumber = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : null;
};

const isRetryablePipelineError = (error) => {
  const statusCode = error?.response?.status;
  if (!statusCode) return true;
  return [408, 409, 429, 500, 502, 503, 504].includes(statusCode);
};

const waitMs = (ms) => new Promise((resolve) => {
  window.setTimeout(resolve, ms);
});

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
  const [lenderNameInput, setLenderNameInput] = useState('');
  const [productNameInput, setProductNameInput] = useState('');
  const [rmEmail, setRmEmail] = useState('');
  const [reuploadFiles, setReuploadFiles] = useState([]);
  const [documentPreview, setDocumentPreview] = useState(null);
  const [pipelineMetrics, setPipelineMetrics] = useState(null);
  const [pipelineQueueStatus, setPipelineQueueStatus] = useState(null);
  const [shareLinkInfo, setShareLinkInfo] = useState(null);

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

  const { data: extractedFieldsData } = useQuery({
    queryKey: ['extracted-fields', caseId],
    queryFn: () => getExtractedFields(caseId),
    enabled: activeTab === 'profile',
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
    refetchInterval: activeTab === 'report' ? 10000 : false,
  });

  const { data: whatsappSummaryData } = useQuery({
    queryKey: ['report-whatsapp', caseId],
    queryFn: () => getWhatsAppSummary(caseId),
    enabled: activeTab === 'report' && !!caseId,
    retry: 1,
    refetchInterval: activeTab === 'report' ? 10000 : false,
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

  const createShareLinkMutation = useMutation({
    mutationFn: (payload) => createCaseDocumentsShareLink(caseId, payload),
    onSuccess: (response) => {
      setShareLinkInfo(response?.data || null);
    },
    onError: (error) => {
      toast.error(error?.response?.data?.detail || 'Failed to generate secure document link');
    },
  });

  const previewDocumentMutation = useMutation({
    mutationFn: (doc) => getCaseDocumentPreview(caseId, doc.id),
    onSuccess: (response, doc) => {
      if (documentPreview?.url) {
        window.URL.revokeObjectURL(documentPreview.url);
      }
      const blob = response.data instanceof Blob
        ? response.data
        : new Blob([response.data], { type: inferMimeFromFilename(doc?.original_filename) });
      const url = window.URL.createObjectURL(blob);
      setDocumentPreview({
        id: doc.id,
        filename: doc.original_filename || 'document',
        url,
        mimeType: blob.type || inferMimeFromFilename(doc?.original_filename),
      });
    },
    onError: async (error) => {
      const message = await extractBlobErrorMessage(error, 'Unable to preview this document');
      toast.error(message);
    },
  });

  const caseInfo = caseData?.data;
  const documents = Array.isArray(documentsData?.data) ? documentsData.data : [];
  const sortedDocuments = useMemo(() => {
    const known = [];
    const unknown = [];
    documents.forEach((doc) => {
      const docType = normalizeToken(doc?.doc_type);
      if (!docType || docType === 'unknown') {
        unknown.push(doc);
      } else {
        known.push(doc);
      }
    });
    return [...known, ...unknown];
  }, [documents]);
  const checklist = checklistData?.data || {};
  const features = featuresData?.data || {};
  const eligibility = eligibilityData?.data || {};
  const eligibilityExplain = eligibilityExplainData?.data || null;
  const caseReport = caseReportData?.data || null;
  const whatsappSummary = typeof whatsappSummaryData?.data === 'string' ? whatsappSummaryData.data : '';
  const allEligibilityResults = Array.isArray(eligibility?.results)
    ? eligibility.results
    : [];
  const matchingEligibilityResults = allEligibilityResults
    .filter((result) => result.hard_filter_status === 'pass');
  const rejectedEligibilityResults = allEligibilityResults
    .filter((result) => result.hard_filter_status === 'fail');
  const extractedFields = Array.isArray(extractedFieldsData?.data) ? extractedFieldsData.data : [];
  const extractedFieldMap = useMemo(() => {
    const map = new Map();
    extractedFields.forEach((field) => {
      if (!field?.field_name || map.has(field.field_name)) return;
      map.set(field.field_name, field.field_value);
    });
    return map;
  }, [extractedFields]);
  const additionalApplicants = useMemo(() => {
    const primaryPan = String(features?.pan_number || '').trim().toUpperCase();
    const primaryAadhaar = String(features?.aadhaar_number || '').replace(/\s+/g, '');
    const primaryName = String(features?.full_name || '').trim().toLowerCase();

    const panValues = extractedFields
      .filter((field) => field.field_name === 'pan_number' && field.field_value)
      .map((field) => String(field.field_value).trim().toUpperCase());
    const aadhaarValues = extractedFields
      .filter((field) => field.field_name === 'aadhaar_number' && field.field_value)
      .map((field) => String(field.field_value).replace(/\s+/g, ''));
    const nameValues = extractedFields
      .filter((field) => field.field_name === 'full_name' && field.field_value)
      .map((field) => String(field.field_value).trim());
    const dobValues = extractedFields
      .filter((field) => field.field_name === 'dob' && field.field_value)
      .map((field) => String(field.field_value).trim());
    const applicantMap = new Map();

    const ensureApplicant = (key) => {
      if (!applicantMap.has(key)) {
        applicantMap.set(key, {
          full_name: '',
          pan_number: null,
          aadhaar_number: null,
          dob: null,
        });
      }
      return applicantMap.get(key);
    };

    panValues.forEach((pan) => {
      if (!pan || (primaryPan && pan === primaryPan)) return;
      const applicant = ensureApplicant(`pan:${pan}`);
      applicant.pan_number = pan;
    });

    aadhaarValues.forEach((aadhaar) => {
      if (!aadhaar || (primaryAadhaar && aadhaar === primaryAadhaar)) return;
      const existing = Array.from(applicantMap.values()).find((item) => !item.aadhaar_number);
      if (existing) {
        existing.aadhaar_number = aadhaar;
      } else {
        const applicant = ensureApplicant(`aadhaar:${aadhaar}`);
        applicant.aadhaar_number = aadhaar;
      }
    });

    const validNames = nameValues
      .map((name) => name.trim())
      .filter((name) => name.length >= 3)
      .filter((name) => !/\d{4,}/.test(name))
      .filter((name) => name.toLowerCase() !== primaryName);
    validNames.forEach((name) => {
      const existing = Array.from(applicantMap.values()).find((item) => !item.full_name);
      if (existing) {
        existing.full_name = name;
      }
    });

    dobValues.forEach((dob) => {
      const existing = Array.from(applicantMap.values()).find((item) => !item.dob);
      if (existing) {
        existing.dob = dob;
      }
    });

    return Array.from(applicantMap.values())
      .filter((item) => item.pan_number || item.aadhaar_number)
      .map((item) => ({
        full_name: item.full_name || 'Co-applicant',
        pan_number: item.pan_number,
        aadhaar_number: item.aadhaar_number,
        dob: item.dob,
      }))
      .slice(0, 4);
  }, [extractedFields, features?.aadhaar_number, features?.full_name, features?.pan_number]);
  const annualTurnoverLakhs = (
    toFiniteNumber(features?.annual_turnover)
    ?? toFiniteNumber(extractedFieldMap.get('annual_turnover'))
  );
  const monthlyTurnoverAmount = (
    toFiniteNumber(features?.monthly_turnover)
    ?? toFiniteNumber(features?.monthly_credit_avg)
    ?? toFiniteNumber(extractedFieldMap.get('monthly_turnover'))
    ?? toFiniteNumber(extractedFieldMap.get('monthly_credit_avg'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_credit_transactions_amount'))
  );
  const avgMonthlyBalance = (
    toFiniteNumber(features?.avg_monthly_balance)
    ?? toFiniteNumber(extractedFieldMap.get('avg_monthly_balance'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_custom_average_balance'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_average_balance'))
  );
  const monthlyCreditAvg = (
    toFiniteNumber(features?.monthly_credit_avg)
    ?? toFiniteNumber(extractedFieldMap.get('monthly_credit_avg'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_credit_transactions_amount'))
  );
  const monthlyEmiOutflow = (
    toFiniteNumber(features?.emi_outflow_monthly)
    ?? toFiniteNumber(extractedFieldMap.get('emi_outflow_monthly'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_total_emi_amount'))
  );
  const bounceCountValue = (
    toFiniteNumber(features?.bounce_count_12m)
    ?? toFiniteNumber(extractedFieldMap.get('bounce_count_12m'))
    ?? toFiniteNumber(extractedFieldMap.get('credilo_no_of_emi_bounce'))
  );
  const bankAnalyzerSummaryRows = useMemo(() => {
    const rows = [
      ['Source', extractedFieldMap.get('bank_detected')],
      ['Statements Parsed', extractedFieldMap.get('credilo_statement_count') || extractedFieldMap.get('statement_period_months')],
      ['Transactions', extractedFieldMap.get('credilo_total_transactions') || extractedFieldMap.get('transaction_count')],
      ['Period Start', extractedFieldMap.get('credilo_period_start')],
      ['Period End', extractedFieldMap.get('credilo_period_end')],
      ['Credit Amount', extractedFieldMap.get('credilo_credit_transactions_amount') || extractedFieldMap.get('total_credits_12m')],
      ['Debit Amount', extractedFieldMap.get('credilo_debit_transactions_amount') || extractedFieldMap.get('total_debits_12m')],
      ['EMI Count', extractedFieldMap.get('credilo_no_of_emi')],
      ['EMI Bounce Count', extractedFieldMap.get('credilo_no_of_emi_bounce')],
    ];
    return rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '');
  }, [extractedFieldMap]);
  const gstData = caseInfo?.gst_data && typeof caseInfo.gst_data === 'object' ? caseInfo.gst_data : {};
  const gstRawResponse = gstData?.raw_response && typeof gstData.raw_response === 'object'
    ? gstData.raw_response
    : {};
  const gstStatus = gstData?.status || gstRawResponse?.sts || 'N/A';
  const gstTurnover = gstData?.annual_turnover || gstRawResponse?.aggr_turn_over || null;
  const gstFilingHistory = useMemo(() => {
    const direct = Array.isArray(gstData?.filing_history) ? gstData.filing_history : [];
    if (direct.length > 0) return direct.slice(0, 5);
    const returns = gstRawResponse?.returns;
    if (Array.isArray(returns)) return returns.slice(0, 5);
    return [];
  }, [gstData?.filing_history, gstRawResponse?.returns]);
  const totalOutstandingValue = toFiniteNumber(
    extractedFieldMap.get('total_current_outstanding')
      || extractedFieldMap.get('cibil_total_current_outstanding')
  );
  const dpdHistory = extractedFieldMap.get('dpd_history') || extractedFieldMap.get('cibil_dpd_history') || null;
  const scoreTrend = extractedFieldMap.get('score_trend') || extractedFieldMap.get('cibil_score_trend') || null;
  const activeLoanDetails = extractedFieldMap.get('active_loan_details') || extractedFieldMap.get('cibil_active_loan_details') || null;
  const creditStorySummary = useMemo(() => {
    const pieces = [];
    if (features?.cibil_score) {
      if (features.cibil_score >= 750) {
        pieces.push('Excellent score band with low default probability.');
      } else if (features.cibil_score >= 680) {
        pieces.push('Healthy score band, generally acceptable to most BL lenders.');
      } else {
        pieces.push('Sub-prime score band; file quality and banking profile become critical.');
      }
    }
    if ((features?.overdue_count || 0) > 0) {
      pieces.push(`${features.overdue_count} overdue account(s) detected and needs justification.`);
    } else {
      pieces.push('No overdue accounts detected in the parsed bureau summary.');
    }
    if ((features?.enquiry_count_6m || 0) > 4) {
      pieces.push('High recent enquiry velocity may impact approval confidence.');
    } else if (features?.enquiry_count_6m !== null && features?.enquiry_count_6m !== undefined) {
      pieces.push('Recent enquiry velocity is within acceptable range.');
    }
    if (totalOutstandingValue) {
      pieces.push(`Total current outstanding stands at ${formatCurrency(totalOutstandingValue)}.`);
    }
    return pieces.join(' ');
  }, [
    features?.cibil_score,
    features?.overdue_count,
    features?.enquiry_count_6m,
    totalOutstandingValue,
  ]);
  const selectedEmailLender = allEligibilityResults.find((item) => (
    normalizeToken(item.lender_name) === normalizeToken(lenderNameInput)
      && normalizeToken(item.product_name) === normalizeToken(productNameInput)
  )) || allEligibilityResults.find(
    (item) => normalizeToken(item.lender_name) === normalizeToken(lenderNameInput)
  ) || null;
  const lenderNameSuggestions = useMemo(
    () => Array.from(new Set(allEligibilityResults.map((item) => item.lender_name).filter(Boolean))),
    [allEligibilityResults]
  );
  const productNameSuggestions = useMemo(
    () => Array.from(new Set([
      ...PRODUCT_NAME_OPTIONS,
      ...allEligibilityResults.map((item) => item.product_name).filter(Boolean),
    ])),
    [allEligibilityResults]
  );
  const selectedLenderSignals = buildMatchedSignalsForModal(selectedLender, features);
  const docFramework =
    DOCUMENTATION_FRAMEWORK_2026[selectedProgram] || DOCUMENTATION_FRAMEWORK_2026.banking;
  const firstMatchTicket = matchingEligibilityResults[0]?.expected_ticket_max;

  const emiLoanAmountRupees = lakhToRupees(emiLoanAmountLakhs);
  const waitForCasePipelineCompletion = async (targetCaseId, opts = {}) => {
    const maxAttempts = Number.isFinite(opts.maxAttempts) ? opts.maxAttempts : 360; // ~18 minutes
    const pollIntervalMs = Number.isFinite(opts.pollIntervalMs) ? opts.pollIntervalMs : 3000;
    let latestStatus = null;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await getCaseStatus(targetCaseId);
        latestStatus = response?.data;
        const jobs = latestStatus?.document_jobs || null;
        if (typeof opts.onTick === 'function') {
          opts.onTick(jobs);
        }

        const caseStatus = String(latestStatus?.status || '').toLowerCase();
        if (caseStatus === 'report_generated' || caseStatus === 'submitted') {
          return latestStatus;
        }
        if (caseStatus === 'failed') {
          throw new Error('Pipeline failed in background processing');
        }
      } catch (error) {
        // Keep polling across intermittent network/redeploy blips.
        if (attempt === maxAttempts - 1) {
          throw error;
        }
      }
      await waitMs(pollIntervalMs);
    }

    throw new Error('Pipeline is taking longer than expected. Please check status again in a minute.');
  };

  const runFullPipelineMutation = useMutation({
    mutationFn: async () => {
      setPipelineQueueStatus(null);
      const startedAt = performance.now();
      const triggerWithRetry = async (payload = {}, attempts = 3) => {
        let lastError = null;
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
          try {
            return await triggerCasePipeline(caseId, payload);
          } catch (error) {
            lastError = error;
            if (attempt === attempts || !isRetryablePipelineError(error)) {
              throw error;
            }
            await waitMs(1000 * attempt);
          }
        }
        throw lastError || new Error('Unable to trigger pipeline');
      };

      let triggerResponse;
      try {
        triggerResponse = await triggerWithRetry({}, 3);
      } catch (error) {
        // If trigger call itself fails due transient network/proxy issues,
        // still check whether pipeline is already running and continue polling.
        const statusSnapshot = await getCaseStatus(caseId).catch(() => null);
        const statusValue = String(statusSnapshot?.data?.status || '').toLowerCase();
        const queueInProgress = Boolean(statusSnapshot?.data?.document_jobs?.in_progress);
        if (statusValue === 'processing' || queueInProgress) {
          const finalState = await waitForCasePipelineCompletion(caseId, {
            onTick: (jobs) => setPipelineQueueStatus(jobs),
          });
          return {
            total: Number((performance.now() - startedAt).toFixed(0)),
            mode: 'async_queue',
            final_status: finalState?.status,
            queue_snapshot: finalState?.document_jobs || null,
          };
        }
        throw error;
      }

      let triggerStatus = triggerResponse?.data?.status;

      if (triggerStatus === 'already_complete') {
        return {
          total: Number((performance.now() - startedAt).toFixed(0)),
          mode: 'already_complete',
        };
      }

      if (triggerStatus === 'waiting_for_documents') {
        await waitForDocumentQueue(caseId, {
          maxAttempts: 240,
          onTick: (jobs) => setPipelineQueueStatus(jobs),
        });
        triggerResponse = await triggerWithRetry({ force: true }, 3);
        triggerStatus = triggerResponse?.data?.status;
      }

      const finalState = await waitForCasePipelineCompletion(caseId, {
        onTick: (jobs) => setPipelineQueueStatus(jobs),
      });

      return {
        total: Number((performance.now() - startedAt).toFixed(0)),
        mode: 'async_queue',
        final_status: finalState?.status,
        queue_snapshot: finalState?.document_jobs || null,
      };
    },
    onSuccess: (result) => {
      setPipelineMetrics(result);
      setPipelineQueueStatus(null);
      toast.success(
        result?.mode === 'already_complete'
          ? 'Report is already generated for this case.'
          : `Pipeline completed in ${result?.total || 0}ms`
      );
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-documents', caseId] });
      queryClient.invalidateQueries({ queryKey: ['features', caseId] });
      queryClient.invalidateQueries({ queryKey: ['eligibility', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-report', caseId] });
      queryClient.invalidateQueries({ queryKey: ['report-whatsapp', caseId] });
    },
    onError: (error) => {
      const detail = extractApiErrorMessage(error, 'Full processing failed');
      toast.error(`Pipeline failed: ${detail}`);
    },
    onSettled: () => {
      setPipelineQueueStatus(null);
    },
  });

  const waitForDocumentQueue = async (targetCaseId, opts = {}) => {
    const maxAttempts = Number.isFinite(opts.maxAttempts) ? opts.maxAttempts : 180; // ~6 minutes
    let latestStatus = null;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await getCaseStatus(targetCaseId);
        latestStatus = response?.data;
        const jobs = latestStatus?.document_jobs;
        if (typeof opts.onTick === 'function') {
          opts.onTick(jobs || null);
        }
        if (!jobs || jobs.total === 0 || jobs.in_progress === false) {
          return latestStatus;
        }
      } catch (_) {
        // Continue polling across transient failures.
      }
      await waitMs(2000);
    }
    return latestStatus;
  };

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

  const reuploadDocumentsMutation = useMutation({
    mutationFn: async (filesToUpload) => {
      const formData = new FormData();
      filesToUpload.forEach((file) => {
        formData.append('files', file);
      });
      await uploadDocuments(caseId, formData, { timeout: 600000 });

      let triggerResponse;
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        try {
          triggerResponse = await triggerCasePipeline(caseId, { force: true });
          break;
        } catch (error) {
          if (attempt === 3 || !isRetryablePipelineError(error)) {
            throw error;
          }
          await waitMs(1200 * attempt);
        }
      }

      if (triggerResponse?.data?.status === 'waiting_for_documents') {
        await waitForDocumentQueue(caseId, {
          maxAttempts: 240,
          onTick: (jobs) => setPipelineQueueStatus(jobs),
        });
        await triggerCasePipeline(caseId, { force: true });
      }

      const finalState = await waitForCasePipelineCompletion(caseId, {
        maxAttempts: 420,
        pollIntervalMs: 3000,
        onTick: (jobs) => setPipelineQueueStatus(jobs),
      });

      const failedJobs = Number(finalState?.document_jobs?.failed || 0);
      if (failedJobs > 0) {
        toast(`Re-processing completed with ${failedJobs} failed file(s). Re-upload unreadable files for best output.`, {
          icon: '⚠️',
        });
      }
    },
    onSuccess: () => {
      setPipelineQueueStatus(null);
      toast.success('Documents uploaded. Background pipeline completed.');
      setReuploadFiles([]);
      queryClient.invalidateQueries({ queryKey: ['case', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-documents', caseId] });
      queryClient.invalidateQueries({ queryKey: ['checklist', caseId] });
      queryClient.invalidateQueries({ queryKey: ['features', caseId] });
      queryClient.invalidateQueries({ queryKey: ['eligibility', caseId] });
      queryClient.invalidateQueries({ queryKey: ['case-report', caseId] });
      queryClient.invalidateQueries({ queryKey: ['report-whatsapp', caseId] });
    },
    onError: (error) => {
      setPipelineQueueStatus(null);
      const detail = extractApiErrorMessage(error, 'Failed to upload and reprocess documents');
      toast.error(detail);
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
    if (!allEligibilityResults.length) return;
    if (!lenderNameInput) {
      const first = allEligibilityResults[0];
      setLenderNameInput(first.lender_name || '');
      setProductNameInput(first.product_name || '');
    }
  }, [allEligibilityResults, lenderNameInput]);

  useEffect(() => () => {
    if (documentPreview?.url) {
      window.URL.revokeObjectURL(documentPreview.url);
    }
  }, [documentPreview?.url]);

  const tabs = [
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'checklist', label: 'Checklist', icon: CheckSquare },
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'eligibility', label: 'Eligibility', icon: TrendingUp },
    { id: 'report', label: 'Report', icon: FileDown },
  ];

  const ensureShareLink = async () => {
    const currentUrl = shareLinkInfo?.download_url;
    const currentExpiry = shareLinkInfo?.expires_at ? Date.parse(shareLinkInfo.expires_at) : null;
    const hasValidCurrent =
      typeof currentUrl === 'string'
      && currentUrl.length > 0
      && Number.isFinite(currentExpiry)
      && currentExpiry > Date.now() + 60 * 1000;

    if (hasValidCurrent) {
      return currentUrl;
    }

    const response = await createShareLinkMutation.mutateAsync({
      expires_in_hours: 72,
      max_downloads: 25,
    });
    const generatedUrl = response?.data?.download_url;
    if (!generatedUrl) {
      throw new Error('Share link missing from API response');
    }
    return generatedUrl;
  };

  const openMailtoDraft = async () => {
    const lenderName = lenderNameInput.trim();
    const productName = productNameInput.trim() || selectedEmailLender?.product_name || 'Business Loan';

    if (!lenderName) {
      toast.error('Enter lender name');
      return;
    }
    if (!rmEmail) {
      toast.error('Enter lender RM email');
      return;
    }

    let shareUrl = '';
    try {
      shareUrl = await ensureShareLink();
    } catch (error) {
      toast.error('Unable to generate secure document link');
      return;
    }

    const loggedInUser = getUser();
    const senderName =
      normalizeEmailText(loggedInUser?.full_name) ||
      (loggedInUser?.email ? String(loggedInUser.email).split('@')[0] : 'DSA Team');
    const resolvedTicket =
      selectedEmailLender?.expected_ticket_max ??
      firstMatchTicket ??
      caseInfo?.loan_amount_requested ??
      null;
    const ticketText = formatLakhAmount(resolvedTicket);
    const strengthsList = (caseReport?.strengths || [])
      .map((item) => normalizeEmailText(item))
      .filter(Boolean)
      .slice(0, 4);
    const strengths =
      strengthsList.length > 0
        ? strengthsList.map((item) => `- ${item}`).join('\n')
        : '- Clean banking profile';
    const documentCount = documents.length;
    const documentPackageLine = `${caseId}_documents.zip (${documentCount} file${documentCount === 1 ? '' : 's'})`;

    const subject = `[Credilo] ${productName} Case Submission - ${caseInfo?.borrower_name || caseId} (${caseId})`;
    const body = [
      `Hi ${lenderName} team,`,
      '',
      'Sharing a lender-ready case summary from Credilo.',
      '',
      'Case Snapshot:',
      `- Case ID: ${caseId}`,
      `- Company: ${caseInfo?.borrower_name || 'N/A'}`,
      `- Entity: ${caseInfo?.entity_type || 'N/A'}`,
      `- CIBIL: ${features?.cibil_score || caseInfo?.cibil_score_manual || 'N/A'}`,
      `- Business Vintage: ${features?.business_vintage_years || caseInfo?.business_vintage_years || 'N/A'} years`,
      `- Requested Loan: ${formatLakhAmount(caseInfo?.loan_amount_requested)}`,
      `- Indicative Eligible Ticket: ${ticketText}`,
      `- Pincode: ${features?.pincode || caseInfo?.pincode || 'N/A'}`,
      '',
      'Top Strength Pointers:',
      strengths,
      '',
      `Document Package: ${documentPackageLine}`,
      `Secure Document Link: ${shareUrl}`,
      'Please review using this secure link (temporary, controlled access).',
      '',
      'Please review and share eligibility feedback with next steps.',
      '',
      'Regards,',
      senderName,
    ].join('\n');

    const mailto = `mailto:${encodeURIComponent(rmEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.open(mailto, '_self');
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
              {caseInfo?.borrower_name || 'Unnamed Company'}
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
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 mb-4">
            <div>
              <h2 className="text-xl font-semibold">Uploaded Documents</h2>
              <p className="text-xs text-gray-500 mt-1">
                Re-upload ZIP or individual files to refresh classification and pipeline outputs.
              </p>
            </div>
            <div className="flex flex-col md:flex-row gap-2 md:items-center">
              <input
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.zip"
                onChange={(event) => {
                  const picked = Array.from(event.target.files || []);
                  setReuploadFiles(picked);
                }}
                className="text-sm"
              />
              <Button
                onClick={() => {
                  if (!reuploadFiles.length) {
                    toast.error('Select at least one file to upload');
                    return;
                  }
                  reuploadDocumentsMutation.mutate(reuploadFiles);
                }}
                disabled={reuploadDocumentsMutation.isPending || reuploadFiles.length === 0}
              >
                {reuploadDocumentsMutation.isPending ? 'Uploading & Reprocessing...' : 'Re-upload Documents'}
              </Button>
            </div>
          </div>
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
                  {sortedDocuments.map((doc) => (
                    <tr key={doc.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        <button
                          type="button"
                          className="text-primary hover:underline disabled:text-gray-400"
                          onClick={() => previewDocumentMutation.mutate(doc)}
                          disabled={previewDocumentMutation.isPending}
                          title="Click to preview"
                        >
                          {doc.original_filename}
                        </button>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Badge variant={normalizeToken(doc.doc_type) === 'unknown' ? 'danger' : 'info'}>
                          {doc.doc_type || 'Unknown'}
                        </Badge>
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
          {documents.length > 0 && (
            <p className="text-xs text-gray-500 mt-3">
              Click any filename to preview the uploaded document.
            </p>
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
                Loan Checklist
              </h3>
              <p className="text-xs text-gray-600 mb-3">
                Guidance checklist to reduce back-and-forth with companies and improve first-pass lender submissions.
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
                {runFullPipelineMutation.isPending
                  ? (pipelineQueueStatus?.in_progress
                    ? `Analyzing Documents (${pipelineQueueStatus.completion_pct || 0}%)`
                    : 'Running Background Pipeline...')
                  : 'Run Full Pipeline'}
              </Button>
              <p className="text-xs text-gray-500 mt-2">
                Triggers extraction, eligibility scoring, and report generation in background.
              </p>
              {runFullPipelineMutation.isPending && pipelineQueueStatus?.in_progress && (
                <p className="text-xs text-blue-700 mt-1">
                  Queue status: queued {pipelineQueueStatus.queued || 0}, processing {pipelineQueueStatus.processing || 0},
                  completed {pipelineQueueStatus.completed || 0}, failed {pipelineQueueStatus.failed || 0}
                </p>
              )}
              {pipelineMetrics?.total && (
                <p className="text-xs text-blue-700 mt-2">
                  Last background run completed in {pipelineMetrics.total}ms.
                </p>
              )}
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'profile' && (
        <div className="space-y-5">
          <Card className="transition-all duration-300 hover:shadow-lg border border-slate-200">
            <h2 className="text-xl font-semibold mb-4 text-slate-900">Identity Profile</h2>
            {Object.keys(features).length === 0 ? (
              <p className="text-gray-500 text-center py-6">
                No features extracted yet. Upload documents and run extraction.
              </p>
            ) : (
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                    <div className="text-slate-500 text-xs mb-1">Full Name</div>
                    <div className="font-semibold text-slate-900">{features.full_name || 'N/A'}</div>
                  </div>
                  <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                    <div className="text-slate-500 text-xs mb-1">PAN Number</div>
                    <div className="font-semibold text-slate-900">{features.pan_number || 'N/A'}</div>
                  </div>
                  <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                    <div className="text-slate-500 text-xs mb-1">Aadhaar Number</div>
                    <div className="font-semibold text-slate-900">
                      {features.aadhaar_number ? `****${features.aadhaar_number.slice(-4)}` : 'N/A'}
                    </div>
                  </div>
                  <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                    <div className="text-slate-500 text-xs mb-1">Date of Birth</div>
                    <div className="font-semibold text-slate-900">{features.dob || 'N/A'}</div>
                  </div>
                </div>
                {additionalApplicants.length > 0 && (
                  <div className="pt-2">
                    <h4 className="text-sm font-semibold text-slate-900 mb-2">
                      Additional Applicant Details ({additionalApplicants.length})
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {additionalApplicants.map((applicant, idx) => (
                        <div key={`co-app-${idx}`} className="rounded-md border border-slate-200 p-3 bg-white">
                          <div className="text-xs font-semibold text-slate-700 mb-2">Co-applicant {idx + 1}</div>
                          <div className="space-y-1 text-sm">
                            <div>Full Name: <span className="font-medium">{applicant.full_name || 'N/A'}</span></div>
                            <div>PAN: <span className="font-medium">{applicant.pan_number || 'N/A'}</span></div>
                            <div>Aadhaar: <span className="font-medium">{applicant.aadhaar_number ? `****${applicant.aadhaar_number.slice(-4)}` : 'N/A'}</span></div>
                            <div>DOB: <span className="font-medium">{applicant.dob || 'N/A'}</span></div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card className="transition-all duration-300 hover:shadow-lg border border-slate-200">
            <h2 className="text-xl font-semibold mb-4 text-slate-900">Business Snapshot</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Company Name</div>
                <div className="font-semibold">{caseInfo?.borrower_name || features.full_name || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Entity Type</div>
                <div className="font-semibold capitalize">{features.entity_type || caseInfo?.entity_type || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Business Vintage</div>
                <div className="font-semibold">
                  {features.business_vintage_years || caseInfo?.business_vintage_years
                    ? `${features.business_vintage_years || caseInfo?.business_vintage_years} years`
                    : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">GSTIN</div>
                <div className="font-semibold">{features.gstin || caseInfo?.gstin || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">GST Status</div>
                <div className="font-semibold">{gstStatus || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Pincode</div>
                <div className="font-semibold">{features.pincode || caseInfo?.pincode || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3 md:col-span-2">
                <div className="text-slate-500 text-xs mb-1">Business Address</div>
                <div className="font-semibold">{caseInfo?.business_address || gstData?.address || 'N/A'}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">GST Turnover (API)</div>
                <div className="font-semibold">{gstTurnover ? `₹${Number(gstTurnover).toLocaleString('en-IN')}` : 'N/A'}</div>
              </div>
            </div>
            {gstFilingHistory.length > 0 && (
              <div className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3">
                <h4 className="text-sm font-semibold text-blue-900 mb-1">Recent GST Filing History</h4>
                <ul className="text-xs text-blue-900 space-y-1">
                  {gstFilingHistory.slice(0, 4).map((item, idx) => (
                    <li key={`gst-history-${idx}`}>
                      • {typeof item === 'string' ? item : JSON.stringify(item)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card className="transition-all duration-300 hover:shadow-lg border border-slate-200">
            <h2 className="text-xl font-semibold mb-4 text-slate-900">Credit Health</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">CIBIL Score</div>
                <div className={`text-2xl font-bold ${
                  features.cibil_score >= 750 ? 'text-green-600' :
                    features.cibil_score >= 650 ? 'text-yellow-600' :
                      features.cibil_score ? 'text-red-600' : 'text-gray-400'
                }`}>
                  {features.cibil_score || caseInfo?.cibil_score_manual || 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Active Loans</div>
                <div className="text-lg font-semibold">{features.active_loan_count || 0}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Overdue Accounts</div>
                <div className={`text-lg font-semibold ${(features.overdue_count || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {features.overdue_count !== null && features.overdue_count !== undefined ? features.overdue_count : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Enquiries (6M)</div>
                <div className="text-lg font-semibold">{features.enquiry_count_6m ?? 'N/A'}</div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="rounded-md border border-slate-200 p-3 bg-white">
                <div className="text-slate-500 text-xs mb-1">Total Outstanding</div>
                <div className="font-semibold">{totalOutstandingValue ? formatCurrency(totalOutstandingValue) : 'N/A'}</div>
              </div>
              <div className="rounded-md border border-slate-200 p-3 bg-white">
                <div className="text-slate-500 text-xs mb-1">Score Trend</div>
                <div className="font-semibold">{scoreTrend || 'N/A'}</div>
              </div>
              <div className="rounded-md border border-slate-200 p-3 bg-white">
                <div className="text-slate-500 text-xs mb-1">DPD History</div>
                <div className="font-semibold">{dpdHistory || 'N/A'}</div>
              </div>
              <div className="rounded-md border border-slate-200 p-3 bg-white">
                <div className="text-slate-500 text-xs mb-1">Active Loan Details</div>
                <div className="font-semibold">{activeLoanDetails || 'N/A'}</div>
              </div>
            </div>
            <div className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3">
              <h4 className="text-sm font-semibold text-blue-900 mb-1">Credit Story</h4>
              <p className="text-sm text-blue-900">
                {creditStorySummary || 'Credit narrative will be generated after CIBIL + banking extraction completes.'}
              </p>
            </div>
            <div className="pt-4 mt-4 border-t border-slate-100">
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
            </div>
          </Card>

          <Card className="transition-all duration-300 hover:shadow-lg border border-slate-200">
            <h2 className="text-xl font-semibold mb-4 text-slate-900">Financial Overview</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Annual Turnover</div>
                <div className="font-semibold">
                  {annualTurnoverLakhs ? `₹${Number(annualTurnoverLakhs).toLocaleString('en-IN')} L` : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Monthly Turnover</div>
                <div className="font-semibold">
                  {monthlyTurnoverAmount ? `₹${Number(monthlyTurnoverAmount).toLocaleString('en-IN')}` : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Avg Monthly Balance (K)</div>
                <div className="font-semibold">{formatInThousands(avgMonthlyBalance)}</div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Monthly Credits (Avg)</div>
                <div className="font-semibold">
                  {monthlyCreditAvg ? `₹${Number(monthlyCreditAvg).toLocaleString('en-IN')}` : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">EMI Outflow (Monthly)</div>
                <div className="font-semibold">
                  {monthlyEmiOutflow ? `₹${Number(monthlyEmiOutflow).toLocaleString('en-IN')}` : 'N/A'}
                </div>
              </div>
              <div className="rounded-md bg-slate-50 border border-slate-100 p-3">
                <div className="text-slate-500 text-xs mb-1">Bounce Count (12M)</div>
                <div className={`font-semibold ${(bounceCountValue || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {bounceCountValue !== null && bounceCountValue !== undefined ? bounceCountValue : 'N/A'}
                </div>
              </div>
            </div>
            {bankAnalyzerSummaryRows.length > 0 && (
              <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
                <h4 className="text-sm font-semibold text-slate-900 mb-2">Bank Analyzer Snapshot</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                  {bankAnalyzerSummaryRows.map(([label, value]) => (
                    <div key={`bank-metric-${label}`} className="flex justify-between items-start">
                      <span className="text-gray-600">{label}</span>
                      <span className="font-medium text-right">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-4 pt-4 border-t">
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
          </Card>
        </div>
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
                onClick={() => downloadPdfMutation.mutate()}
                disabled={downloadPdfMutation.isPending}
                variant="success"
                className="flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  {downloadPdfMutation.isPending ? 'Downloading...' : 'Download PDF'}
                </Button>
            </div>
            <p className="text-xs text-blue-700">
              Report summary auto-refreshes every 10 seconds.
            </p>

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

                <div className="p-4 rounded-lg border border-gray-200 bg-white">
                    <h4 className="font-semibold mb-3">Email Collaboration (Lender RM)</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="md:col-span-1">
                        <label className="block text-xs text-gray-600 mb-1">Lender Name</label>
                        <input
                          type="text"
                          list="lender-name-options"
                          value={lenderNameInput}
                          onChange={(e) => setLenderNameInput(e.target.value)}
                          placeholder="e.g., Bajaj / HDFC / Arthmate"
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                        <datalist id="lender-name-options">
                          {lenderNameSuggestions.map((name) => (
                            <option key={`lender-opt-${name}`} value={name} />
                          ))}
                        </datalist>
                      </div>

                      <div className="md:col-span-1">
                        <label className="block text-xs text-gray-600 mb-1">Product Name</label>
                        <input
                          type="text"
                          list="product-name-options"
                          value={productNameInput}
                          onChange={(e) => setProductNameInput(e.target.value)}
                          placeholder="e.g., BL / STBL / HTBL"
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                        <datalist id="product-name-options">
                          {productNameSuggestions.map((product) => (
                            <option key={`product-opt-${product}`} value={product} />
                          ))}
                        </datalist>
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
                      <div className="md:col-span-1 flex items-end gap-2">
                        <Button
                          className="w-full"
                          onClick={() => { void openMailtoDraft(); }}
                          disabled={createShareLinkMutation.isPending}
                        >
                          {createShareLinkMutation.isPending ? 'Creating Link...' : 'Generate Link + Open Draft'}
                        </Button>
                      </div>
                      <div className="md:col-span-1 flex items-end gap-2">
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={async () => {
                            try {
                              const link = await ensureShareLink();
                              await navigator.clipboard.writeText(link);
                              toast.success('Secure link copied');
                            } catch {
                              toast.error('Unable to copy secure link');
                            }
                          }}
                        >
                          Copy Secure Link
                        </Button>
                      </div>
                      <div className="md:col-span-1 flex items-end gap-2">
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={() => { void openMailtoDraft(); }}
                        >
                          Open Draft
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      Large attachments are replaced with a secure temporary download link, so sharing works even above email attachment limits.
                    </p>
                    {shareLinkInfo?.download_url && (
                      <p className="text-xs text-blue-700 mt-2 break-all">
                        Latest secure link: {shareLinkInfo.download_url}
                      </p>
                    )}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      <Modal
        isOpen={!!documentPreview}
        onClose={() => {
          if (documentPreview?.url) {
            window.URL.revokeObjectURL(documentPreview.url);
          }
          setDocumentPreview(null);
        }}
        title={documentPreview ? `Document Preview • ${documentPreview.filename}` : 'Document Preview'}
        size="lg"
      >
        {!documentPreview ? null : (
          <div className="space-y-3">
            {(documentPreview.mimeType || '').startsWith('image/') ? (
              <img
                src={documentPreview.url}
                alt={documentPreview.filename}
                className="max-h-[70vh] w-full object-contain border border-gray-200 rounded-lg"
              />
            ) : (documentPreview.mimeType || inferMimeFromFilename(documentPreview.filename)).includes('pdf') ? (
              <iframe
                src={documentPreview.url}
                title={documentPreview.filename}
                className="w-full h-[70vh] border border-gray-200 rounded-lg"
              />
            ) : (
              <div className="border border-gray-200 rounded-lg p-6 text-sm text-gray-600 bg-gray-50">
                This file type cannot be rendered in preview. Use download to open it locally.
              </div>
            )}
            <div className="flex justify-end">
              <Button
                variant="outline"
                onClick={() => {
                  const link = document.createElement('a');
                  link.href = documentPreview.url;
                  link.setAttribute('download', documentPreview.filename);
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                }}
              >
                Download File
              </Button>
            </div>
          </div>
        )}
      </Modal>

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
