import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, Users, Briefcase, Activity, AlertTriangle } from 'lucide-react';

import {
  getAdminStats,
  getAdminUsers,
  getAdminCases,
  getAdminLogs,
  getAdminHealth,
} from '../api/services';
import { Card, Loading, Badge } from '../components/ui';
import { formatDate, formatPercentage } from '../utils/format';

const AdminPanel = () => {
  const [searchUser, setSearchUser] = useState('');

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: getAdminStats,
    retry: 1,
  });

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ['admin-users', searchUser],
    queryFn: () => getAdminUsers({ q: searchUser || undefined, limit: 50 }),
    retry: 1,
  });

  const { data: casesData, isLoading: casesLoading } = useQuery({
    queryKey: ['admin-cases'],
    queryFn: () => getAdminCases({ limit: 50 }),
    retry: 1,
  });

  const { data: logsData } = useQuery({
    queryKey: ['admin-logs'],
    queryFn: () => getAdminLogs({ days: 7 }),
    retry: 1,
  });

  const { data: healthData } = useQuery({
    queryKey: ['admin-health'],
    queryFn: getAdminHealth,
    retry: 1,
    refetchInterval: 30000,
  });

  const stats = statsData?.data;
  const users = usersData?.data || [];
  const cases = casesData?.data || [];
  const logs = logsData?.data || {};
  const health = healthData?.data;

  const topStatuses = useMemo(() => {
    const distribution = stats?.status_distribution || {};
    return Object.entries(distribution)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 6);
  }, [stats]);

  if (statsLoading) {
    return <Loading size="lg" text="Loading admin analytics..." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Admin Control Panel</h1>
          <p className="text-sm text-gray-600 mt-1">Cross-platform operational visibility and health checks.</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <ShieldCheck className="w-4 h-4 text-green-600" />
          <span className="text-gray-700">Role-gated admin access</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <div className="text-sm text-gray-600">Users</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">{stats?.users_total || 0}</div>
          <div className="text-xs text-gray-500 mt-1">Active: {stats?.users_active || 0}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Cases</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">{stats?.cases_total || 0}</div>
          <div className="text-xs text-gray-500 mt-1">Last 24h: {stats?.cases_created_24h || 0}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Reports Generated</div>
          <div className="text-3xl font-bold text-green-600 mt-1">{stats?.reports_generated || 0}</div>
          <div className="text-xs text-gray-500 mt-1">Eligibility runs: {stats?.eligibility_runs || 0}</div>
        </Card>
        <Card>
          <div className="text-sm text-gray-600">Avg Completeness</div>
          <div className="text-3xl font-bold text-primary mt-1">{formatPercentage(stats?.avg_case_completeness || 0)}</div>
          <div className="text-xs text-gray-500 mt-1">Documents: {stats?.documents_total || 0}</div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Briefcase className="w-5 h-5 text-gray-700" />
            <h2 className="text-lg font-semibold text-gray-900">Case Status Distribution</h2>
          </div>
          {topStatuses.length === 0 ? (
            <p className="text-sm text-gray-500">No status data available.</p>
          ) : (
            <div className="space-y-3">
              {topStatuses.map(([status, count]) => {
                const value = Number(count || 0);
                const pct = stats?.cases_total ? (value / stats.cases_total) * 100 : 0;
                return (
                  <div key={status}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium text-gray-700">{status}</span>
                      <span className="text-gray-600">{value}</span>
                    </div>
                    <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                      <div className="bg-blue-600 h-2" style={{ width: `${Math.min(pct, 100)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-5 h-5 text-gray-700" />
            <h2 className="text-lg font-semibold text-gray-900">Runtime Health</h2>
          </div>
          {!health ? (
            <Loading text="Checking..." />
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex justify-between items-center">
                <span>Database</span>
                <Badge variant={health.database_ok ? 'success' : 'danger'}>
                  {health.database_ok ? 'Healthy' : 'Down'}
                </Badge>
              </div>
              <div className="flex justify-between items-center">
                <span>LLM Config</span>
                <Badge variant={health.llm_configured ? 'success' : 'warning'}>
                  {health.llm_configured ? 'Configured' : 'Missing'}
                </Badge>
              </div>
              <div className="flex justify-between items-center">
                <span>WhatsApp Service</span>
                <Badge variant={health.whatsapp_service_ok ? 'success' : 'danger'}>
                  {health.whatsapp_service_ok ? `OK (${health.whatsapp_service_status})` : 'Unavailable'}
                </Badge>
              </div>
              <div className="text-xs text-gray-500 pt-2">
                Checked: {formatDate(health.checked_at)}
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Users className="w-5 h-5 text-gray-700" />
            User Operations
          </h2>
          <input
            type="text"
            value={searchUser}
            onChange={(e) => setSearchUser(e.target.value)}
            placeholder="Search user/email"
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64"
          />
        </div>
        {usersLoading ? (
          <Loading text="Loading users..." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Role</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cases</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Latest Case</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="px-4 py-3 text-sm text-gray-800">
                      <div className="font-medium">{user.full_name}</div>
                      <div className="text-xs text-gray-500">{user.email}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">{user.role}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{user.case_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {user.latest_case_at ? formatDate(user.latest_case_at) : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <Badge variant={user.is_active ? 'success' : 'danger'}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Cases (All Users)</h2>
        {casesLoading ? (
          <Loading text="Loading cases..." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Case ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Borrower</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Owner</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Completeness</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {cases.map((caseRow) => (
                  <tr key={caseRow.id}>
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">{caseRow.case_id}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{caseRow.borrower_name || 'N/A'}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{caseRow.user_email}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{caseRow.status}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{formatPercentage(caseRow.completeness_score || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-yellow-600" />
          Operational Watchlist (7 days)
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
          <div>
            <div className="font-medium text-gray-800 mb-2">Failed Cases</div>
            {(logs.failed_cases || []).length === 0 ? (
              <p className="text-gray-500">No failed cases in window.</p>
            ) : (
              <ul className="space-y-1 text-gray-700">
                {logs.failed_cases.slice(0, 8).map((item, idx) => (
                  <li key={`failed-${idx}`}>• {item.case_id} ({item.borrower_name || 'N/A'})</li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="font-medium text-gray-800 mb-2">Doc Classification Watchlist</div>
            {(logs.classification_watchlist || []).length === 0 ? (
              <p className="text-gray-500">No unreadable/unknown docs in window.</p>
            ) : (
              <ul className="space-y-1 text-gray-700">
                {logs.classification_watchlist.slice(0, 8).map((item, idx) => (
                  <li key={`watch-${idx}`}>• {item.case_id}: {item.original_filename || 'unnamed'}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
};

export default AdminPanel;
