import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Calculator, Plus, Trash2, Wallet } from 'lucide-react';

import {
  getCases,
  getCommissionOverview,
  getCommissionRates,
  upsertCommissionRate,
  deleteCommissionRate,
  calculateCommission,
  upsertCommissionPayout,
  getCommissionPayouts,
} from '../api/services';
import { Badge, Button, Card, Loading } from '../components/ui';
import { formatCurrency } from '../utils/format';

const LOAN_TYPES = ['BL', 'PL', 'HL', 'LAP'];
const PAYOUT_STATUSES = ['pending', 'received', 'overdue'];

const getStatusBadge = (status) => {
  if (status === 'received') return 'success';
  if (status === 'overdue') return 'danger';
  return 'warning';
};

const Commission = () => {
  const queryClient = useQueryClient();

  const [rateForm, setRateForm] = useState({
    lender_name: '',
    loan_type: 'BL',
    commission_pct: '',
    notes: '',
  });

  const [calcForm, setCalcForm] = useState({
    case_id: '',
    lender_name: '',
    loan_type: 'BL',
    disbursed_amount: '',
    disbursement_date: new Date().toISOString().slice(0, 10),
    expected_payout_date: '',
    actual_payout_date: '',
    payout_status: 'pending',
  });

  const [calculationPreview, setCalculationPreview] = useState(null);

  const { data: overviewData, isLoading: overviewLoading } = useQuery({
    queryKey: ['commission-overview'],
    queryFn: getCommissionOverview,
  });

  const { data: ratesData, isLoading: ratesLoading } = useQuery({
    queryKey: ['commission-rates'],
    queryFn: getCommissionRates,
  });

  const { data: payoutsData, isLoading: payoutsLoading } = useQuery({
    queryKey: ['commission-payouts'],
    queryFn: () => getCommissionPayouts({ limit: 100 }),
  });

  const { data: casesData } = useQuery({
    queryKey: ['cases-for-commission'],
    queryFn: getCases,
  });

  const rates = ratesData?.data?.rates || [];
  const payouts = payoutsData?.data?.payouts || [];
  const overview = overviewData?.data || {};
  const summary = overview.summary || {};
  const monthlyTrend = Array.isArray(overview.monthly_trend) ? overview.monthly_trend : [];
  const cases = Array.isArray(casesData?.data) ? casesData.data : [];

  const lenderOptions = useMemo(() => {
    const known = new Set();
    const list = [];

    rates.forEach((rate) => {
      const value = String(rate.lender_name || '').trim();
      if (value && !known.has(value.toLowerCase())) {
        known.add(value.toLowerCase());
        list.push(value);
      }
    });

    payouts.forEach((payout) => {
      const value = String(payout.lender_name || '').trim();
      if (value && !known.has(value.toLowerCase())) {
        known.add(value.toLowerCase());
        list.push(value);
      }
    });

    return list.sort((a, b) => a.localeCompare(b));
  }, [rates, payouts]);

  const saveRateMutation = useMutation({
    mutationFn: upsertCommissionRate,
    onSuccess: () => {
      toast.success('Commission rate saved');
      setRateForm({ lender_name: '', loan_type: 'BL', commission_pct: '', notes: '' });
      queryClient.invalidateQueries({ queryKey: ['commission-rates'] });
      queryClient.invalidateQueries({ queryKey: ['commission-overview'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to save commission rate');
    },
  });

  const deleteRateMutation = useMutation({
    mutationFn: deleteCommissionRate,
    onSuccess: () => {
      toast.success('Commission rate removed');
      queryClient.invalidateQueries({ queryKey: ['commission-rates'] });
      queryClient.invalidateQueries({ queryKey: ['commission-overview'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to remove commission rate');
    },
  });

  const calculateMutation = useMutation({
    mutationFn: calculateCommission,
    onSuccess: (response) => {
      setCalculationPreview(response.data);
      toast.success('Commission calculated');
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to calculate commission');
    },
  });

  const savePayoutMutation = useMutation({
    mutationFn: upsertCommissionPayout,
    onSuccess: () => {
      toast.success('Payout record saved');
      queryClient.invalidateQueries({ queryKey: ['commission-payouts'] });
      queryClient.invalidateQueries({ queryKey: ['commission-overview'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to save payout record');
    },
  });

  const onSaveRate = (event) => {
    event.preventDefault();
    saveRateMutation.mutate({
      lender_name: rateForm.lender_name.trim(),
      loan_type: rateForm.loan_type,
      commission_pct: Number(rateForm.commission_pct),
      notes: rateForm.notes.trim() || null,
    });
  };

  const onCalculate = (event) => {
    event.preventDefault();
    calculateMutation.mutate({
      lender_name: calcForm.lender_name.trim(),
      loan_type: calcForm.loan_type,
      disbursed_amount: Number(calcForm.disbursed_amount),
    });
  };

  const onSavePayout = () => {
    if (!calcForm.case_id) {
      toast.error('Select a case ID to save payout');
      return;
    }

    savePayoutMutation.mutate({
      case_id: calcForm.case_id,
      lender_name: calcForm.lender_name.trim(),
      loan_type: calcForm.loan_type,
      disbursed_amount: Number(calcForm.disbursed_amount),
      disbursement_date: calcForm.disbursement_date,
      expected_payout_date: calcForm.expected_payout_date || null,
      actual_payout_date: calcForm.actual_payout_date || null,
      payout_status: calcForm.payout_status,
    });
  };

  if (overviewLoading || ratesLoading || payoutsLoading) {
    return <Loading text="Loading commission workspace..." />;
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Commission Calculator</h1>
            <p className="text-sm text-gray-600 mt-1">
              Manage lender-wise commission rates, compute expected payouts, and track collections.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 border border-gray-200">
            <Wallet className="w-4 h-4 text-primary" />
            <span className="text-sm text-gray-700">Rates configured: {overview.rate_count || 0}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
          <div className="rounded-lg border border-green-200 bg-green-50 p-3">
            <p className="text-xs uppercase text-green-700">Received</p>
            <p className="text-xl font-bold text-green-900 mt-1">{formatCurrency(summary.total_received)}</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs uppercase text-amber-700">Pending</p>
            <p className="text-xl font-bold text-amber-900 mt-1">{formatCurrency(summary.pending_amount)}</p>
          </div>
          <div className="rounded-lg border border-red-200 bg-red-50 p-3">
            <p className="text-xs uppercase text-red-700">Overdue</p>
            <p className="text-xl font-bold text-red-900 mt-1">{formatCurrency(summary.overdue_amount)}</p>
          </div>
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
            <p className="text-xs uppercase text-blue-700">Projected Total</p>
            <p className="text-xl font-bold text-blue-900 mt-1">{formatCurrency(summary.projected_total)}</p>
          </div>
        </div>

        {monthlyTrend.length > 0 && (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-gray-800 mb-2">Recent Monthly Trend</h3>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
              {monthlyTrend.map((row) => (
                <div key={row.month} className="rounded border border-gray-200 px-2 py-2 bg-white">
                  <p className="text-xs text-gray-500">{row.month}</p>
                  <p className="text-sm font-semibold text-gray-900">{formatCurrency(row.amount)}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Commission Rate Master</h2>
          <form onSubmit={onSaveRate} className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Lender Name</label>
              <input
                required
                value={rateForm.lender_name}
                onChange={(e) => setRateForm((prev) => ({ ...prev, lender_name: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="e.g., Tata Capital"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Loan Type</label>
                <select
                  value={rateForm.loan_type}
                  onChange={(e) => setRateForm((prev) => ({ ...prev, loan_type: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  {LOAN_TYPES.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">Commission %</label>
                <input
                  required
                  type="number"
                  min="0.01"
                  max="100"
                  step="0.01"
                  value={rateForm.commission_pct}
                  onChange={(e) => setRateForm((prev) => ({ ...prev, commission_pct: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">Notes</label>
              <input
                value={rateForm.notes}
                onChange={(e) => setRateForm((prev) => ({ ...prev, notes: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Optional channel agreement notes"
              />
            </div>

            <Button type="submit" disabled={saveRateMutation.isPending} className="flex items-center gap-2">
              <Plus className="w-4 h-4" />
              {saveRateMutation.isPending ? 'Saving...' : 'Save Rate'}
            </Button>
          </form>

          <div className="mt-5 overflow-x-auto border border-gray-200 rounded-lg">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Rate</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {rates.map((rate) => (
                  <tr key={rate.id}>
                    <td className="px-3 py-2 font-medium text-gray-900">{rate.lender_name}</td>
                    <td className="px-3 py-2 text-gray-700">{rate.loan_type}</td>
                    <td className="px-3 py-2 text-gray-700">{rate.commission_pct}%</td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        className="text-red-600 hover:text-red-700"
                        onClick={() => deleteRateMutation.mutate(rate.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {rates.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-gray-500">No commission rates configured yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Commission Estimator + Payout Save</h2>
          <form onSubmit={onCalculate} className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Case ID</label>
              <select
                value={calcForm.case_id}
                onChange={(e) => setCalcForm((prev) => ({ ...prev, case_id: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="">Select case (optional for calculate, required for save)</option>
                {cases.map((item) => (
                  <option key={item.id} value={item.case_id}>
                    {item.case_id} {item.borrower_name ? `• ${item.borrower_name}` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">Lender Name</label>
              <input
                list="commission-lenders"
                required
                value={calcForm.lender_name}
                onChange={(e) => setCalcForm((prev) => ({ ...prev, lender_name: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Use same lender name as rate master"
              />
              <datalist id="commission-lenders">
                {lenderOptions.map((lender) => (
                  <option key={lender} value={lender} />
                ))}
              </datalist>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Loan Type</label>
                <select
                  value={calcForm.loan_type}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, loan_type: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  {LOAN_TYPES.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Disbursed Amount (₹)</label>
                <input
                  type="number"
                  min="1"
                  required
                  value={calcForm.disbursed_amount}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, disbursed_amount: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Disbursement Date</label>
                <input
                  type="date"
                  required
                  value={calcForm.disbursement_date}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, disbursement_date: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Expected Payout Date</label>
                <input
                  type="date"
                  value={calcForm.expected_payout_date}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, expected_payout_date: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Actual Payout Date</label>
                <input
                  type="date"
                  value={calcForm.actual_payout_date}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, actual_payout_date: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Payout Status</label>
                <select
                  value={calcForm.payout_status}
                  onChange={(e) => setCalcForm((prev) => ({ ...prev, payout_status: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  {PAYOUT_STATUSES.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2">
              <Button type="submit" disabled={calculateMutation.isPending} className="flex items-center gap-2">
                <Calculator className="w-4 h-4" />
                {calculateMutation.isPending ? 'Calculating...' : 'Calculate'}
              </Button>
              <Button
                type="button"
                variant="success"
                disabled={savePayoutMutation.isPending}
                onClick={onSavePayout}
              >
                {savePayoutMutation.isPending ? 'Saving...' : 'Save Payout Record'}
              </Button>
            </div>
          </form>

          {calculationPreview && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm">
              <p className="text-gray-700">Lender: <span className="font-medium">{calculationPreview.lender_name}</span></p>
              <p className="text-gray-700">Commission %: <span className="font-medium">{calculationPreview.commission_pct}%</span></p>
              <p className="text-blue-900 font-semibold mt-2">
                Estimated Commission: {formatCurrency(calculationPreview.commission_amount)}
              </p>
            </div>
          )}
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Payout Ledger</h2>
        <div className="overflow-x-auto border border-gray-200 rounded-lg">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Case</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Disbursed</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Rate</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Commission</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {payouts.map((payout) => (
                <tr key={payout.id}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">{payout.case_id}</div>
                    {payout.borrower_name && <div className="text-xs text-gray-500">{payout.borrower_name}</div>}
                  </td>
                  <td className="px-3 py-2 text-gray-700">{payout.lender_name || 'N/A'}</td>
                  <td className="px-3 py-2 text-gray-700">{formatCurrency(payout.disbursed_amount)}</td>
                  <td className="px-3 py-2 text-gray-700">{payout.commission_pct || 0}%</td>
                  <td className="px-3 py-2 font-semibold text-gray-900">{formatCurrency(payout.commission_amount)}</td>
                  <td className="px-3 py-2">
                    <Badge variant={getStatusBadge(payout.payout_status)}>
                      {(payout.payout_status || 'pending').toUpperCase()}
                    </Badge>
                  </td>
                </tr>
              ))}
              {payouts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-gray-500">No payout records yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export default Commission;
