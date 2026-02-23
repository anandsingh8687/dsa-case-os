import apiClient from './client';

// Auth
export const login = (credentials) =>
  apiClient.post('/auth/login', credentials);

export const register = (userData) =>
  apiClient.post('/auth/register', userData);

export const getCurrentUser = () =>
  apiClient.get('/auth/me');

// Cases
export const createCase = (caseData) =>
  apiClient.post('/cases/', caseData);

export const getCases = (params) =>
  apiClient.get('/cases/', {
    params,
    timeout: 15000,
  });

export const getCase = (caseId) =>
  apiClient.get(`/cases/${caseId}`);

export const getCaseDocuments = (caseId) =>
  apiClient.get(`/cases/${caseId}/documents`);

export const getCaseDocumentPreview = (caseId, documentId) =>
  apiClient.get(`/cases/${caseId}/documents/${documentId}/preview`, {
    responseType: 'blob',
  });

export const getCaseDocumentsArchive = (caseId) =>
  apiClient.get(`/cases/${caseId}/documents/archive`, {
    responseType: 'blob',
  });

export const updateCase = (caseId, data) =>
  apiClient.patch(`/cases/${caseId}`, data);

export const deleteCase = (caseId) =>
  apiClient.delete(`/cases/${caseId}`);

export const uploadDocuments = (caseId, formData, config = {}) =>
  apiClient.post(`/cases/${caseId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    ...config,
  });

export const getCaseStatus = (caseId) =>
  apiClient.get(`/cases/${caseId}/status`);

export const getDocumentChecklist = (caseId, programType) =>
  apiClient.get(`/cases/${caseId}/checklist`, {
    params: { program_type: programType },
  });

export const getManualPrompts = (caseId, programType) =>
  apiClient.get(`/cases/${caseId}/manual-prompts`, {
    params: { program_type: programType },
  });

// Documents
export const getOcrText = (docId) =>
  apiClient.get(`/documents/${docId}/ocr-text`);

export const reclassifyDocument = (docId, newType) =>
  apiClient.post(`/documents/${docId}/reclassify`, {
    new_doc_type: newType,
  });

// Extraction
export const runExtraction = (caseId) =>
  apiClient.post(`/extraction/case/${caseId}/extract`, null, {
    timeout: 300000,
  });

export const getExtractedFields = (caseId) =>
  apiClient.get(`/extraction/case/${caseId}/fields`);

export const getFeatureVector = (caseId) =>
  apiClient.get(`/extraction/case/${caseId}/features`);

// Eligibility
export const runScoring = (caseId) =>
  apiClient.post(`/eligibility/case/${caseId}/score`, null, {
    timeout: 180000,
  });

export const getEligibilityResults = (caseId) =>
  apiClient.get(`/eligibility/case/${caseId}/results`);

export const getEligibilityExplanation = (caseId) =>
  apiClient.get(`/eligibility/case/${caseId}/explain`);

// Reports
export const generateReport = (caseId) =>
  apiClient.post(`/reports/case/${caseId}/generate`, null, {
    timeout: 180000,
  });

export const getReportPdf = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/report/pdf`, {
    responseType: 'blob',
  });

export const getCaseReport = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/report`);

export const getWhatsAppSummary = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/report/whatsapp`, {
    responseType: 'text',
  });

export const getNarrativeProfileReport = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/narrative/profile`);

export const getNarrativeEligibilityReport = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/narrative/eligibility`);

export const getNarrativeDocumentReport = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/narrative/documents`);

export const getNarrativeComprehensiveReport = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/narrative/comprehensive`);

// Quick Scan
export const runQuickScan = (data) =>
  apiClient.post('/quick-scan', data);

export const getQuickScan = (scanId) =>
  apiClient.get(`/quick-scan/${scanId}`);

export const getQuickScanCard = (scanId) =>
  apiClient.get(`/quick-scan/${scanId}/card`, { responseType: 'blob' });

export const getQuickScanKnowledgeBaseStats = () =>
  apiClient.get('/quick-scan/knowledge-base/stats');

// Admin
export const getAdminStats = () =>
  apiClient.get('/admin/stats');

export const getAdminUsers = (params) =>
  apiClient.get('/admin/users', { params });

export const getAdminCases = (params) =>
  apiClient.get('/admin/cases', { params });

export const getAdminLogs = (params) =>
  apiClient.get('/admin/logs', { params });

export const getAdminHealth = () =>
  apiClient.get('/admin/health');

export const getAdminLatency = () =>
  apiClient.get('/admin/latency');

export const getAdminUserUsage = (params) =>
  apiClient.get('/admin/user-usage', { params });

export const getAdminActivityFeed = (params) =>
  apiClient.get('/admin/activity-feed', { params });

// Commission
export const getCommissionOverview = () =>
  apiClient.get('/commission/overview');

export const getCommissionRates = () =>
  apiClient.get('/commission/rates');

export const upsertCommissionRate = (payload) =>
  apiClient.post('/commission/rates', payload);

export const deleteCommissionRate = (rateId) =>
  apiClient.delete(`/commission/rates/${rateId}`);

export const calculateCommission = (payload) =>
  apiClient.post('/commission/calculate', payload);

export const upsertCommissionPayout = (payload) =>
  apiClient.post('/commission/payouts', payload);

export const getCommissionPayouts = (params) =>
  apiClient.get('/commission/payouts', { params });

// Leads
export const getLeads = (params) =>
  apiClient.get('/leads', { params });

export const createLead = (payload) =>
  apiClient.post('/leads', payload);

export const updateLead = (leadId, payload) =>
  apiClient.patch(`/leads/${leadId}`, payload);

export const getLeadActivities = (leadId) =>
  apiClient.get(`/leads/${leadId}/activities`);

export const addLeadActivity = (leadId, payload) =>
  apiClient.post(`/leads/${leadId}/activities`, payload);

// Submission Tracker
export const getSubmissions = (params) =>
  apiClient.get('/submissions', { params });

export const getCaseSubmissions = (caseId) =>
  apiClient.get(`/submissions/case/${caseId}`);

export const createCaseSubmission = (caseId, payload) =>
  apiClient.post(`/submissions/case/${caseId}`, payload);

export const updateSubmission = (submissionId, payload) =>
  apiClient.patch(`/submissions/${submissionId}`, payload);

export const addSubmissionQuery = (submissionId, payload) =>
  apiClient.post(`/submissions/${submissionId}/queries`, payload);

export const updateSubmissionQuery = (queryId, payload) =>
  apiClient.patch(`/submissions/queries/${queryId}`, payload);

// Bank Statement Analyzer
export const processBankStatements = (formData, config = {}) =>
  apiClient.post('/bank-statement/process', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: 'blob',
    timeout: 240000,
    ...config,
  });

// Lenders
export const getLenders = () =>
  apiClient.get('/lenders/');

export const getLendersByPincode = (pincode) =>
  apiClient.get(`/lenders/by-pincode/${pincode}`);

// Copilot
export const queryCopilot = (payload) => {
  if (typeof payload === 'string') {
    return apiClient.post('/copilot/query', { query: payload });
  }
  return apiClient.post('/copilot/query', payload);
};
