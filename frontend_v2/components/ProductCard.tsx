
import React from 'react';
import { Product } from '../types';

interface ProductCardProps {
  product: Product;
  onPreview: (url: string) => void;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product, onPreview }) => {
  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 90) return 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300';
    if (similarity >= 75) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300';
    return 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300';
  };
  
  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-sm overflow-hidden flex flex-col group transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
      <div className="relative overflow-hidden">
        <img
          src={product.imageUrl}
          alt={product.name}
          className="w-full h-56 object-cover transition-transform duration-300 group-hover:scale-105"
        />
        <div className={`absolute top-3 right-3 text-xs font-bold px-2 py-1 rounded-full ${getSimilarityColor(product.similarity)}`}>
          {product.similarity}% Match
        </div>
      </div>
      <div className="p-5 flex flex-col flex-grow">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 truncate" title={product.name}>
          {product.name}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{product.store}</p>
        <div className="mt-auto flex justify-between items-center">
          <p className="text-2xl font-extrabold text-blue-600 dark:text-blue-400">${product.price.toFixed(2)}</p>
          <button
            onClick={() => onPreview(product.url)}
            className="bg-blue-50 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300 font-semibold py-2 px-5 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors duration-300"
          >
            View
          </button>
        </div>
      </div>
    </div>
  );
};
