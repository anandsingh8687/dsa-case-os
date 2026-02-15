import React, { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { FileSpreadsheet, UploadCloud, Download, Loader2 } from 'lucide-react';

import { processBankStatements } from '../api/services';
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
  const [files, setFiles] = useState([]);
  const [jsonPreview, setJsonPreview] = useState(null);

  const totalSize = useMemo(
    () => files.reduce((sum, file) => sum + (file.size || 0), 0),
    [files]
  );

  const processMutation = useMutation({
    mutationFn: (selectedFiles) => {
      const formData = new FormData();
      selectedFiles.forEach((file) => {
        formData.append('files', file);
      });
      return processBankStatements(formData);
    },
    onSuccess: async (response) => {
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
  });

  const onFilesChange = (event) => {
    const selected = Array.from(event.target.files || []);
    const accepted = selected.filter((file) => {
      const lower = file.name.toLowerCase();
      return lower.endsWith('.pdf') || lower.endsWith('.zip') || lower.endsWith('.xlsx') || lower.endsWith('.xls');
    });
    setFiles(accepted);
  };

  const runAnalysis = () => {
    if (!files.length) {
      toast.error('Please select at least one file.');
      return;
    }
    processMutation.mutate(files);
  };

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
                Processing...
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
            }}
            disabled={processMutation.isPending}
          >
            Reset
          </Button>
        </div>
      </Card>

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
