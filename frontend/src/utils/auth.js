export const getToken = () => localStorage.getItem('token');

export const setToken = (token) => {
  if (!token || token === 'undefined' || token === 'null') {
    localStorage.removeItem('token');
    return;
  }
  localStorage.setItem('token', token);
};

export const removeToken = () => localStorage.removeItem('token');

export const isAuthenticated = () => !!getToken();

export const isAdmin = () => {
  const user = getUser();
  return user?.role === 'admin' || user?.role === 'super_admin';
};

export const getUser = () => {
  const userStr = localStorage.getItem('user');

  // Handle edge cases: null, undefined, or invalid JSON
  if (!userStr || userStr === 'undefined' || userStr === 'null') {
    return null;
  }

  try {
    return JSON.parse(userStr);
  } catch (error) {
    console.error('Failed to parse user data from localStorage:', error);
    // Clear invalid data
    localStorage.removeItem('user');
    return null;
  }
};

export const setUser = (user) => {
  if (!user) {
    localStorage.removeItem('user');
    return;
  }
  localStorage.setItem('user', JSON.stringify(user));
};

export const removeUser = () => {
  localStorage.removeItem('user');
};

export const logout = () => {
  removeToken();
  removeUser();
  window.location.href = '/login';
};
