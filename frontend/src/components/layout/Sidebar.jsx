import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FilePlus,
  MessageSquare,
  MapPin,
  Settings,
  Shield,
  FileSpreadsheet,
  CircleHelp,
} from 'lucide-react';
import { getUser } from '../../utils/auth';
import crediloLogo from '../../assets/credilo-logo.svg';

const Sidebar = () => {
  const user = getUser();
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/cases/new', icon: FilePlus, label: 'New Case' },
    { to: '/copilot', icon: MessageSquare, label: 'Copilot' },
    { to: '/bank-statement', icon: FileSpreadsheet, label: 'Bank Statement' },
    { to: '/quick-forward-help', icon: CircleHelp, label: 'Quick Forward Help' },
    { to: '/pincode-checker', icon: MapPin, label: 'Pincode Checker' },
    { to: '/settings', icon: Settings, label: 'Settings' },
    ...(isAdmin ? [{ to: '/admin', icon: Shield, label: 'Admin' }] : []),
  ];

  return (
    <div className="w-64 bg-gray-900 text-white h-screen fixed left-0 top-0 overflow-y-auto">
      <div className="p-6">
        <div className="flex items-center gap-3">
          <img
            src={crediloLogo}
            alt="Credilo logo"
            className="w-9 h-9 rounded-lg object-cover border border-gray-700 bg-gray-800"
          />
          <h1 className="text-2xl font-bold text-primary">Credilo</h1>
        </div>
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
