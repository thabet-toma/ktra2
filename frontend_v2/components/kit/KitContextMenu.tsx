import React, { useRef, useEffect, useState } from 'react';

export interface KitContextMenuAction {
  label: string;
  icon?: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  hint?: string;
}

export interface KitContextMenuProps {
  actions: KitContextMenuAction[];
  children: React.ReactNode;
}

export const KitContextMenu: React.FC<KitContextMenuProps> = ({ actions, children }) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleContext = (e: React.MouseEvent) => {
    e.preventDefault();
    setPos({ x: e.clientX, y: e.clientY });
    setOpen(true);
  };

  return (
    <div ref={ref} onContextMenu={handleContext}>
      {children}
      {open && (
        <div
          className="ktra-context-menu"
          style={{
            position: 'fixed',
            top: pos.y,
            left: pos.x,
            zIndex: 9999,
            background: 'var(--ktra-panel)',
            border: '1px solid var(--ktra-border)',
            borderRadius: 'var(--ktra-radius)',
            padding: '4px 0',
            minWidth: '180px',
            boxShadow: '2px 2px 6px rgba(0,0,0,0.15)',
          }}
          onClick={() => setOpen(false)}
        >
          {actions.map((a, i) => (
            <button
              key={i}
              className="ktra-context-item"
              disabled={a.disabled}
              onClick={a.onClick}
              title={a.hint}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                width: '100%',
                padding: '6px 12px',
                border: 'none',
                background: 'transparent',
                color: a.disabled ? 'var(--ktra-ink-soft)' : 'var(--ktra-ink)',
                font: 'inherit',
                fontSize: '12px',
                cursor: a.disabled ? 'default' : 'pointer',
                textAlign: 'right',
              }}
              onMouseEnter={(e) => {
                if (!a.disabled) e.currentTarget.style.background = 'var(--ktra-accent-bg)';
              }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              {a.icon && <span style={{ width: '16px', textAlign: 'center' }}>{a.icon}</span>}
              <span>{a.label}</span>
              {a.hint && <span style={{ marginRight: 'auto', fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>{a.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
