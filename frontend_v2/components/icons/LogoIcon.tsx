import React from 'react';

// قمنا بتغيير النوع ليقبل خصائص الصور (Image Props) بدلاً من SVG
export const LogoIcon: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = ({ className, ...props }) => (
  <img 
    src="/favicon-32x32.png" 
    alt="Logo"
    className={`object-contain ${className}`} 
    {...props} 
  />
);