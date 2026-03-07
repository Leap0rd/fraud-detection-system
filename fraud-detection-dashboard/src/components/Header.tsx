// src/components/Header.tsx
import { FC, useState } from 'react';
import { BellIcon, UserCircleIcon } from '@heroicons/react/24/outline';

interface HeaderProps {
  // Add any props you need here
}

export const Header: FC<HeaderProps> = () => {
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  return (
    <header className="topbar">
      <div className="topbar-title">Fraud Detection Dashboard</div>

      <div className="topbar-actions">
        <button type="button" className="btn" aria-label="Notifications">
          <BellIcon style={{ width: 18, height: 18 }} aria-hidden="true" />
        </button>

        <div style={{ position: 'relative' }}>
          <button
            type="button"
            className="btn"
            aria-label="User menu"
            onClick={() => setIsProfileOpen((v) => !v)}
          >
            <UserCircleIcon style={{ width: 20, height: 20 }} aria-hidden="true" />
          </button>

          {isProfileOpen && (
            <div className="menu" role="menu" aria-label="User menu">
              <button type="button" className="menu-item" role="menuitem" onClick={() => setIsProfileOpen(false)}>
                Profile
              </button>
              <button type="button" className="menu-item" role="menuitem" onClick={() => setIsProfileOpen(false)}>
                Settings
              </button>
              <button type="button" className="menu-item" role="menuitem" onClick={() => setIsProfileOpen(false)}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;