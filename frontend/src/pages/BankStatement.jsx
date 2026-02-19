import React, { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { FileSpreadsheet, UploadCloud, Download, Loader2, ArrowRight } from 'lucide-react';

import {
  processBankStatements,
  createCase,
  uploadDocuments,
  getCaseStatus,
  runExtraction,
  runScoring,
  generateReport,
} from '../api/services';
import { Card, Button } from '../components/ui';

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(1)} ${units[idx]}`;
};

const BankStatement = () => {
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const [jsonPreview, setJsonPreview] = useState(null);
  const [analysisReady, setAnalysisReady] = useState(false);
  const [analysisElapsedSeconds, setAnalysisElapsedSeconds] = useState(0);
  const [analysisPhase, setAnalysisPhase] = useState('idle');
  const [analysisUploadProgress, setAnalysisUploadProgress] = useState(0);
  const [convertInput, setConvertInput] = useState({
    borrower_name: '',
    entity_type: 'proprietorship',
    program_type: 'banking',
    pincode: '',
  });

  const totalSize = useMemo(
    () => files.reduce((sum, file) => sum + (file.size || 0), 0),
    [files]
  );

  const processMutation = useMutation({
    onMutate: () => {
      setAnalysisReady(false);
      setAnalysisPhase('uploading');
      setAnalysisElapsedSeconds(0);
      setAnalysisUploadProgress(0);
      setJsonPreview(null);
    },
    mutationFn: (selectedFiles) => {
      const formData = new FormData();
      selectedFiles.forEach((file) => {
        formData.append('files', file);
      });
      return processBankStatements(formData, {
        onUploadProgress: (event) => {
          if (!event.total) return;
          const pct = Math.round((event.loaded * 100) / event.total);
          setAnalysisUploadProgress(pct);
          if (pct >= 100) {
            setAnalysisPhase('analyzing');
          }
        },
      });
    },
    onSuccess: async (response) => {
      setAnalysisReady(true);
      const contentType = response.headers?.['content-type'] || '';
      const contentDisposition = response.headers?.['content-disposition'] || '';

      if (contentType.includes('application/json')) {
        const text = await response.data.text();
        const parsed = JSON.parse(text);
        setJsonPreview(parsed);
        toast.success('Bank statement analysis completed (JSON response).');
        return;
      }

      const filenameMatch = contentDisposition.match(/filename="?([^\";]+)"?/i);
      const filename = filenameMatch?.[1] || `bank_statement_analysis_${Date.now()}.xlsx`;
      const blob = new Blob([response.data], { type: contentType || 'application/octet-stream' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setJsonPreview(null);
      toast.success('Analysis complete. Excel downloaded.');
    },
    onError: async (error) => {
      if (error?.code === 'ECONNABORTED') {
        toast.error('Analyzer timed out. Try 1-3 statements per run for faster processing.');
        return;
      }
      const fallback = error.response?.data?.detail || 'Bank statement processing failed.';
      if (error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const parsed = JSON.parse(text);
          toast.error(parsed?.detail || fallback);
          return;
        } catch {
          toast.error(fallback);
          return;
        }
      }
      toast.error(fallback);
    },
    onSettled: () => {
      setAnalysisPhase('idle');
    },
  });

  const onFilesChange = (event) => {
    const selected = Array.from(event.target.files || []);
    const accepted = selected.filter((file) => {
      const lower = file.name.toLowerCase();
      return lower.endsWith('.pdf') || lower.endsWith('.zip') || lower.endsWith('.xlsx') || lower.endsWith('.xls');
    });
    setFiles(accepted);
    setAnalysisReady(false);
  };

  const runAnalysis = () => {
    if (!files.length) {
      toast.error('Please select at least one file.');
      return;
    }
    processMutation.mutate(files);
  };

  useEffect(() => {
    if (!processMutation.isPending) return undefined;

    const interval = window.setInterval(() => {
      setAnalysisElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => window.clearInterval(interval);
  }, [processMutation.isPending]);

  const caseUploadEligibleFiles = useMemo(
    () => files.filter((file) => /\.(pdf|zip|png|jpg|jpeg|tiff)$/i.test(file.name)),
    [files]
  );

  const waitMs = (ms) => new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });

  const isRetryable = (statusCode) => [408, 409, 429, 500, 502, 503, 504].includes(Number(statusCode));

  const withRetry = async (fn) => {
    try {
      return await fn();
    } catch (error) {
      if (!isRetryable(error?.response?.status)) {
        throw error;
      }
      await waitMs(1200);
      return fn();
    }
  };

  const waitForDocumentQueue = async (targetCaseId) => {
    const maxAttempts = 180;
    let latest = null;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const response = await getCaseStatus(targetCaseId);
        latest = response?.data;
        const jobs = latest?.document_jobs;
        if (!jobs || jobs.total === 0 || jobs.in_progress === false) {
          return latest;
        }
      } catch (_) {
        // keep polling
      }
      await waitMs(2000);
    }
    return latest;
  };

  const convertToCaseMutation = useMutation({
    mutationFn: async () => {
      const borrowerName = convertInput.borrower_name.trim();
      if (!borrowerName) {
        throw new Error('Borrower name is required to convert into a full case.');
      }

      const created = await createCase({
        borrower_name: borrowerName,
        entity_type: convertInput.entity_type,
        program_type: convertInput.program_type,
        pincode: convertInput.pincode || undefined,
      });
      const newCaseId = created.data.case_id;

      if (caseUploadEligibleFiles.length === 0) {
        return {
          caseId: newCaseId,
          docsUploaded: false,
        };
      }

      const formData = new FormData();
      caseUploadEligibleFiles.forEach((file) => {
        formData.append('files', file);
      });

      await uploadDocuments(newCaseId, formData);

      // Fire downstream processing in background after async document queue completes.
      void (async () => {
        const queueState = await waitForDocumentQueue(newCaseId);
        const failedJobs = Number(queueState?.document_jobs?.failed || 0);
        if (failedJobs > 0) {
          toast(`Document processing finished with ${failedJobs} failed file(s).`, {
            icon: '⚠️',
          });
        }
        try {
          await withRetry(() => runExtraction(newCaseId));
          await withRetry(() => runScoring(newCaseId));
          await withRetry(() => generateReport(newCaseId));
        } catch (_) {
          // User can continue from case workspace if background run fails.
        }
      })();

      return {
        caseId: newCaseId,
        docsUploaded: true,
      };
    },
    onSuccess: ({ caseId, docsUploaded }) => {
      toast.success(
        docsUploaded
          ? 'Full case created with bank statement files. Opening workspace.'
          : 'Full case created. Please upload supporting documents in case workspace.'
      );
      navigate(`/cases/${caseId}`);
    },
    onError: (error) => {
      toast.error(error?.message || error.response?.data?.detail || 'Failed to convert to full case.');
    },
  });

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Bank Statement Analyzer</h1>
            <p className="text-sm text-gray-600">
              Upload one or multiple statements. The pipeline proxies to your existing analyzer and returns an Excel output.
            </p>
          </div>
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
            Existing analyzer preserved
          </div>
        </div>

        <div className="mt-6 border border-dashed border-gray-300 rounded-lg p-6 bg-gray-50">
          <label className="flex flex-col items-center justify-center cursor-pointer text-center">
            <UploadCloud className="w-8 h-8 text-gray-500 mb-2" />
            <span className="text-sm font-medium text-gray-700">Select Bank Statement Files</span>
            <span className="text-xs text-gray-500 mt-1">Supported: PDF, ZIP, XLSX, XLS</span>
            <input
              type="file"
              multiple
              className="hidden"
              onChange={onFilesChange}
            />
          </label>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="rounded-lg border border-gray-200 p-3">
            <div className="text-gray-500">Selected Files</div>
            <div className="text-xl font-semibold text-gray-900">{files.length}</div>
          </div>
          <div className="rounded-lg border border-gray-200 p-3">
            <div className="text-gray-500">Total Size</div>
            <div className="text-xl font-semibold text-gray-900">{formatBytes(totalSize)}</div>
          </div>
          <div className="rounded-lg border border-gray-200 p-3">
            <div className="text-gray-500">Output</div>
            <div className="text-xl font-semibold text-gray-900">Excel / JSON</div>
          </div>
        </div>

        {files.length > 0 && (
          <div className="mt-4 rounded-lg border border-gray-200 bg-white">
            <div className="px-4 py-3 border-b border-gray-200 text-sm font-semibold text-gray-800">File Queue</div>
            <div className="max-h-52 overflow-auto divide-y divide-gray-100">
              {files.map((file) => (
                <div key={`${file.name}-${file.size}`} className="px-4 py-2 text-sm flex items-center justify-between">
                  <div className="text-gray-700">{file.name}</div>
                  <div className="text-gray-500">{formatBytes(file.size)}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <Button
            onClick={runAnalysis}
            disabled={processMutation.isPending || files.length === 0}
            className="flex items-center gap-2"
          >
            {processMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {analysisPhase === 'analyzing' ? 'Analyzing Statements...' : 'Uploading Files...'}
              </>
            ) : (
              <>
                <FileSpreadsheet className="w-4 h-4" />
                Run Analysis
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setFiles([]);
              setJsonPreview(null);
              setAnalysisReady(false);
            }}
            disabled={processMutation.isPending}
          >
            Reset
          </Button>
        </div>

        {processMutation.isPending && (
          <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
            <div className="font-medium">
              {analysisPhase === 'analyzing'
                ? 'Upload complete. Analyzer is processing your statements on server.'
                : 'Uploading bank statement files...'}
            </div>
            <div className="mt-1 text-xs text-blue-700">
              Elapsed: {Math.floor(analysisElapsedSeconds / 60)}m {analysisElapsedSeconds % 60}s
              {analysisPhase === 'analyzing' ? ' • Typical time: 1-3 minutes for large PDFs/ZIP' : ` • Upload: ${analysisUploadProgress}%`}
            </div>
          </div>
        )}
      </Card>

      {analysisReady && (
        <Card className="border-blue-100 bg-blue-50">
          <h2 className="text-lg font-semibold text-blue-900 mb-2">Convert to Full Case</h2>
          <p className="text-sm text-blue-800 mb-4">
            Move this bank-statement run into the full DSA case journey. Bank files will be attached automatically
            when supported (PDF/ZIP/Image), and you can add remaining docs in case workspace.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-blue-900 mb-1">Borrower Name</label>
              <input
                value={convertInput.borrower_name}
                onChange={(e) => setConvertInput((prev) => ({ ...prev, borrower_name: e.target.value }))}
                placeholder="Enter borrower / business name"
                className="w-full border border-blue-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-blue-900 mb-1">Pincode (Optional)</label>
              <input
                value={convertInput.pincode}
                onChange={(e) =>
                  setConvertInput((prev) => ({ ...prev, pincode: e.target.value.replace(/\D/g, '').slice(0, 6) }))
                }
                placeholder="6-digit pincode"
                className="w-full border border-blue-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-blue-900 mb-1">Entity Type</label>
              <select
                value={convertInput.entity_type}
                onChange={(e) => setConvertInput((prev) => ({ ...prev, entity_type: e.target.value }))}
                className="w-full border border-blue-200 rounded-lg px-3 py-2 text-sm"
              >
                <option value="proprietorship">Proprietorship</option>
                <option value="partnership">Partnership</option>
                <option value="llp">LLP</option>
                <option value="pvt_ltd">Private Limited</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-blue-900 mb-1">Program Type</label>
              <select
                value={convertInput.program_type}
                onChange={(e) => setConvertInput((prev) => ({ ...prev, program_type: e.target.value }))}
                className="w-full border border-blue-200 rounded-lg px-3 py-2 text-sm"
              >
                <option value="banking">Banking</option>
                <option value="income">Income</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </div>
          </div>
          <div className="mt-3 text-xs text-blue-800">
            Files selected: {files.length} | Eligible for auto-attach: {caseUploadEligibleFiles.length}
          </div>
          <div className="mt-4">
            <Button
              onClick={() => convertToCaseMutation.mutate()}
              disabled={convertToCaseMutation.isPending}
              className="inline-flex items-center gap-2"
            >
              {convertToCaseMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Converting...
                </>
              ) : (
                <>
                  Convert to Full Case
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </Button>
          </div>
        </Card>
      )}

      {jsonPreview && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">JSON Output Preview</h2>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const blob = new Blob([JSON.stringify(jsonPreview, null, 2)], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', `bank_statement_analysis_${Date.now()}.json`);
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.URL.revokeObjectURL(url);
              }}
              className="flex items-center gap-1"
            >
              <Download className="w-3.5 h-3.5" />
              Download JSON
            </Button>
          </div>
          <pre className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-4 overflow-auto max-h-[420px] text-gray-700">
            {JSON.stringify(jsonPreview, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
};

export default BankStatement;
