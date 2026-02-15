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
  apiClient.get('/cases/', { params });

export const getCase = (caseId) =>
  apiClient.get(`/cases/${caseId}`);

export const getCaseDocuments = (caseId) =>
  apiClient.get(`/cases/${caseId}/documents`);

export const updateCase = (caseId, data) =>
  apiClient.patch(`/cases/${caseId}`, data);

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
  apiClient.post(`/extraction/case/${caseId}/extract`);

export const getExtractedFields = (caseId) =>
  apiClient.get(`/extraction/case/${caseId}/fields`);

export const getFeatureVector = (caseId) =>
  apiClient.get(`/extraction/case/${caseId}/features`);

// Eligibility
export const runScoring = (caseId) =>
  apiClient.post(`/eligibility/case/${caseId}/score`);

export const getEligibilityResults = (caseId) =>
  apiClient.get(`/eligibility/case/${caseId}/results`);

export const getEligibilityExplanation = (caseId) =>
  apiClient.get(`/eligibility/case/${caseId}/explain`);

// Reports
export const generateReport = (caseId) =>
  apiClient.post(`/reports/case/${caseId}/generate`);

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

// Bank Statement Analyzer
export const processBankStatements = (formData) =>
  apiClient.post('/bank-statement/process', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: 'blob',
  });

// Lenders
export const getLenders = () =>
  apiClient.get('/lenders/');

export const getLendersByPincode = (pincode) =>
  apiClient.get(`/lenders/by-pincode/${pincode}`);

// Copilot
export const queryCopilot = (query) =>
  apiClient.post('/copilot/query', { query });
