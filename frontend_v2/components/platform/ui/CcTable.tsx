import React from "react";

export interface CcTableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  className?: string;
  children?: React.ReactNode;
}

export const CcTable: React.FC<CcTableProps> = ({ className = "", children, ...props }) => {
  return (
    <div className="w-full overflow-x-auto rounded-[var(--radius-cc,1rem)] border border-cc-border bg-cc-surface/50">
      <table className={`w-full text-right text-sm border-collapse ${className}`} {...props}>
        {children}
      </table>
    </div>
  );
};

export interface CcTheadProps extends React.HTMLAttributes<HTMLTableSectionElement> {
  className?: string;
  children?: React.ReactNode;
}

export const CcThead: React.FC<CcTheadProps> = ({ className = "", children, ...props }) => {
  return (
    <thead
      className={`border-b border-cc-border bg-cc-surface-2/60 text-xs font-semibold text-cc-text-muted ${className}`}
      {...props}
    >
      {children}
    </thead>
  );
};

export interface CcThProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  className?: string;
  children?: React.ReactNode;
}

export const CcTh: React.FC<CcThProps> = ({ className = "", children, ...props }) => {
  return (
    <th className={`px-4 py-3 font-semibold text-right text-cc-text-muted ${className}`} {...props}>
      {children}
    </th>
  );
};

export interface CcTrProps extends React.HTMLAttributes<HTMLTableRowElement> {
  className?: string;
  children?: React.ReactNode;
}

export const CcTr: React.FC<CcTrProps> = ({ className = "", children, ...props }) => {
  return (
    <tr
      className={`border-b border-cc-border last:border-0 even:bg-cc-bg-2 hover:bg-cc-surface-2 transition-colors duration-150 ${className}`}
      {...props}
    >
      {children}
    </tr>
  );
};

export interface CcTdProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  className?: string;
  children?: React.ReactNode;
}

export const CcTd: React.FC<CcTdProps> = ({ className = "", children, ...props }) => {
  return (
    <td className={`px-4 py-3 text-cc-text align-middle ${className}`} {...props}>
      {children}
    </td>
  );
};
