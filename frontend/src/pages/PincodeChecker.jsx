import React, { useState } from 'react';
import { MapPin, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import apiClient from '../api/client';
import { Card, Button, Badge, Loading } from '../components/ui';

const PincodeChecker = () => {
  const [pincode, setPincode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSearch = async () => {
    if (!/^\d{6}$/.test(pincode)) {
      toast.error('Please enter a valid 6-digit pincode');
      return;
    }

    setIsLoading(true);
    try {
      const response = await apiClient.get(`/pincodes/${pincode}/lenders`);
      setResult(response.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to fetch lenders');
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Pincode Checker</h1>
        <p className="text-gray-600 mt-1">
          Check lender availability instantly by pincode.
        </p>
      </div>

      <Card className="mb-6">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Enter 6-digit pincode"
              value={pincode}
              onChange={(e) => setPincode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSearch();
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <Button
            variant="primary"
            onClick={handleSearch}
            disabled={isLoading}
            className="flex items-center gap-2"
          >
            <Search className="w-4 h-4" />
            {isLoading ? 'Searching...' : 'Search'}
          </Button>
        </div>
      </Card>

      {isLoading && <Loading text="Checking lender coverage..." />}

      {!isLoading && result && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Pincode {result.pincode}
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  {result.lender_count} lender{result.lender_count === 1 ? '' : 's'} available
                </p>
              </div>
              <Badge variant={result.lender_count > 0 ? 'success' : 'danger'}>
                {result.lender_count > 0 ? 'Coverage Available' : 'No Coverage'}
              </Badge>
            </div>
          </Card>

          {result.lender_count > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {result.lenders.map((lender) => (
                <Card key={lender.lender_id} hover>
                  <h3 className="font-semibold text-gray-900 mb-3">{lender.lender_name}</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Products</span>
                      <span className="font-medium">{lender.product_count || 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Min CIBIL</span>
                      <span className="font-medium">{lender.min_cibil || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Max Ticket</span>
                      <span className="font-medium">
                        {lender.max_ticket_size ? `₹${Number(lender.max_ticket_size).toLocaleString('en-IN')}L` : 'N/A'}
                      </span>
                    </div>
                    {Array.isArray(lender.product_types) && lender.product_types.length > 0 && (
                      <div>
                        <span className="text-gray-600">Product Types</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {lender.product_types.slice(0, 4).map((product) => (
                            <Badge key={`${lender.lender_id}-${product}`} variant="info">
                              {product}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card>
              <p className="text-sm text-gray-600">
                No lenders currently mapped for this pincode. Try nearby pincodes or check again later.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default PincodeChecker;
