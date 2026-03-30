import React from 'react';
import { Outlet } from 'react-router-dom';
import { PublicNavbar } from './PublicNavbar';

export const PublicLayout = () => {
  return (
    <>
      <PublicNavbar />
      {/* 
        pt-20: لإضافة مسافة علوية لأن الناف بار fixed 
        min-h-screen: لضمان أن الخلفية تغطي كامل الشاشة
      */}
      <div className="pt-20 min-h-screen bg-gray-50 dark:bg-gray-900">
        <Outlet />
      </div>
    </>
  );
};