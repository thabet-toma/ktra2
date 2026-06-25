import React, { createContext, useCallback, useContext, useState } from 'react';
import { ConfirmDialog, type ConfirmDialogProps } from '../components/common/ConfirmDialog';

type ConfirmOptions = Omit<ConfirmDialogProps, 'onConfirm' | 'onCancel'>;
type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

/** حوار تأكيد موحّد: `const confirm = useConfirm(); if (!(await confirm({message}))) return;` */
export const useConfirm = (): ConfirmFn => {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider');
  return ctx;
};

export const ConfirmProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<{ opts: ConfirmOptions; resolve: (v: boolean) => void } | null>(null);

  const confirm = useCallback<ConfirmFn>(
    (opts) => new Promise<boolean>((resolve) => setState({ opts, resolve })),
    [],
  );

  const close = (value: boolean) => {
    setState((s) => { s?.resolve(value); return null; });
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <ConfirmDialog
          {...state.opts}
          onConfirm={() => close(true)}
          onCancel={() => close(false)}
        />
      )}
    </ConfirmContext.Provider>
  );
};
