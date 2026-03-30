
import React, { useState } from 'react';

interface ProductPreviewModalProps {
    isOpen: boolean;
    onClose: () => void;
    productUrl: string;
}

export const ProductPreviewModal: React.FC<ProductPreviewModalProps> = ({ isOpen, onClose, productUrl }) => {
    const [isLoading, setIsLoading] = useState(true);

    if (!isOpen) return null;

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-4xl h-[90vh] flex flex-col transform transition-all"
                onClick={e => e.stopPropagation()}
            >
                <header className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
                    <div className="flex items-center gap-4">
                        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-3xl font-light">&times;</button>
                        <h2 className="text-lg font-bold text-gray-800 dark:text-gray-100 truncate">Product Preview</h2>
                    </div>
                    <a 
                        href={productUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="bg-blue-600 text-white font-bold py-2 px-5 rounded-lg hover:bg-blue-700 transition"
                    >
                        Open in New Tab
                    </a>
                </header>

                <div className="flex-grow relative">
                    {isLoading && (
                        <div className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-gray-800">
                            <div className="text-center">
                                <div className="w-12 h-12 border-4 border-blue-500 border-dashed rounded-full animate-spin mx-auto"></div>
                                <p className="mt-4 text-gray-600 dark:text-gray-300">Loading product page...</p>
                                <p className="text-sm text-gray-400 dark:text-gray-500">Some sites may not load in a preview.</p>
                            </div>
                        </div>
                    )}
                    <iframe
                        src={productUrl}
                        className={`w-full h-full border-0 transition-opacity duration-500 ${isLoading ? 'opacity-0' : 'opacity-100'}`}
                        onLoad={() => setIsLoading(false)}
                        title="Product Preview"
                        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                    ></iframe>
                </div>
            </div>
        </div>
    );
};
