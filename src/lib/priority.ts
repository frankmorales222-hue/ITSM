type Impact = "high" | "medium" | "low";
type Urgency = "high" | "medium" | "low";
type Priority = "critical" | "high" | "medium" | "normal" | "low";

// Matrix from the source spec, section 6.
const MATRIX: Record<Impact, Record<Urgency, Priority>> = {
  high: { high: "critical", medium: "high", low: "medium" },
  medium: { high: "high", medium: "medium", low: "low" },
  low: { high: "medium", medium: "low", low: "low" },
};

export function calculatePriority(impact: Impact, urgency: Urgency): Priority {
  return MATRIX[impact][urgency];
}

// Lowest to highest — used to bump a ticket's priority on escalation.
const PRIORITY_ORDER: Priority[] = ["low", "normal", "medium", "high", "critical"];

export function bumpPriority(priority: string): Priority {
  const index = PRIORITY_ORDER.indexOf(priority as Priority);
  if (index === -1) return "normal";
  return PRIORITY_ORDER[Math.min(index + 1, PRIORITY_ORDER.length - 1)];
}
