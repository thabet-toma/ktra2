import React from 'react';
import { Link } from 'react-router-dom';
import { Department } from '../data/departments';
import { DepartmentIcon } from './icons/DepartmentIcons';

interface DepartmentCardProps {
  department: Department;
}

const DepartmentCard: React.FC<DepartmentCardProps> = ({ department }) => {
  return (
    <Link 
      to={`/contact/${department.id}`}
      className="group bg-white dark:bg-slate-800 rounded-xl p-8 shadow-sm hover:shadow-lg transition-all duration-300 border border-slate-100 dark:border-slate-700 flex flex-col items-center text-center cursor-pointer"
    >
      <div className="text-[var(--color-primary)] dark:text-[var(--color-primary)] mb-6 group-hover:scale-110 transition-transform duration-300">
        <DepartmentIcon type={department.iconType} className="w-16 h-16" />
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
    </Link>
  );
};

export default DepartmentCard;