
import React, { useState, useMemo } from 'react';
import { Product } from '../types';
import { ProductCard } from './ProductCard';
import { FilterIcon } from './icons/FilterIcon';
import { SearchIcon } from './icons/SearchIcon';
import { ProductPreviewModal } from './modals/ProductPreviewModal';

interface ResultsPageProps {
  products: Product[];
  onBack: () => void;
  isTaskActive: boolean;
}

export const ResultsPage: React.FC<ResultsPageProps> = ({ products, onBack, isTaskActive }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [maxPrice, setMaxPrice] = useState(() => {
    if (products.length === 0) return 1000;
    return Math.ceil(Math.max(...products.map(p => p.price)));
  });
  const [price, setPrice] = useState(maxPrice);
  const [sortBy, setSortBy] = useState('similarity');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [showMobileFilters, setShowMobileFilters] = useState(false);

  const filteredAndSortedProducts = useMemo(() => {
    return products
      .filter(product => product.name.toLowerCase().includes(searchTerm.toLowerCase()))
      .filter(product => product.price <= price)
      .sort((a, b) => {
        if (sortBy === 'similarity') return b.similarity - a.similarity;
        if (sortBy === 'price_asc') return a.price - b.price;
        return b.price - a.price;
      });
  }, [products, searchTerm, price, sortBy]);

  return (
    <>
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg border border-gray-100 dark:border-gray-700 p-4 sm:p-6 animate-fade-in h-full flex flex-col">
          <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
              <div>
                <h2 className="text-xl sm:text-2xl font-bold text-gray-800 dark:text-gray-100">نتائج تحليل AI</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">تم العثور على {filteredAndSortedProducts.length} منتج مطابق</p>
              </div>
              
              <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
                  <div className="relative flex-grow md:flex-grow-0">
                      <input
                          type="text"
                          placeholder="تصفية النتائج..."
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                          className="w-full md:w-64 pl-4 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200 text-sm"
                      />
                      <SearchIcon className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400"/>
                  </div>
                  
                  <button 
                    className="md:hidden p-2 bg-gray-100 dark:bg-gray-700 rounded-lg text-gray-600 dark:text-gray-300"
                    onClick={() => setShowMobileFilters(!showMobileFilters)}
                  >
                    <FilterIcon className="h-5 w-5" />
                  </button>

                  <button 
                      onClick={onBack}
                      className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg text-sm transition ml-auto md:ml-0"
                  >
                      {isTaskActive ? 'بحث جديد' : 'إنهاء'}
                  </button>
              </div>
          </header>

          <div className="flex flex-col lg:flex-row gap-6">
              {/* Filters Sidebar (Responsive) */}
              <aside className={`
                ${showMobileFilters ? 'block' : 'hidden'} 
                lg:block w-full lg:w-64 flex-shrink-0 space-y-6
                bg-slate-50 dark:bg-gray-800/50 p-4 rounded-xl border border-gray-200 dark:border-gray-700
              `}>
                  <div>
                      <h3 className="font-bold text-gray-800 dark:text-gray-100 mb-4 flex items-center gap-2">
                          <FilterIcon className="h-4 w-4" /> الفلاتر
                      </h3>
                      
                      <div className="mb-6">
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">الحد الأقصى للسعر: ${price}</label>
                          <input
                              type="range"
                              min="0"
                              max={maxPrice}
                              value={price}
                              onChange={(e) => setPrice(Number(e.target.value))}
                              className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-blue-600"
                          />
                          <div className="flex justify-between text-xs text-gray-500 mt-1">
                              <span>$0</span>
                              <span>${maxPrice}</span>
                          </div>
                      </div>

                      <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">الترتيب حسب</label>
                          <select
                              value={sortBy}
                              onChange={(e) => setSortBy(e.target.value)}
                              className="w-full p-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                          >
                              <option value="similarity">الأفضل مطابقة (AI)</option>
                              <option value="price_asc">السعر: من الأقل</option>
                              <option value="price_desc">السعر: من الأعلى</option>
                          </select>
                      </div>
                  </div>
              </aside>

              {/* Products Grid */}
              <main className="flex-1">
                  {filteredAndSortedProducts.length > 0 ? (
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-6">
                          {filteredAndSortedProducts.map((product, index) => (
                              <ProductCard key={`${product.name}-${index}`} product={product} onPreview={setPreviewUrl} />
                          ))}
                      </div>
                  ) : (
                      <div className="flex flex-col items-center justify-center py-16 text-center bg-gray-50 dark:bg-gray-800/50 rounded-2xl border-2 border-dashed border-gray-200 dark:border-gray-700">
                           <SearchIcon className="h-16 w-16 text-gray-300 dark:text-gray-600 mb-4"/>
                           <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">لا توجد نتائج</h3>
                           <p className="text-gray-500 text-sm mt-1">حاول توسيع نطاق البحث أو تغيير الفلاتر.</p>
                      </div>
                  )}
              </main>
          </div>
      </div>
      {previewUrl && (
            <ProductPreviewModal
                isOpen={!!previewUrl}
                onClose={() => setPreviewUrl(null)}
                productUrl={previewUrl}
            />
        )}
    </>
  );
};
