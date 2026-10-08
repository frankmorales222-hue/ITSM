"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

// A function can't be passed as a prop from a Server Component to a
// Client Component (only plain JSX/serializable values can cross that
// boundary) — so "close the modal on success" is threaded through context
// instead of a render-prop, letting the page just pass ordinary JSX
// children built on the server.
const ModalCloseContext = createContext<(() => void) | null>(null);

export function useModalClose(): (() => void) | null {
  return useContext(ModalCloseContext);
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// A button that opens `children` in a modal.
export default function ModalTrigger({
  label,
  title,
  buttonClassName,
  children,
}: {
  label: string;
  title: string;
  buttonClassName?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" className={buttonClassName} onClick={() => setOpen(true)}>
        {label}
      </button>
      {open && (
        <Modal title={title} onClose={() => setOpen(false)}>
          <ModalCloseContext.Provider value={() => setOpen(false)}>{children}</ModalCloseContext.Provider>
        </Modal>
      )}
    </>
  );
}
