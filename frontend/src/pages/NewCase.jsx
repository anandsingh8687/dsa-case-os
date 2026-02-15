import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useDropzone } from 'react-dropzone';
import { useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Upload, FileText, CheckCircle, Sparkles } from 'lucide-react';
import { createCase, updateCase, uploadDocuments, getCaseStatus } from '../api/services';
import { Button, Input, Select, Card, ProgressBar } from '../components/ui';
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
  const [step, setStep] = useState(0); // Start at step 0 for mode selection
  const [workflowMode, setWorkflowMode] = useState(null); // 'form-first' or 'docs-first'
  const [caseId, setCaseId] = useState(null);
  const [files, setFiles] = useState([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileProgress, setFileProgress] = useState([]);
  const [gstData, setGstData] = useState(null);
  const [isCheckingGST, setIsCheckingGST] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm();

  const updateCaseMutation = useMutation({
    mutationFn: ({ caseId: currentCaseId, data }) => updateCase(currentCaseId, data),
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to update case');
    },
  });

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

  const waitForProcessing = async (targetCaseId) => {
    const pendingStatuses = new Set(['created', 'processing', 'documents_classified']);
    const maxAttempts = 30; // ~60 seconds

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await getCaseStatus(targetCaseId);
        const statusValue = response?.data?.status;
        if (!pendingStatuses.has(statusValue)) {
          return statusValue;
        }
      } catch (error) {
        // Keep polling even if one attempt fails.
      }
      await wait(2000);
    }
    return null;
  };

  const uploadMutation = useMutation({
    mutationFn: ({ caseId: currentCaseId, formData, totalFileBytes }) =>
      uploadDocuments(currentCaseId, formData, {
        onUploadProgress: (event) => {
          if (!event.total) return;
          const overallProgress = Math.round((event.loaded * 100) / event.total);
          setUploadProgress(overallProgress);
          updateProgressByLoadedBytes(
            Math.round((event.loaded / event.total) * totalFileBytes),
            totalFileBytes
          );
        },
      }),
    onSuccess: async (_response, variables) => {
      toast.success('Documents uploaded successfully! Processing...');
      setUploadProgress(100);
      setFileProgress((prev) => prev.map((entry) => ({ ...entry, progress: 100 })));

      const finalStatus = await waitForProcessing(variables.caseId);
      await checkForGSTData(variables.caseId);

      if (!finalStatus) {
        toast('Processing is taking longer than expected. You can continue now.', {
          icon: '⏳',
        });
      }

      if (workflowMode === 'docs-first') {
        setStep(2);
      } else {
        setStep(3);
      }
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to upload documents');
    },
  });

  // Check if GST data is available for this case
  const checkForGSTData = async (targetCaseId = caseId) => {
    if (!targetCaseId) return;

    setIsCheckingGST(true);
    try {
      const response = await apiClient.get(`/cases/${targetCaseId}/gst-data`);

      if (response.data && response.data.gst_data) {
        setGstData(response.data.gst_data);
        toast.success('🎉 GST data detected! You can auto-fill the form now.');
      }
    } catch (error) {
      // No GST data available yet - this is normal
      console.log('No GST data available yet');
    } finally {
      setIsCheckingGST(false);
    }
  };

  // Auto-fill form with GST data
  const autoFillFromGST = () => {
    if (!gstData) return;

    if (gstData.borrower_name) {
      setValue('borrower_name', gstData.borrower_name);
    }
    if (gstData.entity_type) {
      setValue('entity_type', gstData.entity_type);
    }
    if (gstData.pincode) {
      setValue('pincode', gstData.pincode);
    }

    toast.success('Form pre-filled from GST data!');
    setStep(1); // Go back to step 1 to edit
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
  const handleDocsFirstStart = async () => {
    try {
      const minimalData = {
        borrower_name: 'Pending Upload',
        entity_type: 'proprietorship',
        program_type: 'banking',
      };

      const response = await createCase(minimalData);
      setCaseId(response.data.case_id);
      setWorkflowMode('docs-first');
      setStep(1); // Go to upload step
      toast.success('Case created! Please upload documents.');
    } catch (error) {
      toast.error('Failed to create case. Please try again.');
      setStep(0); // Go back to mode selection
    }
  };

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
              Select how you'd like to create this case
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
              {/* Option 1: Form First (Traditional) */}
              <button
                onClick={() => {
                  setWorkflowMode('form-first');
                  setStep(1);
                }}
                className="group p-6 border-2 border-gray-200 rounded-xl hover:border-primary hover:bg-primary/5 transition-all text-left"
              >
                <div className="flex items-center justify-between mb-3">
                  <FileText className="w-8 h-8 text-primary" />
                  <span className="text-xs font-semibold text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    Traditional
                  </span>
                </div>
                <h3 className="text-lg font-semibold mb-2 group-hover:text-primary">
                  Fill Form First
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  Enter borrower details manually, then upload documents for verification
                </p>
                <div className="text-xs text-gray-500">
                  ✓ Best for returning clients<br />
                  ✓ When you know all details upfront
                </div>
              </button>

              {/* Option 2: Documents First (Smart) */}
              <button
                onClick={() => {
                  setWorkflowMode('docs-first');
                  // Create a minimal case first
                  handleDocsFirstStart();
                }}
                className="group p-6 border-2 border-primary bg-primary/5 rounded-xl hover:bg-primary/10 transition-all text-left relative overflow-hidden"
              >
                <div className="absolute top-2 right-2">
                  <span className="text-xs font-bold text-primary bg-white px-2 py-1 rounded-full shadow-sm">
                    ✨ SMART
                  </span>
                </div>
                <div className="flex items-center justify-between mb-3">
                  <Upload className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-lg font-semibold mb-2 text-primary">
                  Upload Documents First
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  Upload GST/Bank statements first, and we'll auto-fill the form for you
                </p>
                <div className="text-xs text-primary font-medium">
                  ✓ Auto-extracts borrower name<br />
                  ✓ Auto-fills entity type & pincode<br />
                  ✓ Calculates business vintage<br />
                  ✓ Saves time & reduces errors
                </div>
              </button>
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
              { num: 1, label: workflowMode === 'docs-first' ? 'Upload Documents' : 'Basic Info' },
              { num: 2, label: workflowMode === 'docs-first' ? 'Review & Complete' : 'Upload Documents' },
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
              {gstData && gstData.borrower_name && (
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
            <Button
              variant="primary"
              onClick={handleStep2Submit}
              disabled={uploadMutation.isPending || files.length === 0}
            >
              {uploadMutation.isPending ? 'Uploading & Extracting...' : 'Upload & Continue'}
            </Button>
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
            <Button
              variant="primary"
              onClick={handleStep2Submit}
              disabled={uploadMutation.isPending || files.length === 0}
            >
              {uploadMutation.isPending ? 'Uploading...' : 'Upload & Continue'}
            </Button>
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
            await updateCaseMutation.mutateAsync({
              caseId,
              data: toCasePayload(data),
            });
            toast.success('Case details saved!');
            setStep(3);
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
              {gstData && gstData.borrower_name && (
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
