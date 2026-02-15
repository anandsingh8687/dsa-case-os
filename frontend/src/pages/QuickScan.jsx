import React, { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Search, ArrowRight, Download } from 'lucide-react';

import { runQuickScan, getQuickScanCard } from '../api/services';
import { Button, Card, Loading, Badge } from '../components/ui';
import { formatCurrency } from '../utils/format';

const defaultForm = {
  loan_type: 'BL',
  cibil_score: 720,
  monthly_income_or_turnover: 12,
  vintage_or_experience: 2,
  entity_type_or_employer: 'proprietorship',
  pincode: '560001',
};

const QuickScan = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState(defaultForm);
  const [scanResult, setScanResult] = useState(null);

  const quickScanMutation = useMutation({
    mutationFn: runQuickScan,
    onSuccess: (response) => {
      setScanResult(response.data);
      toast.success('Quick scan completed.');
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Quick scan failed');
    },
  });

  const downloadCardMutation = useMutation({
    mutationFn: (scanId) => getQuickScanCard(scanId),
    onSuccess: (response, scanId) => {
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `quick_scan_${scanId}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Quick scan card downloaded');
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to download card');
    },
  });

  const matchedCount = scanResult?.matches_found || 0;
  const topTicket = useMemo(() => {
    if (!scanResult?.top_matches?.length) return null;
    return Math.max(...scanResult.top_matches.map((m) => Number(m.expected_ticket_max || 0)));
  }, [scanResult]);

  const onSubmit = (event) => {
    event.preventDefault();

    if (!/^\d{6}$/.test(form.pincode)) {
      toast.error('Pincode must be a 6-digit number');
      return;
    }

    quickScanMutation.mutate({
      ...form,
      cibil_score: Number(form.cibil_score),
      monthly_income_or_turnover: Number(form.monthly_income_or_turnover),
      vintage_or_experience: Number(form.vintage_or_experience),
      pincode: String(form.pincode),
    });
  };

  const convertToCase = () => {
    navigate('/cases/new', {
      state: {
        quickScanPrefill: {
          borrower_name: 'Quick Scan Prospect',
          entity_type: form.entity_type_or_employer,
          program_type: 'banking',
          pincode: form.pincode,
          loan_amount_requested: topTicket || null,
        },
      },
    });
    toast.success('Opening full case workflow. Upload documents to continue.');
  };

  return (
    <div className="space-y-6">
      <Card>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Instant Eligibility Quick Scan</h1>
        <p className="text-sm text-gray-600 mb-6">
          Run a 30-second BL eligibility snapshot before creating a full case.
        </p>

        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Loan Type</label>
            <select
              value={form.loan_type}
              onChange={(e) => setForm((prev) => ({ ...prev, loan_type: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              <option value="BL">Business Loan (BL)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CIBIL Score</label>
            <input
              type="number"
              min="300"
              max="900"
              value={form.cibil_score}
              onChange={(e) => setForm((prev) => ({ ...prev, cibil_score: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monthly Turnover (Lakhs)</label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={form.monthly_income_or_turnover}
              onChange={(e) => setForm((prev) => ({ ...prev, monthly_income_or_turnover: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Business Vintage (Years)</label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={form.vintage_or_experience}
              onChange={(e) => setForm((prev) => ({ ...prev, vintage_or_experience: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Entity Type</label>
            <select
              value={form.entity_type_or_employer}
              onChange={(e) => setForm((prev) => ({ ...prev, entity_type_or_employer: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              <option value="proprietorship">Proprietorship</option>
              <option value="partnership">Partnership</option>
              <option value="llp">LLP</option>
              <option value="pvt_ltd">Private Limited</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pincode</label>
            <input
              type="text"
              maxLength={6}
              value={form.pincode}
              onChange={(e) => setForm((prev) => ({ ...prev, pincode: e.target.value.replace(/\D/g, '') }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
          </div>

          <div className="md:col-span-2 lg:col-span-3 flex gap-3 pt-2">
            <Button type="submit" disabled={quickScanMutation.isPending} className="flex items-center gap-2">
              <Search className="w-4 h-4" />
              {quickScanMutation.isPending ? 'Scanning...' : 'Run Quick Scan'}
            </Button>

            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setForm(defaultForm);
                setScanResult(null);
              }}
            >
              Reset
            </Button>
          </div>
        </form>
      </Card>

      {quickScanMutation.isPending && (
        <Card>
          <Loading text="Evaluating lenders in real time..." />
        </Card>
      )}

      {scanResult && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Quick Scan Outcome</h2>
                <p className="text-sm text-gray-600 mt-1">
                  {matchedCount} matches out of {scanResult.total_evaluated} evaluated lenders
                </p>
                <p className="text-sm text-blue-800 mt-3 whitespace-pre-wrap">
                  {scanResult.summary_pitch}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={convertToCase}
                  className="flex items-center gap-2"
                >
                  Convert to Full Case
                  <ArrowRight className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline"
                  className="flex items-center gap-2"
                  onClick={() => downloadCardMutation.mutate(scanResult.scan_id)}
                  disabled={downloadCardMutation.isPending}
                >
                  <Download className="w-4 h-4" />
                  {downloadCardMutation.isPending ? 'Preparing...' : 'Card PNG'}
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Top Matching Lenders</h3>
            {(scanResult.top_matches || []).length === 0 ? (
              <p className="text-sm text-gray-600">No immediate matches found. Use recommended actions and retry.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Probability</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ticket Range</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Why</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {scanResult.top_matches.map((item, idx) => (
                      <tr key={`${item.lender_name}-${item.product_name}-${idx}`}>
                        <td className="px-4 py-3 text-sm font-medium text-gray-900">
                          {item.lender_name}
                          <div className="text-xs text-gray-500">{item.product_name}</div>
                        </td>
                        <td className="px-4 py-3 text-sm font-semibold text-primary">{Math.round(item.score || 0)}/100</td>
                        <td className="px-4 py-3 text-sm">
                          <Badge
                            variant={
                              item.probability === 'high'
                                ? 'success'
                                : item.probability === 'medium'
                                ? 'warning'
                                : 'danger'
                            }
                          >
                            {(item.probability || 'n/a').toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">
                          {formatCurrency(Number(item.expected_ticket_min || 0) * 100000)} - {formatCurrency(Number(item.expected_ticket_max || 0) * 100000)}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">{item.key_reason || 'Core hard filters satisfied'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <h3 className="text-lg font-semibold text-gray-900 mb-3">Recommended Next Actions</h3>
            <ul className="space-y-2 text-sm text-gray-700">
              {(scanResult.insights?.suggested_actions || []).slice(0, 5).map((action, idx) => (
                <li key={`qs-action-${idx}`}>• {action}</li>
              ))}
              {(scanResult.insights?.suggested_actions || []).length === 0 && (
                <li>• Keep CIBIL and document quality strong to maintain match confidence.</li>
              )}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
};

export default QuickScan;
