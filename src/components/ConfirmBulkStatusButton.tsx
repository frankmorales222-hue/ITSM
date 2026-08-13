"use client";

// Counts the checked "ticketIds" boxes in the enclosing form at click time
// so the confirmation reflects exactly what's about to change, since a
// bulk status change (unlike a single-ticket edit) has no per-item undo.
export default function ConfirmBulkStatusButton() {
  return (
    <button
      type="submit"
      className="secondary"
      onClick={(e) => {
        const form = e.currentTarget.closest("form");
        const count = form?.querySelectorAll('input[name="ticketIds"]:checked').length ?? 0;

        if (count === 0) {
          e.preventDefault();
          alert("Select at least one ticket first.");
          return;
        }

        const status = (form?.querySelector('select[name="bulkStatus"]') as HTMLSelectElement | null)?.value;
        const message = `Change status to "${status}" for ${count} selected ticket${count === 1 ? "" : "s"}?`;
        if (!confirm(message)) {
          e.preventDefault();
        }
      }}
    >
      Apply to selected
    </button>
  );
}
