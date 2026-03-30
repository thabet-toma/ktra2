import React from 'react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  showText?: boolean;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = 'lg', showText = true }) => {
  const messages = [
    "Analyzing product image with AI...",
    "Extracting keywords...",
    "Searching Chinese marketplaces...",
    "Matching prices and results...",
    "Finalizing results..."
  ];
  const [messageIndex, setMessageIndex] = React.useState(0);

  React.useEffect(() => {
    if (!showText) return;
    const interval = setInterval(() => {
      setMessageIndex((prevIndex) => (prevIndex + 1) % messages.length);
    }, 2500);
    return () => clearInterval(interval);
  }, [messages.length, showText]);

  if (size === 'sm') {
    return (
      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center text-center p-10 bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-lg">
      <div className={`border-blue-500 border-dashed rounded-full animate-spin ${size === 'md' ? 'w-10 h-10 border-4' : 'w-16 h-16 border-4'}`}></div>
      {showText && (
        <>
          <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-200 mt-6">Searching for Products</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-2 transition-opacity duration-500">{messages[messageIndex]}</p>
        </>
      )}
    </div>
  );
};