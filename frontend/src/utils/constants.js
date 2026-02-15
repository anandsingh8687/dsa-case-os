export const ENTITY_TYPES = [
  'Proprietorship',
  'Partnership',
  'LLP',
  'Private Limited',
  'Public Limited',
  'Trust',
  'Society',
  'HUF',
];

export const PROGRAM_TYPES = ['Banking', 'Income', 'Hybrid'];

export const DOCUMENT_TYPES = [
  'PAN',
  'Aadhaar',
  'GST',
  'ITR',
  'Bank Statement',
  'Financial Statement',
  'Utility Bill',
  'Rent Agreement',
  'MOA/AOA',
  'Partnership Deed',
  'LLP Agreement',
  'Board Resolution',
  'Share Certificate',
  'License/Registration',
  'Existing Loan Statement',
  'CIBIL Report',
  'Property Document',
  'Invoice',
  'Purchase Order',
  'Other',
];

export const CASE_STATUSES = {
  created: { label: 'Created', color: 'bg-gray-500' },
  documents_uploaded: { label: 'Documents Uploaded', color: 'bg-blue-500' },
  processing: { label: 'Processing', color: 'bg-yellow-500' },
  documents_classified: { label: 'Documents Classified', color: 'bg-cyan-500' },
  features_extracted: { label: 'Features Extracted', color: 'bg-purple-500' },
  scored: { label: 'Scored', color: 'bg-indigo-500' },
  eligibility_scored: { label: 'Eligibility Scored', color: 'bg-indigo-500' },
  report_generated: { label: 'Report Generated', color: 'bg-green-500' },
  failed: { label: 'Failed', color: 'bg-red-500' },
};

export const CONFIDENCE_LEVELS = {
  HIGH: { label: 'HIGH', color: 'text-green-600 bg-green-100' },
  MEDIUM: { label: 'MEDIUM', color: 'text-yellow-600 bg-yellow-100' },
  LOW: { label: 'LOW', color: 'text-red-600 bg-red-100' },
};
