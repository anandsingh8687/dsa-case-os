import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Search, ArrowRight, Download, ChevronLeft } from 'lucide-react';

import {
  runQuickScan,
  getQuickScanCard,
  getQuickScanKnowledgeBaseStats,
  lookupGstDetails,
} from '../api/services';
import { Button, Card, Loading, Badge } from '../components/ui';
import { formatCurrency } from '../utils/format';

const defaultForm = {
  gstin: '',
  company_name: '',
  business_address: '',
  loan_type: 'BL',
  cibil_score: 720,
  monthly_income_or_turnover: 12,
  vintage_or_experience: 2,
  entity_type_or_employer: 'proprietorship',
  pincode: '560001',
};

const GSTIN_PATTERN = /^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$/i;

const isValidGstin = (value) => GSTIN_PATTERN.test(String(value || '').trim().toUpperCase());

const normalizeEntityType = (value) => {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_');
  const map = {
    proprietorship: 'proprietorship',
    proprietary: 'proprietorship',
    sole_proprietorship: 'proprietorship',
    partnership: 'partnership',
    llp: 'llp',
    private_limited: 'pvt_ltd',
    private_ltd: 'pvt_ltd',
    pvt_ltd: 'pvt_ltd',
    pvt_limited: 'pvt_ltd',
  };
  return map[normalized] || 'proprietorship';
};

const getCompanyNameFromGst = (gstPayload) => {
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

const getBusinessAddressFromGst = (gstPayload) => {
  if (!gstPayload || typeof gstPayload !== 'object') return '';
  const candidates = [
    gstPayload.address,
    gstPayload.principal_address,
    gstPayload.principal_place,
    gstPayload.pradr_address,
  ];
  const direct = candidates.find((value) => typeof value === 'string' && value.trim());
  if (direct) return String(direct).trim();
  const pradr = gstPayload?.raw_response?.pradr;
  if (pradr && typeof pradr === 'object') {
    const composed = ['bno', 'bnm', 'st', 'loc', 'dst', 'stcd', 'pncd']
      .map((key) => (pradr[key] ? String(pradr[key]).trim() : ''))
      .filter(Boolean)
      .join(', ');
    if (composed) return composed;
  }
  return '';
};

const QuickScan = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState(defaultForm);
  const [scanResult, setScanResult] = useState(null);
  const [manualWithoutGst, setManualWithoutGst] = useState(false);
  const [isCheckingGST, setIsCheckingGST] = useState(false);
  const [gstData, setGstData] = useState(null);
  const [lastLookedUpGstin, setLastLookedUpGstin] = useState('');
  const launchedFromNewCase = Boolean(location.state?.fromNewCase);

  const { data: kbStatsData } = useQuery({
    queryKey: ['quick-scan-kb-stats'],
    queryFn: getQuickScanKnowledgeBaseStats,
    staleTime: 1000 * 60 * 15,
  });

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
  const isBusinessLoan = form.loan_type === 'BL';
  const monthlyFieldLabel = isBusinessLoan ? 'Monthly Turnover (Lakhs)' : 'Monthly Income (INR)';
  const profileFieldLabel = isBusinessLoan ? 'Entity Type' : 'Applicant Type';
  const vintageFieldLabel = isBusinessLoan ? 'Business Vintage (Years)' : 'Work/Business Experience (Years)';

  const topTicket = useMemo(() => {
    if (!scanResult?.top_matches?.length) return null;
    return Math.max(...scanResult.top_matches.map((m) => Number(m.expected_ticket_max || 0)));
  }, [scanResult]);

  const kbStats = kbStatsData?.data;
  const plCount = kbStats?.by_loan_type?.PL || 0;
  const hlCount = kbStats?.by_loan_type?.HL || 0;

  const lookupAndAutofillByGstin = async (rawGstin) => {
    const normalized = String(rawGstin || '').trim().toUpperCase();
    if (!isValidGstin(normalized)) return;
    if (normalized === lastLookedUpGstin) return;

    setIsCheckingGST(true);
    try {
      const response = await lookupGstDetails(normalized);
      const payload = response?.data?.gst_data;
      if (!payload) {
        toast.error('GST details not found for this GSTIN');
        return;
      }

      const companyName = getCompanyNameFromGst(payload);
      const businessAddress = getBusinessAddressFromGst(payload);
      const pincode = String(payload?.pincode || '').replace(/\D/g, '').slice(0, 6);
      const entity = normalizeEntityType(payload?.entity_type);

      setGstData(payload);
      setLastLookedUpGstin(normalized);
      setForm((prev) => ({
        ...prev,
        gstin: normalized,
        company_name: companyName || prev.company_name,
        business_address: businessAddress || prev.business_address,
        entity_type_or_employer: entity || prev.entity_type_or_employer,
        pincode: pincode || prev.pincode,
      }));
      toast.success('GST details auto-filled');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Unable to fetch GST details');
    } finally {
      setIsCheckingGST(false);
    }
  };

  useEffect(() => {
    if (manualWithoutGst) return undefined;
    const normalized = String(form.gstin || '').trim().toUpperCase();
    if (!isValidGstin(normalized) || normalized === lastLookedUpGstin) return undefined;
    const timer = window.setTimeout(() => {
      void lookupAndAutofillByGstin(normalized);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [form.gstin, manualWithoutGst, lastLookedUpGstin]);

  const onSubmit = (event) => {
    event.preventDefault();

    if (!manualWithoutGst) {
      if (!isValidGstin(form.gstin)) {
        toast.error('Valid GST Number is required');
        return;
      }
    } else if (!String(form.company_name || '').trim()) {
      toast.error('Company Name is required when GST is unavailable');
      return;
    }

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
    const companyName = String(form.company_name || '').trim();
    navigate('/cases/new', {
      state: {
        quickScanPrefill: {
          borrower_name: companyName || undefined,
          gstin: !manualWithoutGst ? String(form.gstin || '').trim().toUpperCase() : undefined,
          business_address: form.business_address || undefined,
          entity_type: isBusinessLoan ? form.entity_type_or_employer : 'proprietorship',
          program_type: form.loan_type === 'PL' ? 'income' : form.loan_type === 'HL' ? 'hybrid' : 'banking',
          pincode: form.pincode,
          loan_amount_requested: topTicket || null,
        },
      },
    });
    toast.success('Opening full case workflow with quick-scan prefill.');
  };

  return (
    <div className="space-y-6">
      {launchedFromNewCase && (
        <Card className="border-blue-100 bg-blue-50">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-blue-900">New Case Assistant: Quick Scan</div>
              <div className="text-xs text-blue-800 mt-1">
                Run this scan and convert directly into New Case with prefilled fields.
              </div>
            </div>
            <Button
              variant="outline"
              className="w-full md:w-auto"
              onClick={() => navigate('/cases/new')}
            >
              <span className="inline-flex items-center gap-2">
                <ChevronLeft className="w-4 h-4" />
                Back to New Case
              </span>
            </Button>
          </div>
        </Card>
      )}

      <Card>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Instant Eligibility Quick Scan</h1>
        <p className="text-sm text-gray-600 mb-6">
          Start with GST for auto-fill, then run a 30-second BL/PL/HL eligibility snapshot before creating a full case.
        </p>
        {kbStats && (
          <div className="mb-6 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-900">
            PL/HL policy knowledge base loaded: {kbStats.total} rows
            {' '}({plCount} PL, {hlCount} HL).
          </div>
        )}

        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">GST Number</label>
            <input
              type="text"
              maxLength={15}
              value={form.gstin}
              onChange={(e) => setForm((prev) => ({ ...prev, gstin: e.target.value.toUpperCase() }))}
              onBlur={(e) => {
                if (!manualWithoutGst && isValidGstin(e.target.value)) {
                  void lookupAndAutofillByGstin(e.target.value);
                }
              }}
              placeholder="Enter 15-character GSTIN"
              disabled={manualWithoutGst}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 disabled:bg-gray-100"
            />
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                checked={manualWithoutGst}
                onChange={(e) => {
                  const enabled = e.target.checked;
                  setManualWithoutGst(enabled);
                  setGstData(null);
                  setLastLookedUpGstin('');
                  if (enabled) {
                    setForm((prev) => ({ ...prev, gstin: '' }));
                  }
                }}
              />
              No GST available, continue with manual company details
            </label>
            {isCheckingGST && (
              <p className="mt-1 text-xs text-blue-700">Fetching GST details and auto-filling company fields...</p>
            )}
          </div>

          <div className="lg:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
            <input
              type="text"
              value={form.company_name}
              onChange={(e) => setForm((prev) => ({ ...prev, company_name: e.target.value }))}
              placeholder="Enter company name"
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required={manualWithoutGst}
            />
            {gstData && getCompanyNameFromGst(gstData) && (
              <p className="mt-1 text-xs text-green-700">Auto-filled from GST</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Business Address</label>
            <input
              type="text"
              value={form.business_address}
              onChange={(e) => setForm((prev) => ({ ...prev, business_address: e.target.value }))}
              placeholder="Auto-filled from GST"
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Loan Type</label>
            <select
              value={form.loan_type}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  loan_type: e.target.value,
                  monthly_income_or_turnover: e.target.value === 'BL' ? 12 : 50000,
                  entity_type_or_employer: e.target.value === 'BL' ? 'proprietorship' : 'self_employed',
                }))
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              <option value="BL">Business Loan (BL)</option>
              <option value="PL">Personal Loan (PL)</option>
              <option value="HL">Home Loan (HL)</option>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">{monthlyFieldLabel}</label>
            <input
              type="number"
              min="0"
              step={isBusinessLoan ? '0.1' : '1000'}
              value={form.monthly_income_or_turnover}
              onChange={(e) => setForm((prev) => ({ ...prev, monthly_income_or_turnover: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              {isBusinessLoan
                ? 'Use monthly turnover in Lakhs (example: 12 = ₹12L/month).'
                : 'Use monthly net income in INR (example: 50000).'}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{vintageFieldLabel}</label>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">{profileFieldLabel}</label>
            <select
              value={form.entity_type_or_employer}
              onChange={(e) => setForm((prev) => ({ ...prev, entity_type_or_employer: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              {isBusinessLoan ? (
                <>
                  <option value="proprietorship">Proprietorship</option>
                  <option value="partnership">Partnership</option>
                  <option value="llp">LLP</option>
                  <option value="pvt_ltd">Private Limited</option>
                </>
              ) : (
                <>
                  <option value="salaried">Salaried</option>
                  <option value="self_employed">Self-employed</option>
                </>
              )}
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
                setGstData(null);
                setManualWithoutGst(false);
                setLastLookedUpGstin('');
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
