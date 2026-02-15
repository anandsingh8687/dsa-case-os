import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FilePlus,
  MessageSquare,
  MapPin,
  Settings,
  Search,
  Shield,
  FileSpreadsheet,
  Percent,
  Users,
  Send,
} from 'lucide-react';
import { getUser } from '../../utils/auth';

const Sidebar = () => {
  const user = getUser();
  const isAdmin = user?.role === 'admin';

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/cases/new', icon: FilePlus, label: 'New Case' },
    { to: '/quick-scan', icon: Search, label: 'Quick Scan' },
    { to: '/copilot', icon: MessageSquare, label: 'Copilot' },
    { to: '/bank-statement', icon: FileSpreadsheet, label: 'Bank Statement' },
    { to: '/commission', icon: Percent, label: 'Commission' },
    { to: '/leads', icon: Users, label: 'Leads' },
    { to: '/submissions', icon: Send, label: 'Submissions' },
    { to: '/pincode-checker', icon: MapPin, label: 'Pincode Checker' },
    { to: '/settings', icon: Settings, label: 'Settings' },
    ...(isAdmin ? [{ to: '/admin', icon: Shield, label: 'Admin' }] : []),
  ];

  return (
    <div className="w-64 bg-gray-900 text-white h-screen fixed left-0 top-0 overflow-y-auto">
      <div className="p-6">
        <h1 className="text-2xl font-bold text-primary">Credilo</h1>
      </div>

      <nav className="mt-6">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center px-6 py-3 text-gray-300 hover:bg-gray-800 hover:text-white transition-colors ${
                isActive ? 'bg-gray-800 text-white border-l-4 border-primary' : ''
              }`
            }
          >
            <item.icon className="w-5 h-5 mr-3" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

export default Sidebar;
