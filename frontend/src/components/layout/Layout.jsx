import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';

const Layout = ({ children }) => {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 ml-64">
        <Header />
        <main className="mt-16 p-6 overflow-y-auto" style={{ height: 'calc(100vh - 4rem)' }}>
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
