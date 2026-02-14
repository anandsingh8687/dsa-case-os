import { useState } from 'react';
import { Search, MapPin, Building2, TrendingUp, AlertCircle } from 'lucide-react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function PincodeChecker() {
  const [pincode, setPincode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();

    // Validate pincode
    if (!pincode || pincode.length !== 6 || !/^\d+$/.test(pincode)) {
      setError('Please enter a valid 6-digit pincode');
      return;
    }

    setLoading(true);
    setError('');
    setResults(null);

    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/v1/lenders/pincodes/${pincode}/details`,
        {
          params: { include_market_summary: true }
        }
      );

      setResults(response.data);
    } catch (err) {
      console.error('Error fetching pincode data:', err);
      setError(err.response?.data?.detail || 'Failed to fetch lender data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    if (!amount) return 'N/A';
    return `₹${amount.toFixed(0)}L`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center space-x-3">
            <MapPin className="w-8 h-8 text-blue-600" />
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Pincode Checker</h1>
              <p className="text-sm text-gray-600 mt-1">
                Find all lenders active in your area instantly
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search Box */}
        <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
          <form onSubmit={handleSearch} className="space-y-4">
            <div>
              <label htmlFor="pincode" className="block text-sm font-medium text-gray-700 mb-2">
                Enter Pincode
              </label>
              <div className="flex space-x-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    id="pincode"
                    value={pincode}
                    onChange={(e) => setPincode(e.target.value)}
                    placeholder="e.g., 411038"
                    maxLength="6"
                    className="w-full pl-12 pr-4 py-4 text-lg border-2 border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-8 py-4 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg"
                >
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-start space-x-3 p-4 bg-red-50 border border-red-200 rounded-lg">
                <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}
          </form>
        </div>

        {/* Results */}
        {results && (
          <div className="space-y-6">
            {/* Summary Card */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl shadow-lg p-6 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-3xl font-bold mb-2">
                    {results.lender_count} Lenders Found
                  </h2>
                  <p className="text-blue-100">
                    Active in Pincode: {results.pincode}
                  </p>
                </div>
                <Building2 className="w-16 h-16 opacity-20" />
              </div>

              {/* Market Summary */}
              {results.market_summary && (
                <div className="mt-6 pt-6 border-t border-blue-400">
                  <div className="flex items-start space-x-3">
                    <TrendingUp className="w-5 h-5 mt-1 flex-shrink-0" />
                    <p className="text-blue-50 leading-relaxed">
                      {results.market_summary}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Lender Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {results.lenders.map((lender) => (
                <div
                  key={lender.lender_id}
                  className="bg-white rounded-xl shadow-md hover:shadow-xl transition-all p-6 border border-gray-200"
                >
                  {/* Lender Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-xl font-bold text-gray-900">
                        {lender.lender_name}
                      </h3>
                      {lender.lender_code && (
                        <p className="text-sm text-gray-500 mt-1">
                          Code: {lender.lender_code}
                        </p>
                      )}
                    </div>
                    <div className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm font-medium">
                      {lender.product_count} {lender.product_count === 1 ? 'Product' : 'Products'}
                    </div>
                  </div>

                  {/* Key Parameters */}
                  <div className="grid grid-cols-2 gap-4 mb-4 p-4 bg-gray-50 rounded-lg">
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                        CIBIL Range
                      </p>
                      <p className="text-lg font-semibold text-gray-900">
                        {lender.cibil_range?.min || 'N/A'} - {lender.cibil_range?.max || 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Max Ticket
                      </p>
                      <p className="text-lg font-semibold text-gray-900">
                        {formatCurrency(lender.ticket_range?.max)}
                      </p>
                    </div>
                  </div>

                  {/* Products */}
                  {lender.products && lender.products.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-gray-700 mb-2">
                        Available Products:
                      </p>
                      {lender.products.slice(0, 3).map((product, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-3 bg-blue-50 rounded-lg"
                        >
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              {product.product_name}
                            </p>
                            <p className="text-xs text-gray-600 mt-1">
                              {product.program_type}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-xs text-gray-500">Min CIBIL</p>
                            <p className="text-sm font-semibold text-blue-600">
                              {product.min_cibil || 'N/A'}
                            </p>
                          </div>
                        </div>
                      ))}
                      {lender.products.length > 3 && (
                        <p className="text-xs text-gray-500 text-center pt-2">
                          +{lender.products.length - 3} more products
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* No Results */}
            {results.lender_count === 0 && (
              <div className="bg-white rounded-xl shadow-md p-12 text-center">
                <AlertCircle className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  No Lenders Found
                </h3>
                <p className="text-gray-600">
                  No lenders are currently active in pincode {results.pincode}.
                  Try a different pincode.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!results && !loading && (
          <div className="bg-white rounded-xl shadow-md p-12 text-center">
            <MapPin className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              Search for Lenders
            </h3>
            <p className="text-gray-600 max-w-md mx-auto">
              Enter a 6-digit pincode above to discover which lenders are active in that area.
              Get instant access to eligibility criteria and product details.
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 text-center">
          <p className="text-sm text-blue-900">
            <span className="font-semibold">Free Tool</span> · No login required ·
            Updated regularly with latest lender policies
          </p>
        </div>
      </div>
    </div>
  );
}
