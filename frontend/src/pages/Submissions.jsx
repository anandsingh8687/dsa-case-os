import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import {
  getSubmissions,
  getCaseSubmissions,
  createCaseSubmission,
  updateSubmission,
  addSubmissionQuery,
  updateSubmissionQuery,
} from '../api/services';
import { Badge, Button, Card, Loading, Modal } from '../components/ui';
import { formatCurrency } from '../utils/format';

const STAGES = [
  'submitted',
  'query_raised',
  'sanctioned',
  'disbursed',
  'rejected',
  'dropped',
];

const QUERY_STATUS = ['open', 'resolved', 'ignored'];

const stageVariant = (stage) => {
  if (stage === 'disbursed' || stage === 'sanctioned') return 'success';
  if (stage === 'query_raised') return 'warning';
  if (stage === 'rejected' || stage === 'dropped') return 'danger';
  return 'default';
};

const Submissions = () => {
  const queryClient = useQueryClient();
  const [stageFilter, setStageFilter] = useState('');
  const [selectedSubmission, setSelectedSubmission] = useState(null);
  const [createForm, setCreateForm] = useState({
    case_id: '',
    lender_name: '',
    product_type: 'BL',
    notes: '',
  });
  const [queryForm, setQueryForm] = useState({
    query_text: '',
    status: 'open',
  });

  const { data: submissionsData, isLoading } = useQuery({
    queryKey: ['submissions', stageFilter],
    queryFn: () => getSubmissions({ stage: stageFilter || undefined, limit: 300 }),
  });

  const { data: caseSubmissionData, isLoading: caseSubmissionLoading } = useQuery({
    queryKey: ['case-submissions', selectedSubmission?.case_id],
    queryFn: () => getCaseSubmissions(selectedSubmission.case_id),
    enabled: !!selectedSubmission?.case_id,
  });

  const createSubmissionMutation = useMutation({
    mutationFn: ({ caseId, payload }) => createCaseSubmission(caseId, payload),
    onSuccess: () => {
      toast.success('Submission added');
      setCreateForm({ case_id: '', lender_name: '', product_type: 'BL', notes: '' });
      queryClient.invalidateQueries({ queryKey: ['submissions'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to add submission');
    },
  });

  const updateSubmissionMutation = useMutation({
    mutationFn: ({ submissionId, payload }) => updateSubmission(submissionId, payload),
    onSuccess: () => {
      toast.success('Submission updated');
      queryClient.invalidateQueries({ queryKey: ['submissions'] });
      queryClient.invalidateQueries({ queryKey: ['case-submissions', selectedSubmission?.case_id] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to update submission');
    },
  });

  const addQueryMutation = useMutation({
    mutationFn: ({ submissionId, payload }) => addSubmissionQuery(submissionId, payload),
    onSuccess: () => {
      toast.success('Query added');
      setQueryForm({ query_text: '', status: 'open' });
      queryClient.invalidateQueries({ queryKey: ['submissions'] });
      queryClient.invalidateQueries({ queryKey: ['case-submissions', selectedSubmission?.case_id] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to add query');
    },
  });

  const updateQueryMutation = useMutation({
    mutationFn: ({ queryId, payload }) => updateSubmissionQuery(queryId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case-submissions', selectedSubmission?.case_id] });
      queryClient.invalidateQueries({ queryKey: ['submissions'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to update query');
    },
  });

  const submissions = submissionsData?.data?.submissions || [];
  const caseSubmissions = caseSubmissionData?.data?.submissions || [];
  const caseQueries = caseSubmissionData?.data?.queries || [];

  const selectedSubmissionDetails = useMemo(() => {
    if (!selectedSubmission) return null;
    return caseSubmissions.find((item) => item.id === selectedSubmission.id) || selectedSubmission;
  }, [caseSubmissions, selectedSubmission]);

  const selectedQueries = useMemo(() => {
    if (!selectedSubmission) return [];
    return caseQueries.filter((item) => item.submission_id === selectedSubmission.id);
  }, [caseQueries, selectedSubmission]);

  if (isLoading) return <Loading text="Loading submissions..." />;

  return (
    <div className="space-y-6">
      <Card>
        <h1 className="text-2xl font-bold text-gray-900">Lender Submission Tracker</h1>
        <p className="text-sm text-gray-600 mt-1">
          Track every lender submission, sanction/disbursal updates, and lender queries.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-5">
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
          >
            <option value="">All stages</option>
            {STAGES.map((stage) => (
              <option key={stage} value={stage}>{stage}</option>
            ))}
          </select>
          <div className="text-sm text-gray-600 rounded-lg border border-gray-200 px-3 py-2 bg-gray-50">
            Active rows: <span className="font-semibold text-gray-900">{submissions.length}</span>
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Add Lender Submission</h2>
        <form
          className="grid grid-cols-1 md:grid-cols-4 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            createSubmissionMutation.mutate({
              caseId: createForm.case_id.trim(),
              payload: {
                lender_name: createForm.lender_name.trim(),
                product_type: createForm.product_type,
                notes: createForm.notes || null,
              },
            });
          }}
        >
          <input
            required
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Case ID (e.g. CASE-20260215-0011)"
            value={createForm.case_id}
            onChange={(e) => setCreateForm((prev) => ({ ...prev, case_id: e.target.value }))}
          />
          <input
            required
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Lender name"
            value={createForm.lender_name}
            onChange={(e) => setCreateForm((prev) => ({ ...prev, lender_name: e.target.value }))}
          />
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={createForm.product_type}
            onChange={(e) => setCreateForm((prev) => ({ ...prev, product_type: e.target.value }))}
          >
            <option value="BL">BL</option>
            <option value="PL">PL</option>
            <option value="HL">HL</option>
            <option value="LAP">LAP</option>
          </select>
          <Button type="submit" disabled={createSubmissionMutation.isPending}>
            {createSubmissionMutation.isPending ? 'Adding...' : 'Add Submission'}
          </Button>
          <textarea
            className="md:col-span-4 border border-gray-300 rounded-lg px-3 py-2 text-sm"
            rows={2}
            placeholder="Notes (optional)"
            value={createForm.notes}
            onChange={(e) => setCreateForm((prev) => ({ ...prev, notes: e.target.value }))}
          />
        </form>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Submission Pipeline</h2>
        <div className="overflow-x-auto border border-gray-200 rounded-lg">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Case</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Lender</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Stage</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Amounts</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Updated</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {submissions.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">{item.case_id}</div>
                    <div className="text-xs text-gray-500">{item.borrower_name || 'Borrower not set'}</div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    <div className="font-medium text-gray-900">{item.lender_name}</div>
                    <div className="text-xs text-gray-500">{item.product_type || 'N/A'}</div>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={stageVariant(item.stage)}>{item.stage}</Badge>
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    <div className="text-xs">Sanctioned: {formatCurrency(item.sanctioned_amount)}</div>
                    <div className="text-xs">Disbursed: {formatCurrency(item.disbursed_amount)}</div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{item.updated_at || '—'}</td>
                  <td className="px-3 py-2">
                    <Button size="sm" variant="outline" onClick={() => setSelectedSubmission(item)}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
              {submissions.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-gray-500">No submissions found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        isOpen={!!selectedSubmission}
        onClose={() => setSelectedSubmission(null)}
        title={selectedSubmission ? `Submission • ${selectedSubmission.lender_name}` : 'Submission'}
        size="lg"
      >
        {!selectedSubmission ? null : (
          <div className="space-y-5">
            {caseSubmissionLoading ? (
              <Loading text="Loading submission details..." />
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <span className="text-gray-500">Case ID:</span>{' '}
                    <span className="font-medium text-gray-900">{selectedSubmission.case_id}</span>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <span className="text-gray-500">Lender:</span>{' '}
                    <span className="font-medium text-gray-900">{selectedSubmission.lender_name}</span>
                  </div>
                </div>

                <form
                  className="grid grid-cols-1 md:grid-cols-4 gap-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const form = new FormData(e.currentTarget);
                    updateSubmissionMutation.mutate({
                      submissionId: selectedSubmission.id,
                      payload: {
                        stage: String(form.get('stage')),
                        sanctioned_amount: form.get('sanctioned_amount')
                          ? Number(form.get('sanctioned_amount'))
                          : null,
                        disbursed_amount: form.get('disbursed_amount')
                          ? Number(form.get('disbursed_amount'))
                          : null,
                        rejection_reason: String(form.get('rejection_reason') || '') || null,
                        notes: String(form.get('notes') || '') || null,
                      },
                    });
                  }}
                >
                  <select
                    name="stage"
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    defaultValue={selectedSubmissionDetails?.stage || 'submitted'}
                  >
                    {STAGES.map((stage) => (
                      <option key={stage} value={stage}>{stage}</option>
                    ))}
                  </select>
                  <input
                    name="sanctioned_amount"
                    type="number"
                    min="0"
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="Sanctioned amount"
                    defaultValue={selectedSubmissionDetails?.sanctioned_amount || ''}
                  />
                  <input
                    name="disbursed_amount"
                    type="number"
                    min="0"
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="Disbursed amount"
                    defaultValue={selectedSubmissionDetails?.disbursed_amount || ''}
                  />
                  <Button type="submit" disabled={updateSubmissionMutation.isPending}>
                    {updateSubmissionMutation.isPending ? 'Saving...' : 'Update'}
                  </Button>
                  <input
                    name="rejection_reason"
                    className="md:col-span-2 border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="Rejection reason (if any)"
                    defaultValue={selectedSubmissionDetails?.rejection_reason || ''}
                  />
                  <input
                    name="notes"
                    className="md:col-span-2 border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="Notes"
                    defaultValue={selectedSubmissionDetails?.notes || ''}
                  />
                </form>

                <div className="border-t pt-4">
                  <h3 className="font-semibold text-gray-900 mb-3">Lender Queries</h3>
                  <form
                    className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4"
                    onSubmit={(e) => {
                      e.preventDefault();
                      addQueryMutation.mutate({
                        submissionId: selectedSubmission.id,
                        payload: {
                          query_text: queryForm.query_text,
                          status: queryForm.status,
                        },
                      });
                    }}
                  >
                    <input
                      required
                      className="md:col-span-3 border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      placeholder="Query raised by lender"
                      value={queryForm.query_text}
                      onChange={(e) => setQueryForm((prev) => ({ ...prev, query_text: e.target.value }))}
                    />
                    <div className="flex gap-2">
                      <select
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        value={queryForm.status}
                        onChange={(e) => setQueryForm((prev) => ({ ...prev, status: e.target.value }))}
                      >
                        {QUERY_STATUS.map((status) => (
                          <option key={status} value={status}>{status}</option>
                        ))}
                      </select>
                      <Button type="submit" disabled={addQueryMutation.isPending}>
                        {addQueryMutation.isPending ? 'Adding...' : 'Add'}
                      </Button>
                    </div>
                  </form>

                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Query</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Response</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-100">
                        {selectedQueries.map((item) => (
                          <tr key={item.id}>
                            <td className="px-3 py-2 text-gray-700">{item.query_text}</td>
                            <td className="px-3 py-2">
                              <select
                                className="border border-gray-300 rounded px-2 py-1 text-xs"
                                value={item.status}
                                onChange={(e) =>
                                  updateQueryMutation.mutate({
                                    queryId: item.id,
                                    payload: { status: e.target.value },
                                  })
                                }
                              >
                                {QUERY_STATUS.map((status) => (
                                  <option key={status} value={status}>{status}</option>
                                ))}
                              </select>
                            </td>
                            <td className="px-3 py-2 text-gray-600">{item.response_text || '—'}</td>
                          </tr>
                        ))}
                        {selectedQueries.length === 0 && (
                          <tr>
                            <td colSpan={3} className="px-3 py-4 text-center text-gray-500">
                              No lender queries for this submission.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Submissions;
