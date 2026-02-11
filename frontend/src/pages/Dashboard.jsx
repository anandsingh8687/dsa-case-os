import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { getCases } from '../api/services';
import { Card, Button, Badge, Loading, ProgressBar } from '../components/ui';
import { CASE_STATUSES } from '../utils/constants';
import { formatDate, formatPercentage } from '../utils/format';

const Dashboard = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');

  const { data: casesData, isLoading, error } = useQuery({
    queryKey: ['cases'],
    queryFn: () => getCases(),
    retry: 2,
    retryDelay: 1000,
  });

  const cases = casesData?.data?.cases || [];

  const filteredCases = cases.filter((caseItem) =>
    caseItem.borrower_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const stats = {
    total: cases.length,
    avgCompleteness:
      cases.length > 0
        ? cases.reduce((sum, c) => sum + (c.completeness_percentage || 0), 0) /
          cases.length
        : 0,
    completed: cases.filter((c) => c.status === 'report_generated').length,
    processing: cases.filter((c) => c.status === 'processing').length,
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loading size="lg" text="Loading cases..." />
      </div>
    );
  }

  // Show error state but allow user to continue using the app
  if (error) {
    console.error('Dashboard API error:', error);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <Button
          onClick={() => navigate('/cases/new')}
          variant="primary"
          className="flex items-center gap-2"
        >
          <Plus className="w-5 h-5" />
          New Case
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <div className="text-sm text-gray-600">Total Cases</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">
            {stats.total}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Avg Completeness</div>
          <div className="text-3xl font-bold text-primary mt-1">
            {formatPercentage(stats.avgCompleteness)}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Completed</div>
          <div className="text-3xl font-bold text-green-600 mt-1">
            {stats.completed}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Processing</div>
          <div className="text-3xl font-bold text-yellow-600 mt-1">
            {stats.processing}
          </div>
        </Card>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="Search by borrower name..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      {/* Cases Grid */}
      {filteredCases.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">
              {searchTerm ? 'No cases found.' : 'No cases yet. Create your first case!'}
            </p>
            {!searchTerm && (
              <Button onClick={() => navigate('/cases/new')} variant="primary">
                Create Case
              </Button>
            )}
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredCases.map((caseItem) => {
            const statusInfo =
              CASE_STATUSES[caseItem.status] || CASE_STATUSES.created;

            return (
              <Card
                key={caseItem.case_id}
                hover
                onClick={() => navigate(`/cases/${caseItem.case_id}`)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold text-gray-900">
                      {caseItem.borrower_name || 'Unnamed'}
                    </h3>
                    <p className="text-sm text-gray-600">
                      {caseItem.case_id?.substring(0, 8)}...
                    </p>
                  </div>
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
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Entity:</span>
                    <span className="font-medium">
                      {caseItem.entity_type || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Program:</span>
                    <span className="font-medium">
                      {caseItem.program_type || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Created:</span>
                    <span className="font-medium">
                      {formatDate(caseItem.created_at)}
                    </span>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600">Completeness</span>
                    <span className="font-medium">
                      {formatPercentage(caseItem.completeness_percentage)}
                    </span>
                  </div>
                  <ProgressBar
                    value={caseItem.completeness_percentage || 0}
                    max={100}
                  />
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
