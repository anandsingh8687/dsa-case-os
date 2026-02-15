import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import {
  getLeads,
  createLead,
  updateLead,
  getLeadActivities,
  addLeadActivity,
} from '../api/services';
import { Badge, Button, Card, Loading, Modal } from '../components/ui';

const STAGES = ['new', 'contacted', 'qualified', 'doc_collection', 'converted', 'lost'];
const ACTIVITIES = ['call', 'whatsapp', 'email', 'note', 'stage_change'];

const stageVariant = (stage) => {
  if (stage === 'converted') return 'success';
  if (stage === 'lost') return 'danger';
  if (stage === 'qualified' || stage === 'doc_collection') return 'warning';
  return 'default';
};

const Leads = () => {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedLead, setSelectedLead] = useState(null);
  const [form, setForm] = useState({
    customer_name: '',
    phone: '',
    email: '',
    loan_type_interest: 'BL',
    loan_amount_approx: '',
    city: '',
    pincode: '',
    source: 'manual',
    stage: 'new',
  });
  const [activityForm, setActivityForm] = useState({
    activity_type: 'note',
    notes: '',
    call_outcome: '',
  });

  const { data: leadsData, isLoading } = useQuery({
    queryKey: ['leads', search],
    queryFn: () => getLeads({ q: search || undefined, limit: 200 }),
  });

  const { data: activitiesData, isLoading: activitiesLoading } = useQuery({
    queryKey: ['lead-activities', selectedLead?.id],
    queryFn: () => getLeadActivities(selectedLead.id),
    enabled: !!selectedLead?.id,
  });

  const createLeadMutation = useMutation({
    mutationFn: createLead,
    onSuccess: () => {
      toast.success('Lead created');
      setForm({
        customer_name: '',
        phone: '',
        email: '',
        loan_type_interest: 'BL',
        loan_amount_approx: '',
        city: '',
        pincode: '',
        source: 'manual',
        stage: 'new',
      });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to create lead');
    },
  });

  const updateLeadMutation = useMutation({
    mutationFn: ({ leadId, payload }) => updateLead(leadId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['lead-activities'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to update lead');
    },
  });

  const addActivityMutation = useMutation({
    mutationFn: ({ leadId, payload }) => addLeadActivity(leadId, payload),
    onSuccess: () => {
      toast.success('Activity added');
      setActivityForm({ activity_type: 'note', notes: '', call_outcome: '' });
      queryClient.invalidateQueries({ queryKey: ['lead-activities'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to add activity');
    },
  });

  const leads = leadsData?.data?.leads || [];
  const activities = activitiesData?.data?.activities || [];

  if (isLoading) return <Loading text="Loading leads..." />;

  return (
    <div className="space-y-6">
      <Card>
        <h1 className="text-2xl font-bold text-gray-900">Lead Management CRM</h1>
        <p className="text-sm text-gray-600 mt-1">
          Track lead journey from first contact to conversion with follow-up history.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-5">
          <input
            className="md:col-span-2 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Search by name, phone, or email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="text-sm text-gray-600 rounded-lg border border-gray-200 px-3 py-2 bg-gray-50">
            Total Leads: <span className="font-semibold text-gray-900">{leads.length}</span>
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Create New Lead</h2>
        <form
          className="grid grid-cols-1 md:grid-cols-4 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            createLeadMutation.mutate({
              ...form,
              loan_amount_approx: form.loan_amount_approx ? Number(form.loan_amount_approx) : null,
            });
          }}
        >
          <input
            required
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Customer name"
            value={form.customer_name}
            onChange={(e) => setForm((prev) => ({ ...prev, customer_name: e.target.value }))}
          />
          <input
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Phone"
            value={form.phone}
            onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
          />
          <input
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
          />
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={form.loan_type_interest}
            onChange={(e) => setForm((prev) => ({ ...prev, loan_type_interest: e.target.value }))}
          >
            <option value="BL">BL</option>
            <option value="PL">PL</option>
            <option value="HL">HL</option>
            <option value="LAP">LAP</option>
          </select>
          <input
            type="number"
            min="0"
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Loan amount approx"
            value={form.loan_amount_approx}
            onChange={(e) => setForm((prev) => ({ ...prev, loan_amount_approx: e.target.value }))}
          />
          <input
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="City"
            value={form.city}
            onChange={(e) => setForm((prev) => ({ ...prev, city: e.target.value }))}
          />
          <input
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Pincode"
            value={form.pincode}
            onChange={(e) => setForm((prev) => ({ ...prev, pincode: e.target.value }))}
          />
          <Button type="submit" disabled={createLeadMutation.isPending}>
            {createLeadMutation.isPending ? 'Creating...' : 'Create Lead'}
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Lead Pipeline</h2>
        <div className="overflow-x-auto border border-gray-200 rounded-lg">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Lead</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Loan</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Stage</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Follow-up</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">{lead.customer_name}</div>
                    <div className="text-xs text-gray-500">{lead.phone || lead.email || 'No contact info'}</div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{lead.loan_type_interest || 'N/A'}</td>
                  <td className="px-3 py-2">
                    <select
                      className="border border-gray-300 rounded px-2 py-1 text-xs"
                      value={lead.stage}
                      onChange={(e) =>
                        updateLeadMutation.mutate({
                          leadId: lead.id,
                          payload: { stage: e.target.value },
                        })
                      }
                    >
                      {STAGES.map((stage) => (
                        <option key={stage} value={stage}>{stage}</option>
                      ))}
                    </select>
                    <div className="mt-1">
                      <Badge variant={stageVariant(lead.stage)}>{lead.stage}</Badge>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{lead.next_followup_date || 'Not set'}</td>
                  <td className="px-3 py-2">
                    <Button size="sm" variant="outline" onClick={() => setSelectedLead(lead)}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-gray-500">No leads found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        isOpen={!!selectedLead}
        onClose={() => setSelectedLead(null)}
        title={selectedLead ? `Lead Activity • ${selectedLead.customer_name}` : 'Lead Activity'}
        size="lg"
      >
        {!selectedLead ? null : (
          <div className="space-y-4">
            <form
              className="grid grid-cols-1 md:grid-cols-3 gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                addActivityMutation.mutate({
                  leadId: selectedLead.id,
                  payload: {
                    activity_type: activityForm.activity_type,
                    notes: activityForm.notes || null,
                    call_outcome: activityForm.call_outcome || null,
                  },
                });
              }}
            >
              <select
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={activityForm.activity_type}
                onChange={(e) => setActivityForm((prev) => ({ ...prev, activity_type: e.target.value }))}
              >
                {ACTIVITIES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
              <input
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Call outcome (optional)"
                value={activityForm.call_outcome}
                onChange={(e) => setActivityForm((prev) => ({ ...prev, call_outcome: e.target.value }))}
              />
              <Button type="submit" disabled={addActivityMutation.isPending}>
                {addActivityMutation.isPending ? 'Saving...' : 'Add Activity'}
              </Button>
              <textarea
                className="md:col-span-3 border border-gray-300 rounded-lg px-3 py-2 text-sm"
                rows={3}
                placeholder="Notes"
                value={activityForm.notes}
                onChange={(e) => setActivityForm((prev) => ({ ...prev, notes: e.target.value }))}
              />
            </form>

            {activitiesLoading ? (
              <Loading text="Loading activities..." />
            ) : (
              <div className="max-h-72 overflow-auto border border-gray-200 rounded-lg">
                <ul className="divide-y divide-gray-100">
                  {activities.map((item) => (
                    <li key={item.id} className="px-3 py-2 text-sm">
                      <div className="font-medium text-gray-900">{item.activity_type}</div>
                      <div className="text-gray-700">{item.notes || '—'}</div>
                      <div className="text-xs text-gray-500 mt-1">{item.created_at}</div>
                    </li>
                  ))}
                  {activities.length === 0 && (
                    <li className="px-3 py-4 text-sm text-gray-500">No activity recorded yet.</li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Leads;
