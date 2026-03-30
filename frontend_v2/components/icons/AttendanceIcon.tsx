// components/icons/AttendanceIcon.tsx
import React from 'react';

interface AttendanceIconProps {
  className?: string;
}

export const AttendanceIcon: React.FC<AttendanceIconProps> = ({ className = "h-6 w-6" }) => {
  return (
    <svg 
      className={className} 
      fill="none" 
      stroke="currentColor" 
      viewBox="0 0 24 24"
    >
      <path 
        strokeLinecap="round" 
        strokeLinejoin="round" 
        strokeWidth={2} 
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" 
      />
    </svg>
  );
};