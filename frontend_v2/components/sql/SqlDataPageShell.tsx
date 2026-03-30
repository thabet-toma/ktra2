import React from "react";

export function SqlDataPageShell(props: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="p-4 md:p-6">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900">
            {props.title}
          </h1>
          {props.subtitle ? (
            <div className="text-sm text-gray-600 mt-1">{props.subtitle}</div>
          ) : null}
        </div>
        {props.actions ? <div className="shrink-0">{props.actions}</div> : null}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {props.children}
      </div>
    </div>
  );
}

