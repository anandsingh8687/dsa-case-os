import axios from 'axios';

// Use environment variable for API URL, fallback to backend Railway service URL.
const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  'https://beautiful-insight-production-16a6.up.railway.app/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only redirect to login on 401 if we're not already on a public page
    // This prevents redirect loops after login
    if (error.response?.status === 401) {
      const currentPath = window.location.pathname;
      const isPublicPage = ['/', '/login', '/register'].includes(currentPath);

      if (!isPublicPage) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
