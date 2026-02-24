import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus, Search, Trash2, Sparkles } from 'lucide-react';
import { getCases, deleteCase, smartCaseSearch } from '../api/services';
import { Card, Button, ActionButton, IconButton, Badge, Loading, ProgressBar } from '../components/ui';
import { CASE_STATUSES } from '../utils/constants';
import { formatDate, formatPercentage } from '../utils/format';

const Dashboard = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [showSlowLoadingHint, setShowSlowLoadingHint] = useState(false);

  const withHardTimeout = (promise, timeoutMs = 20000) =>
    new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error('Dashboard request timed out')), timeoutMs);
      promise
        .then((value) => {
          window.clearTimeout(timer);
          resolve(value);
        })
        .catch((err) => {
          window.clearTimeout(timer);
          reject(err);
        });
    });

  const { data: casesData, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['cases'],
    queryFn: () => withHardTimeout(getCases(), 20000),
    retry: 1,
    retryDelay: 1000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    const term = searchTerm.trim();
    const timer = window.setTimeout(() => setDebouncedSearchTerm(term), 350);
    return () => window.clearTimeout(timer);
  }, [searchTerm]);

  const hasSmartSearch = debouncedSearchTerm.length >= 2;

  const {
    data: smartSearchData,
    isFetching: isSmartSearching,
    error: smartSearchError,
  } = useQuery({
    queryKey: ['cases-smart-search', debouncedSearchTerm],
    queryFn: () => withHardTimeout(smartCaseSearch(debouncedSearchTerm), 20000),
    enabled: hasSmartSearch,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!isLoading) {
      setShowSlowLoadingHint(false);
      return undefined;
    }

    const timer = window.setTimeout(() => {
      setShowSlowLoadingHint(true);
    }, 12000);

    return () => window.clearTimeout(timer);
  }, [isLoading]);

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId) => deleteCase(caseId),
    onSuccess: () => {
      toast.success('Case deleted');
      queryClient.invalidateQueries({ queryKey: ['cases'] });
      if (hasSmartSearch) {
        queryClient.invalidateQueries({ queryKey: ['cases-smart-search', debouncedSearchTerm] });
      }
    },
    onError: (apiError) => {
      toast.error(apiError.response?.data?.detail || 'Failed to delete case');
    },
  });

  const cases = Array.isArray(casesData?.data) ? casesData.data : [];
  const smartPayload = smartSearchData?.data || null;
  const smartMatches = Array.isArray(smartPayload?.matches) ? smartPayload.matches : [];
  const displayedCases = hasSmartSearch ? smartMatches : cases;
  const quickView = smartPayload?.quick_view || null;

  const stats = {
    total: cases.length,
    avgCompleteness:
      cases.length > 0
        ? cases.reduce((sum, c) => sum + (c.completeness_score || 0), 0) / cases.length
        : 0,
    completed: cases.filter((c) => c.status === 'report_generated').length,
    processing: cases.filter((c) => c.status === 'processing').length,
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <Loading size="lg" text="Loading cases..." />
        {showSlowLoadingHint && (
          <div className="max-w-md rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 text-center">
            Dashboard is taking longer than usual because heavy processing may be running.
            <div className="mt-3">
              <Button size="sm" variant="outline" onClick={() => refetch()}>
                Retry Dashboard Load
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <ActionButton onClick={() => navigate('/cases/new')} variant="primary" icon={Plus}>
          New Case
        </ActionButton>
      </div>

      {(error || smartSearchError) && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Could not load latest dashboard data right now. Please retry.
          <button type="button" className="ml-2 underline font-medium" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}

      {(isFetching || isSmartSearching) && (
        <div className="mb-4 text-xs text-gray-500">
          {hasSmartSearch ? 'Running smart checks (GST, PAN duplicate, eligibility pre-score)...' : 'Refreshing latest cases...'}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <div className="text-sm text-gray-600">Total Cases</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">{stats.total}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Avg Completeness</div>
          <div className="text-3xl font-bold text-primary mt-1">{formatPercentage(stats.avgCompleteness)}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Completed</div>
          <div className="text-3xl font-bold text-green-600 mt-1">{stats.completed}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Processing</div>
          <div className="text-3xl font-bold text-yellow-600 mt-1">{stats.processing}</div>
        </Card>
      </div>

      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="Search Company / GST / Case ID / PAN / Phone..."
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        {hasSmartSearch && smartPayload?.detected_type && (
          <p className="mt-2 text-xs text-blue-700">
            Search type detected: <span className="font-semibold">{String(smartPayload.detected_type).toUpperCase()}</span>
          </p>
        )}
      </div>

      {hasSmartSearch && quickView && (
        <Card className="mb-6 border-blue-200 bg-blue-50">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-blue-900 font-semibold">
                <Sparkles className="w-4 h-4" />
                Quick View
              </div>
              <h3 className="mt-2 text-lg font-bold text-gray-900">
                {quickView.company_name || 'Company'}
              </h3>
              <p className="text-sm text-gray-700 mt-1">
                {quickView.case_id} • {quickView.gstin || 'GST pending'} • {quickView.pan_number || 'PAN pending'}
              </p>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                <div className="rounded-md bg-white px-3 py-2 border border-blue-100">
                  GST Validation: {quickView?.gst_validation?.is_valid_format ? 'Valid' : 'Pending'}
                </div>
                <div className="rounded-md bg-white px-3 py-2 border border-blue-100">
                  Duplicate PAN: {quickView?.duplicate_pan?.has_duplicates ? `Yes (${quickView.duplicate_pan.count})` : 'No'}
                </div>
                <div className="rounded-md bg-white px-3 py-2 border border-blue-100">
                  Pre-Score: {quickView?.eligibility_pre_score?.score ?? 'N/A'} ({quickView?.eligibility_pre_score?.band || 'N/A'})
                </div>
              </div>
            </div>
            <Button variant="primary" onClick={() => navigate(`/cases/${quickView.case_id}`)}>
              Open Full Profile
            </Button>
          </div>
          {Array.isArray(quickView.insights) && quickView.insights.length > 0 && (
            <ul className="mt-3 text-sm text-gray-700 space-y-1">
              {quickView.insights.map((insight, idx) => (
                <li key={`insight-${idx}`}>• {insight}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {displayedCases.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">
              {hasSmartSearch ? 'No matching cases found for this smart search.' : 'No cases yet. Create your first case!'}
            </p>
            {!hasSmartSearch && (
              <Button onClick={() => navigate('/cases/new')} variant="primary">
                Create Case
              </Button>
            )}
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayedCases.map((caseItem) => {
            const statusInfo = CASE_STATUSES[caseItem.status] || CASE_STATUSES.created;
            return (
              <Card key={caseItem.case_id}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold text-gray-900">{caseItem.borrower_name || 'Unnamed Company'}</h3>
                    <p className="text-sm text-gray-600">{caseItem.case_id?.substring(0, 12)}...</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        caseItem.status === 'report_generated'
                          ? 'success'
                          : caseItem.status === 'processing'
                            ? 'warning'
                            : caseItem.status === 'failed'
                              ? 'danger'
                              : 'default'
                      }
                    >
                      {statusInfo.label}
                    </Badge>
                    <IconButton
                      variant="danger"
                      title={`Delete ${caseItem.case_id}`}
                      label={`Delete ${caseItem.case_id}`}
                      icon={Trash2}
                      size="sm"
                      disabled={deleteCaseMutation.isPending}
                      onClick={(event) => {
                        event.stopPropagation();
                        const confirmed = window.confirm(`Delete case ${caseItem.case_id}? This cannot be undone.`);
                        if (!confirmed) return;
                        deleteCaseMutation.mutate(caseItem.case_id);
                      }}
                    />
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Entity:</span>
                    <span className="font-medium">{caseItem.entity_type || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Program:</span>
                    <span className="font-medium">{caseItem.program_type || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Created:</span>
                    <span className="font-medium">{formatDate(caseItem.created_at)}</span>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600">Completeness</span>
                    <span className="font-medium">{formatPercentage(caseItem.completeness_score)}</span>
                  </div>
                  <ProgressBar value={caseItem.completeness_score || 0} max={100} />
                </div>

                <div className="mt-4">
                  <ActionButton
                    size="sm"
                    variant="primary"
                    className="w-full"
                    onClick={() => navigate(`/cases/${caseItem.case_id}`)}
                  >
                    Open Full Profile
                  </ActionButton>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Dashboard;
