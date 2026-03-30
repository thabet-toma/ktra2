import React from 'react';

interface ErrorDisplayProps {
  message: string;
  onClose: () => void;
}

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({ message, onClose }) => {
  return (
    <div className="bg-red-100 dark:bg-red-900/50 border-r-4 border-red-500 text-red-700 dark:text-red-300 p-4 rounded-lg mb-6 flex justify-between items-center animate-fade-in">
      <div>
        <p className="font-bold">خطأ</p>
        <p>{message}</p>
      </div>
      <button onClick={onClose} className="text-red-500 hover:text-red-700 dark:text-red-300 dark:hover:text-red-100 font-bold text-2xl">&times;</button>
    </div>
  );
};