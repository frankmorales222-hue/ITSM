"use client";

import { useRef, useTransition, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "./Toast";
import { useModalClose } from "./Modal";

export type AjaxAction = (formData: FormData) => Promise<{ error?: string } | void>;

// Submits a Server Action without a full-page redirect: on success it
// shows a toast, resets the form, and does a soft `router.refresh()` (the
// current route's Server Components re-render in place — no scroll reset,
// no loading skeleton flash) instead of the redirect()-driven navigation
// every form used before. On failure it shows the error as a toast instead
// of a `?error=` query param the page has to read back out.
export default function AjaxForm({
  action,
  successMessage,
  children,
  className,
  style,
  onSuccess,
  resetOnSuccess = true,
}: {
  action: AjaxAction;
  successMessage: string;
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onSuccess?: () => void;
  resetOnSuccess?: boolean;
}) {
  const [isPending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();
  const showToast = useToast();
  const closeModal = useModalClose();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);

    startTransition(async () => {
      const result = await action(formData);
      if (result && "error" in result && result.error) {
        showToast(result.error, "error");
        return;
      }
      showToast(successMessage, "success");
      if (resetOnSuccess) {
        formRef.current?.reset();
      }
      onSuccess?.();
      closeModal?.();
      router.refresh();
    });
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className={className} style={style} aria-busy={isPending}>
      <fieldset disabled={isPending} style={{ border: "none", padding: 0, margin: 0 }}>
        {children}
      </fieldset>
    </form>
  );
}
