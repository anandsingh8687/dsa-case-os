import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, MapPin } from 'lucide-react';
import { getLenders, getLendersByPincode } from '../api/services';
import { Card, Loading, Badge } from '../components/ui';

const Lenders = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [pincode, setPincode] = useState('');

  const { data: lendersData, isLoading } = useQuery({
    queryKey: ['lenders'],
    queryFn: getLenders,
  });

  const { data: pincodeData, isLoading: pincodeLoading } = useQuery({
    queryKey: ['lenders-pincode', pincode],
    queryFn: () => getLendersByPincode(pincode),
    enabled: pincode.length === 6,
  });

  const lenders = pincode.length === 6 && pincodeData
    ? pincodeData.data?.lenders || []
    : lendersData?.data?.lenders || [];

  const filteredLenders = lenders.filter((lender) =>
    lender.lender_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (isLoading) {
    return <Loading size="lg" text="Loading lenders..." />;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Lender Directory</h1>

      {/* Search and Filter */}
      <Card className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search by lender name..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="relative">
            <MapPin className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Filter by pincode..."
              value={pincode}
              onChange={(e) => setPincode(e.target.value)}
              maxLength={6}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </Card>

      {/* Lenders List */}
      {pincodeLoading ? (
        <Loading text="Loading lenders..." />
      ) : filteredLenders.length === 0 ? (
        <Card>
          <p className="text-center text-gray-500 py-8">No lenders found</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredLenders.map((lender) => (
            <Card key={lender.lender_id} hover>
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold text-gray-900">
                  {lender.lender_name}
                </h3>
                <Badge variant="primary">Active</Badge>
              </div>

              <div className="space-y-2 text-sm">
                {lender.product_types && (
                  <div>
                    <span className="text-gray-600">Products:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {lender.product_types.map((product, index) => (
                        <Badge key={index} variant="info">
                          {product}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {lender.min_cibil && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Min CIBIL:</span>
                    <span className="font-medium">{lender.min_cibil}</span>
                  </div>
                )}

                {lender.max_ticket_size && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Max Ticket:</span>
                    <span className="font-medium">
                      ₹{(lender.max_ticket_size / 100000).toFixed(1)}L
                    </span>
                  </div>
                )}

                {lender.turnaround_time && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">TAT:</span>
                    <span className="font-medium">
                      {lender.turnaround_time} days
                    </span>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default Lenders;
