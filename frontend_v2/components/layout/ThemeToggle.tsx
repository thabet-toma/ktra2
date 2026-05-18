import React from 'react';
import { useTheme } from '../../contexts/ThemeContext';
import { SunIcon } from '../icons/SunIcon';
import { MoonIcon } from '../icons/MoonIcon';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
      aria-label="تبديل المظهر"
    >
      {theme === 'light' ? <MoonIcon className="h-4 w-4" /> : <SunIcon className="h-4 w-4" />}
    </button>
  );
};