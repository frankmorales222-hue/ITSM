"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "./Toast";
import { useModalClose } from "./Modal";
import type { AjaxAction } from "./AjaxForm";

interface WidgetDef {
  key: string;
  label: string;
}

// No drag-and-drop library — up/down buttons reorder a local array, and
// checkboxes control visibility. "Save" submits the final (visible-only)
// order as JSON to the server action.
export default function DashboardCustomizer({
  widgets,
  initialOrder,
  initialVisible,
  action,
}: {
  widgets: WidgetDef[];
  initialOrder: string[];
  initialVisible: string[];
  action: AjaxAction;
}) {
  const [order, setOrder] = useState(initialOrder);
  const [visible, setVisible] = useState(() => new Set(initialVisible));
  const [isPending, startTransition] = useTransition();
  const router = useRouter();
  const showToast = useToast();
  const closeModal = useModalClose();

  function move(key: string, dir: -1 | 1) {
    setOrder((prev) => {
      const idx = prev.indexOf(key);
      const nextIdx = idx + dir;
      if (nextIdx < 0 || nextIdx >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[nextIdx]] = [next[nextIdx], next[idx]];
      return next;
    });
  }

  function toggle(key: string) {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function handleSave() {
    const formData = new FormData();
    formData.set("order", JSON.stringify(order.filter((k) => visible.has(k))));

    startTransition(async () => {
      const result = await action(formData);
      if (result && "error" in result && result.error) {
        showToast(result.error, "error");
        return;
      }
      showToast("Dashboard updated.", "success");
      closeModal?.();
      router.refresh();
    });
  }

  return (
    <div>
      {order.map((key, i) => {
        const def = widgets.find((w) => w.key === key);
        if (!def) return null;
        return (
          <div
            key={key}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}
          >
            <input
              type="checkbox"
              checked={visible.has(key)}
              onChange={() => toggle(key)}
              style={{ width: "auto" }}
              aria-label={`Show ${def.label}`}
            />
            <span style={{ flex: 1 }}>{def.label}</span>
            <button
              type="button"
              className="secondary"
              disabled={i === 0}
              onClick={() => move(key, -1)}
              style={{ padding: "2px 8px" }}
              aria-label={`Move ${def.label} up`}
            >
              &uarr;
            </button>
            <button
              type="button"
              className="secondary"
              disabled={i === order.length - 1}
              onClick={() => move(key, 1)}
              style={{ padding: "2px 8px" }}
              aria-label={`Move ${def.label} down`}
            >
              &darr;
            </button>
          </div>
        );
      })}
      <button type="button" onClick={handleSave} disabled={isPending} style={{ marginTop: 12 }}>
        Save
      </button>
    </div>
  );
}
