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

// Reports
export const generateReport = (caseId) =>
  apiClient.post(`/reports/case/${caseId}/generate`);

export const getReportPdf = (caseId) =>
  apiClient.get(`/reports/case/${caseId}/report/pdf`, {
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
