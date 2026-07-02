import React from 'react';
import { Department } from '../../services/firestoreService';
import { DepartmentIcon } from './icons/DepartmentIcons';
import { Edit2 } from 'lucide-react';

interface DepartmentCardProps {
  department: Department;
  onEdit?: (dept: Department) => void;
  onClick?: (dept: Department) => void;
}

const DepartmentCard: React.FC<DepartmentCardProps> = ({ department, onEdit, onClick }) => {
  return (
    <div className="relative group h-full">
      <button 
        onClick={() => onClick && onClick(department)}
        className="block h-full w-full bg-white dark:bg-slate-800 rounded-xl p-8 shadow-sm hover:shadow-lg transition-all duration-300 border border-slate-100 dark:border-slate-700 flex flex-col items-center text-center cursor-pointer"
      >
        <div className="text-[var(--color-primary)] dark:text-[var(--color-primary)] mb-6 group-hover:scale-110 transition-transform duration-300">
          <DepartmentIcon type={department.iconType as any} className="w-16 h-16" />
        </div>
      
        <h3 className="text-xl font-bold text-slate-800 dark:text-white mb-1">
          {department.name}
        </h3>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-2 font-medium">
          {department.nameEn}
        </p>
        
        <div className="text-slate-500 dark:text-slate-400 text-sm">
          <span className="font-medium">{department.managerTitle}: </span>
          <span>{department.managerName}</span>
        </div>
      </button>
      {onEdit && (
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onEdit(department);
          }}
          className="absolute top-2 right-2 p-2 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full hover:bg-cyan-100 hover:text-cyan-600 transition-colors z-10"
        >
          <Edit2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};

export default DepartmentCard;