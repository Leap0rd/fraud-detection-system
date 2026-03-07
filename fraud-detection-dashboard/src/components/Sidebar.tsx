// src/components/Sidebar.tsx
import type { ComponentType, FC } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { 
  HomeIcon, 
  ClockIcon, 
  ShieldCheckIcon 
} from '@heroicons/react/24/outline';

interface NavigationItem {
  name: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
  current: boolean;
}

const navigation: NavigationItem[] = [
  { name: 'Dashboard', href: '/', icon: HomeIcon, current: true },
  { name: 'Transactions', href: '/transactions', icon: ClockIcon, current: false },
  { name: 'Alerts', href: '/alerts', icon: ShieldCheckIcon, current: false },
];

const classNames = (...classes: (string | boolean)[]): string => {
  return classes.filter(Boolean).join(' ');
};

export const Sidebar: FC = () => {
  const location = useLocation();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div>
          <div className="sidebar-brand-title">FraudShield</div>
          <div style={{ opacity: 0.8, fontSize: 12, marginTop: 2 }}>Monitoring Console</div>
        </div>
      </div>

      <nav className="nav">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={classNames('nav-item', isActive && 'active')}
            >
              <Icon className="nav-icon" aria-hidden="true" />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div style={{ marginTop: 'auto', opacity: 0.85, fontSize: 12 }}>
        <div style={{ fontWeight: 800 }}>Admin User</div>
        <div style={{ marginTop: 4 }}>Local environment</div>
      </div>
    </aside>
  );
};

export default Sidebar;