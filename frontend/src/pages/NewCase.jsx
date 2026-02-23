import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useDropzone } from 'react-dropzone';
import { useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Upload, FileText, CheckCircle, Sparkles, Search } from 'lucide-react';
import {
  createCase,
  updateCase,
  uploadDocuments,
  getCaseStatus,
  runExtraction,
  runScoring,
  generateReport,
} from '../api/services';
import {
  Button,
  ActionButton,
  Input,
  Select,
  Card,
  ProgressBar,
  WorkflowOptionCard,
} from '../components/ui';
import apiClient from '../api/client';

const ENTITY_OPTIONS = [
  { label: 'Proprietorship', value: 'proprietorship' },
  { label: 'Partnership', value: 'partnership' },
  { label: 'LLP', value: 'llp' },
  { label: 'Private Limited', value: 'pvt_ltd' },
  { label: 'Public Limited', value: 'public_ltd' },
  { label: 'Trust', value: 'trust' },
  { label: 'Society', value: 'society' },
  { label: 'HUF', value: 'huf' },
];

const PROGRAM_OPTIONS = [
  { label: 'Banking', value: 'banking' },
  { label: 'Income', value: 'income' },
  { label: 'Hybrid', value: 'hybrid' },
];

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const isRetryableStatusCode = (statusCode) => [408, 409, 429, 500, 502, 503, 504].includes(Number(statusCode));

const getBorrowerNameFromGst = (gstPayload) => {
  if (!gstPayload || typeof gstPayload !== 'object') return '';
  const candidates = [
    gstPayload.borrower_name,
    gstPayload.tradename,
    gstPayload.trade_name,
    gstPayload.tradeName,
    gstPayload.name,
    gstPayload.legal_name,
    gstPayload.legalName,
  ];
  return candidates.find((value) => typeof value === 'string' && value.trim())?.trim() || '';
};

const toCasePayload = (data) => {
  const normalized = { ...data };

  if (normalized.industry && !normalized.industry_type) {
    normalized.industry_type = normalized.industry;
  }
  delete normalized.industry;

  return normalized;
};

const NewCase = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState(0); // Start at step 0 for mode selection
  const [workflowMode, setWorkflowMode] = useState(null); // 'form-first' or 'docs-first'
  const [caseId, setCaseId] = useState(null);
  const [files, setFiles] = useState([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileProgress, setFileProgress] = useState([]);
  const [gstData, setGstData] = useState(null);
  const [isCheckingGST, setIsCheckingGST] = useState(false);
  const [uploadPhase, setUploadPhase] = useState('idle');
  const [uploadElapsedSeconds, setUploadElapsedSeconds] = useState(0);
  const [uploadEstimateMinutes, setUploadEstimateMinutes] = useState(0);

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm();

  const quickScanPrefill = location.state?.quickScanPrefill || null;
  const bankStatementPrefill = location.state?.bankStatementPrefill || null;
  const inboundPrefill = quickScanPrefill || bankStatementPrefill;

  const updateCaseMutation = useMutation({
    mutationFn: ({ caseId: currentCaseId, data }) => updateCase(currentCaseId, data),
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to update case');
    },
  });

  const runPostUploadPipeline = async (targetCaseId) => {
    const withRetry = async (fn) => {
      try {
        return await fn();
      } catch (error) {
        if (!isRetryableStatusCode(error?.response?.status)) {
          throw error;
        }
        await wait(1200);
        return fn();
      }
    };

    try {
      const queueState = await waitForDocumentJobs(targetCaseId);
      await checkForGSTData(targetCaseId);

      if (!queueState) {
        toast('Documents are still processing. Open the case from dashboard and run pipeline once processing reaches 100%.', {
          icon: 'ℹ️',
        });
        return;
      }

      const failedJobs = Number(queueState?.document_jobs?.failed || 0);
      if (failedJobs > 0) {
        toast(`Document processing finished with ${failedJobs} failed file(s). You can re-upload those files from case workspace.`, {
          icon: '⚠️',
        });
      }

      setUploadPhase('finishing');
      await withRetry(() => runExtraction(targetCaseId));
      await withRetry(() => runScoring(targetCaseId));
      await withRetry(() => generateReport(targetCaseId));
      toast.success('All processing stages completed automatically.');
    } catch (error) {
      const details = error?.response?.data?.detail;
      if (details) {
        console.warn('[NewCase] Auto pipeline warning:', details);
      }
      toast('Upload done. You can continue processing from case workspace.', { icon: 'ℹ️' });
    }
  };

  const createCaseMutation = useMutation({
    mutationFn: createCase,
    onSuccess: (response) => {
      console.log('[NewCase] Case created successfully!', response);
      setCaseId(response.data.case_id);
      toast.success('Case created successfully!');
      setStep(2);
    },
    onError: (error) => {
      console.error('[NewCase] Failed to create case:', error);
      console.error('[NewCase] Error response:', error.response);
      toast.error(error.response?.data?.detail || 'Failed to create case');
    },
  });

  const updateProgressByLoadedBytes = (loadedBytes, totalFileBytes) => {
    if (!totalFileBytes) return;

    let remaining = loadedBytes;
    setFileProgress((prev) =>
      prev.map((entry) => {
        const consumed = Math.max(0, Math.min(entry.size, remaining));
        remaining -= consumed;
        const filePercent = entry.size ? Math.round((consumed / entry.size) * 100) : 0;
        return { ...entry, progress: Math.max(entry.progress, Math.min(100, filePercent)) };
      })
    );
  };

  const waitForDocumentJobs = async (targetCaseId) => {
    const maxAttempts = 180; // ~6 minutes with 2-second polling
    let latestData = null;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await getCaseStatus(targetCaseId);
        latestData = response?.data;
        const jobs = response?.data?.document_jobs;
        if (jobs && typeof jobs.completion_pct === 'number') {
          setUploadProgress(Math.min(100, jobs.completion_pct));
        }
        if (!jobs || jobs.total === 0 || jobs.in_progress === false) {
          return latestData;
        }
      } catch (error) {
        // Keep polling even if one attempt fails.
      }
      await wait(2000);
    }
    return latestData;
  };

  const uploadMutation = useMutation({
    onMutate: ({ totalFileBytes }) => {
      const estimate = Math.max(2, Math.ceil(totalFileBytes / (5 * 1024 * 1024)));
      setUploadEstimateMinutes(estimate);
      setUploadElapsedSeconds(0);
      setUploadPhase('uploading');
    },
    mutationFn: ({ caseId: currentCaseId, formData, totalFileBytes }) =>
      uploadDocuments(currentCaseId, formData, {
        timeout: 600000,
        onUploadProgress: (event) => {
          if (!event.total) return;
          const overallProgress = Math.round((event.loaded * 100) / event.total);
          setUploadProgress(overallProgress);
          if (overallProgress >= 100) {
            setUploadPhase('server_processing');
          } else {
            setUploadPhase('uploading');
          }
          updateProgressByLoadedBytes(
            Math.round((event.loaded / event.total) * totalFileBytes),
            totalFileBytes
          );
        },
      }),
    onSuccess: async (_response, variables) => {
      toast.success('Documents uploaded. Background processing has started.');
      setUploadProgress(100);
      setUploadPhase('server_processing');
      setFileProgress((prev) => prev.map((entry) => ({ ...entry, progress: 100 })));
      void checkForGSTData(variables.caseId, { maxAttempts: 30, pollDelayMs: 1500 });

      if (workflowMode === 'docs-first') {
        setStep(2);
      } else {
        setStep(3);
      }

      // Trigger downstream stages only after async OCR/classification queue is done.
      void runPostUploadPipeline(variables.caseId);
    },
    onError: (error) => {
      setUploadPhase('idle');
      if (error?.code === 'ECONNABORTED') {
        toast.error('Upload request timed out. Files may still be processing. Refresh dashboard and open the case once it appears.');
        return;
      }
      toast.error(error.response?.data?.detail || 'Failed to upload documents');
    },
    onSettled: () => {
      setUploadPhase('idle');
    },
  });

  // Check if GST data is available for this case
  const checkForGSTData = async (targetCaseId = caseId, options = {}) => {
    if (!targetCaseId) return;
    const maxAttempts = Number.isFinite(options.maxAttempts) ? options.maxAttempts : 20;
    const pollDelayMs = Number.isFinite(options.pollDelayMs) ? options.pollDelayMs : 1500;

    setIsCheckingGST(true);
    try {
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          const response = await apiClient.get(`/cases/${targetCaseId}/gst-data`);
          if (response.data && response.data.gst_data) {
            setGstData(response.data.gst_data);
            toast.success('GST data detected and form pre-filled.');
            return;
          }
        } catch (error) {
          // continue polling for GST extraction
        }

        if (attempt < maxAttempts) {
          await wait(pollDelayMs);
        }
      }
      console.log('No GST data available yet');
    } finally {
      setIsCheckingGST(false);
    }
  };

  // Auto-fill form with GST data
  const autoFillFromGST = () => {
    if (!gstData) return;

    const borrowerName = getBorrowerNameFromGst(gstData);
    if (borrowerName) {
      setValue('borrower_name', borrowerName);
    }
    if (gstData.entity_type) {
      setValue('entity_type', gstData.entity_type);
    }
    if (gstData.pincode) {
      setValue('pincode', gstData.pincode);
    }

    toast.success('Form pre-filled from GST data!');
    if (workflowMode === 'form-first') {
      setStep(1);
    }
  };

  const onDrop = (acceptedFiles) => {
    setFiles((prev) => [...prev, ...acceptedFiles]);
    setFileProgress((prev) => [
      ...prev,
      ...acceptedFiles.map((file) => ({
        name: file.name,
        size: file.size,
        progress: 0,
      })),
    ]);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/*': ['.png', '.jpg', '.jpeg'],
      'application/zip': ['.zip'],
    },
  });

  const handleStep1Submit = (data) => {
    console.log('[NewCase] Form submitted!', data);
    console.log('[NewCase] Creating case with mutation...');
    createCaseMutation.mutate(toCasePayload(data));
  };

  const handleStep2Submit = () => {
    if (files.length === 0) {
      toast.error('Please upload at least one document');
      return;
    }

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const totalFileBytes = files.reduce((acc, file) => acc + file.size, 0);
    setUploadProgress(0);
    setFileProgress((prev) => prev.map((entry) => ({ ...entry, progress: 0 })));
    uploadMutation.mutate({ caseId, formData, totalFileBytes });
  };

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setFileProgress((prev) => prev.filter((_, i) => i !== index));
  };

  // Handle docs-first workflow - create minimal case to get case ID
  const handleDocsFirstStart = async (seedData = {}) => {
    try {
      const incomingBorrowerName = String(seedData.borrower_name || '').trim();
      const shouldUseBorrowerName =
        incomingBorrowerName.length > 0 && incomingBorrowerName.toLowerCase() !== 'quick scan prospect';

      const minimalData = {
        borrower_name: shouldUseBorrowerName ? incomingBorrowerName : undefined,
        entity_type: seedData.entity_type || 'proprietorship',
        program_type: seedData.program_type || 'banking',
        pincode: seedData.pincode || undefined,
        loan_amount_requested:
          seedData.loan_amount_requested !== null && seedData.loan_amount_requested !== undefined
            ? seedData.loan_amount_requested
            : undefined,
        industry_type: seedData.industry_type || undefined,
      };

      const response = await createCase(minimalData);
      setCaseId(response.data.case_id);
      setWorkflowMode('docs-first');
      setStep(1); // Go to upload step
      if (minimalData.borrower_name) {
        setValue('borrower_name', minimalData.borrower_name);
      }
      setValue('entity_type', minimalData.entity_type);
      setValue('program_type', minimalData.program_type);
      if (minimalData.pincode) {
        setValue('pincode', minimalData.pincode);
      }
      if (minimalData.industry_type) {
        setValue('industry', minimalData.industry_type);
      }
      toast.success('Case created! Please upload documents.');
    } catch (error) {
      toast.error('Failed to create case. Please try again.');
      setStep(0); // Go back to mode selection
    }
  };

  useEffect(() => {
    if (!inboundPrefill || step !== 0 || workflowMode || caseId) {
      return;
    }

    void handleDocsFirstStart(inboundPrefill);
    navigate('/cases/new', { replace: true, state: null });
  }, [inboundPrefill, step, workflowMode, caseId, navigate]);

  useEffect(() => {
    if (!gstData) return;

    const borrowerName = getBorrowerNameFromGst(gstData);
    if (borrowerName) {
      setValue('borrower_name', borrowerName);
    }
    if (gstData.entity_type) {
      setValue('entity_type', gstData.entity_type);
    }
    if (gstData.pincode) {
      setValue('pincode', String(gstData.pincode));
    }
  }, [gstData, setValue]);

  useEffect(() => {
    if (!uploadMutation.isPending) return undefined;

    const interval = window.setInterval(() => {
      setUploadElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => window.clearInterval(interval);
  }, [uploadMutation.isPending]);

  const uploadPhaseLabel = uploadPhase === 'server_processing'
    ? 'Files uploaded. OCR, classification, and GST checks are running on server.'
    : uploadPhase === 'finishing'
      ? 'Finalizing extracted data and preparing next step...'
      : 'Uploading files...';

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Create New Case</h1>

      {/* Step 0: Workflow Mode Selection */}
      {step === 0 && (
        <Card>
          <div className="text-center py-8">
            <Sparkles className="w-12 h-12 mx-auto mb-4 text-primary" />
            <h2 className="text-2xl font-semibold mb-2">Choose Your Workflow</h2>
            <p className="text-gray-600 mb-8">
              Start with quick scan or upload documents directly.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl mx-auto">
              <WorkflowOptionCard
                icon={Search}
                title="Run Quick Scan"
                description="Check eligibility first, then convert into a full case with prefilled details."
                highlights={[
                  'Instant lender snapshot',
                  'No initial document upload required',
                  'Seamless continuation to full case',
                ]}
                onClick={() => navigate('/quick-scan', { state: { fromNewCase: true } })}
                accent="blue"
              />

              <WorkflowOptionCard
                icon={Upload}
                title="Upload Documents"
                description="Upload GST and bank docs first. We detect GSTIN and auto-fill borrower details."
                highlights={[
                  'Auto-fills borrower trade/legal name',
                  'Auto-fills entity type and pincode',
                  'Calculates business vintage',
                  'Saves time and reduces errors',
                ]}
                badge="SMART"
                onClick={() => {
                  setWorkflowMode('docs-first');
                  handleDocsFirstStart();
                }}
                accent="primary"
              />
            </div>

            <div className="mt-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/dashboard')}
              >
                Cancel
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Progress Stepper - Show only after mode selected */}
      {step > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between">
            {[
              { num: 1, label: 'Upload Documents' },
              { num: 2, label: 'Review & Complete' },
              { num: 3, label: 'Complete' },
            ].map((s) => (
              <div
                key={s.num}
                className={`flex items-center ${
                  s.num < 3 ? 'flex-1' : ''
                }`}
              >
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-full font-semibold ${
                    step >= s.num
                      ? 'bg-primary text-white'
                      : 'bg-gray-200 text-gray-600'
                  }`}
                >
                  {step > s.num ? <CheckCircle className="w-6 h-6" /> : s.num}
                </div>
                <div className="ml-2 text-sm font-medium">
                  {s.label}
                </div>
                {s.num < 3 && (
                  <div
                    className={`flex-1 h-1 mx-4 ${
                      step > s.num ? 'bg-primary' : 'bg-gray-200'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Step 1: Basic Info (form-first) OR Upload (docs-first) */}
      {step === 1 && workflowMode === 'form-first' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Basic Information</h2>
          <form onSubmit={handleSubmit(handleStep1Submit)}>
            <div className="relative">
              <Input
                label="Borrower Name"
                placeholder="Enter borrower name"
                error={errors.borrower_name?.message}
                {...register('borrower_name', {
                  required: 'Borrower name is required',
                })}
              />
              {gstData && getBorrowerNameFromGst(gstData) && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <div className="relative">
              <Select
                label="Entity Type"
                options={ENTITY_OPTIONS}
                error={errors.entity_type?.message}
                {...register('entity_type', {
                  required: 'Entity type is required',
                })}
              />
              {gstData && gstData.entity_type && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <Select
              label="Program Type"
              options={PROGRAM_OPTIONS}
              error={errors.program_type?.message}
              {...register('program_type', {
                required: 'Program type is required',
              })}
            />

            <Input
              label="Industry"
              placeholder="e.g., Manufacturing, Retail"
              {...register('industry')}
            />

            <div className="relative">
              <Input
                label="Pincode"
                type="text"
                placeholder="Enter pincode"
                {...register('pincode', {
                  pattern: {
                    value: /^\d{6}$/,
                    message: 'Invalid pincode',
                  },
                })}
                error={errors.pincode?.message}
              />
              {gstData && gstData.pincode && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/dashboard')}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={createCaseMutation.isPending}
              >
                {createCaseMutation.isPending ? 'Creating...' : 'Next'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Step 1: Upload Documents (docs-first mode) */}
      {step === 1 && workflowMode === 'docs-first' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Upload Documents</h2>
          <p className="text-sm text-gray-600 mb-4">
            Upload your GST documents, bank statements, or other files. We'll extract the information automatically!
          </p>

          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              isDragActive
                ? 'border-primary bg-blue-50'
                : 'border-gray-300 hover:border-primary'
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600 mb-2">
              {isDragActive
                ? 'Drop files here...'
                : 'Drag & drop files here, or click to select'}
            </p>
            <p className="text-sm text-gray-500">
              Supports: PDF, Images, ZIP files
            </p>
            <p className="text-xs text-primary mt-2 font-medium">
              💡 Include GST documents for smart auto-fill!
            </p>
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="mt-6">
              <h3 className="font-medium mb-2">Selected Files ({files.length})</h3>
              <div className="space-y-2">
                {files.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center">
                      <FileText className="w-5 h-5 text-gray-400 mr-2" />
                      <span className="text-sm">{file.name}</span>
                      <span className="text-xs text-gray-500 ml-2">
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <button
                      onClick={() => removeFile(index)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isCheckingGST && (
            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-center">
              <p className="text-sm text-blue-700">🔍 Extracting GST data...</p>
            </div>
          )}

          {uploadMutation.isPending && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                <div className="font-medium">{uploadPhaseLabel}</div>
                <div className="mt-1 text-xs text-blue-700">
                  Elapsed: {Math.floor(uploadElapsedSeconds / 60)}m {uploadElapsedSeconds % 60}s
                  {uploadEstimateMinutes > 0 ? ` • Typical for this upload: ~${uploadEstimateMinutes}-${uploadEstimateMinutes + 2} min` : ''}
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600">Upload Progress</span>
                  <span className="font-medium">{uploadProgress}%</span>
                </div>
                <ProgressBar value={uploadProgress} max={100} />
              </div>
              {fileProgress.length > 0 && (
                <div className="space-y-2">
                  {fileProgress.map((entry, index) => (
                    <div key={`${entry.name}-${index}`}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600 truncate">{entry.name}</span>
                        <span>{entry.progress}%</span>
                      </div>
                      <ProgressBar value={entry.progress} max={100} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between mt-6">
            <Button variant="outline" onClick={() => setStep(0)}>
              Back
            </Button>
            <ActionButton
              variant="primary"
              onClick={handleStep2Submit}
              loading={uploadMutation.isPending}
              loadingText={
                uploadPhase === 'server_processing'
                  ? 'Processing Documents on Server...'
                  : 'Uploading...'
              }
              disabled={files.length === 0}
            >
              Upload & Continue
            </ActionButton>
          </div>
        </Card>
      )}

      {/* Step 2: Upload Documents (form-first mode) OR Review Form (docs-first mode) */}
      {step === 2 && workflowMode === 'form-first' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Upload Documents</h2>

          {/* GST Auto-fill Banner */}
          {gstData && (
            <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-green-600" />
                  <div>
                    <p className="font-medium text-green-800">GST Data Detected!</p>
                    <p className="text-sm text-green-700">
                      We found company details from your GST documents.
                    </p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={autoFillFromGST}
                >
                  Auto-fill Form
                </Button>
              </div>
            </div>
          )}

          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              isDragActive
                ? 'border-primary bg-blue-50'
                : 'border-gray-300 hover:border-primary'
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600 mb-2">
              {isDragActive
                ? 'Drop files here...'
                : 'Drag & drop files here, or click to select'}
            </p>
            <p className="text-sm text-gray-500">
              Supports: PDF, Images, ZIP files (Include GST documents for auto-fill!)
            </p>
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="mt-6">
              <h3 className="font-medium mb-2">Selected Files ({files.length})</h3>
              <div className="space-y-2">
                {files.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center">
                      <FileText className="w-5 h-5 text-gray-400 mr-2" />
                      <span className="text-sm">{file.name}</span>
                      <span className="text-xs text-gray-500 ml-2">
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <button
                      onClick={() => removeFile(index)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {uploadMutation.isPending && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                <div className="font-medium">{uploadPhaseLabel}</div>
                <div className="mt-1 text-xs text-blue-700">
                  Elapsed: {Math.floor(uploadElapsedSeconds / 60)}m {uploadElapsedSeconds % 60}s
                  {uploadEstimateMinutes > 0 ? ` • Typical for this upload: ~${uploadEstimateMinutes}-${uploadEstimateMinutes + 2} min` : ''}
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600">Upload Progress</span>
                  <span className="font-medium">{uploadProgress}%</span>
                </div>
                <ProgressBar value={uploadProgress} max={100} />
              </div>
              {fileProgress.length > 0 && (
                <div className="space-y-2">
                  {fileProgress.map((entry, index) => (
                    <div key={`${entry.name}-${index}`}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600 truncate">{entry.name}</span>
                        <span>{entry.progress}%</span>
                      </div>
                      <ProgressBar value={entry.progress} max={100} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between mt-6">
            <Button variant="outline" onClick={() => setStep(1)}>
              Back
            </Button>
            <ActionButton
              variant="primary"
              onClick={handleStep2Submit}
              loading={uploadMutation.isPending}
              loadingText={
                uploadPhase === 'server_processing'
                  ? 'Processing Documents on Server...'
                  : 'Uploading...'
              }
              disabled={files.length === 0}
            >
              Upload & Continue
            </ActionButton>
          </div>
        </Card>
      )}

      {/* Step 2: Review & Complete Form (docs-first mode) */}
      {step === 2 && workflowMode === 'docs-first' && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Review & Complete Information</h2>

          {/* GST Auto-fill Banner */}
          {gstData && (
            <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-green-600" />
                <div>
                  <p className="font-medium text-green-800">GST Data Extracted!</p>
                  <p className="text-sm text-green-700">
                    Form has been pre-filled with extracted data. Please review and adjust if needed.
                  </p>
                </div>
              </div>
            </div>
          )}

          {!gstData && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-700">
                No GST data was extracted. Please fill the form manually.
              </p>
            </div>
          )}

          <form onSubmit={handleSubmit(async (data) => {
            if (!caseId) {
              toast.error('Case not found. Please restart this flow.');
              return;
            }
            const payload = toCasePayload(data);
            let updated = false;
            let lastError = null;

            for (let attempt = 1; attempt <= 2; attempt += 1) {
              try {
                await updateCaseMutation.mutateAsync({
                  caseId,
                  data: payload,
                });
                updated = true;
                break;
              } catch (error) {
                lastError = error;
                if (attempt < 2) {
                  await wait(700);
                }
              }
            }

            if (!updated) {
              if (!lastError) {
                toast.error('Failed to update case');
              }
              return;
            }

            toast.success('Case details saved!');
            navigate(`/cases/${caseId}`);
          })}>
            <div className="relative">
              <Input
                label="Borrower Name"
                placeholder="Enter borrower name"
                error={errors.borrower_name?.message}
                {...register('borrower_name', {
                  required: 'Borrower name is required',
                })}
              />
              {gstData && getBorrowerNameFromGst(gstData) && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <div className="relative">
              <Select
                label="Entity Type"
                options={ENTITY_OPTIONS}
                error={errors.entity_type?.message}
                {...register('entity_type', {
                  required: 'Entity type is required',
                })}
              />
              {gstData && gstData.entity_type && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <Select
              label="Program Type"
              options={PROGRAM_OPTIONS}
              error={errors.program_type?.message}
              {...register('program_type', {
                required: 'Program type is required',
              })}
            />

            <Input
              label="Industry"
              placeholder="e.g., Manufacturing, Retail"
              {...register('industry')}
            />

            <div className="relative">
              <Input
                label="Pincode"
                type="text"
                placeholder="Enter pincode"
                {...register('pincode', {
                  pattern: {
                    value: /^\d{6}$/,
                    message: 'Invalid pincode',
                  },
                })}
                error={errors.pincode?.message}
              />
              {gstData && gstData.pincode && (
                <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Auto-filled from GST
                </p>
              )}
            </div>

            <div className="flex justify-between mt-6">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={updateCaseMutation.isPending}
              >
                {updateCaseMutation.isPending ? 'Saving...' : 'Complete Case'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Step 3: Complete */}
      {step === 3 && (
        <Card>
          <div className="text-center py-8">
            <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
            <h2 className="text-2xl font-semibold mb-2">Case Created!</h2>
            <p className="text-gray-600 mb-6">
              Your case has been created and documents are being processed.
            </p>
            <div className="flex gap-3 justify-center">
              <Button
                variant="outline"
                onClick={() => navigate('/dashboard')}
              >
                Back to Dashboard
              </Button>
              <Button
                variant="primary"
                onClick={() => navigate(`/cases/${caseId}`)}
              >
                View Case
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default NewCase;
