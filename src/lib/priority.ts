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
