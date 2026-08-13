"use client";

// Wraps a plain submit button with a browser confirm() prompt, so a Server
// Action form still gets a confirmation step without needing client state
// or a modal library — cancelling the dialog just prevents the click's
// default form submission.
export default function ConfirmSubmitButton({
  message,
  children,
  className,
}: {
  message: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="submit"
      className={className}
      onClick={(e) => {
        if (!confirm(message)) {
          e.preventDefault();
        }
      }}
    >
      {children}
    </button>
  );
}
