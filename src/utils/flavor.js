import { FLAVOR_TERM_INDEX } from "../data/flavorWheel";

export function categorizeFlavorNotes(text) {
  if (!text) return [];
  const lower = text.toLowerCase();
  const matched = [];
  for (const { term, cat } of FLAVOR_TERM_INDEX) {
    if (lower.includes(term) && !matched.find((c) => c.en === cat.en)) {
      matched.push(cat);
    }
  }
  return matched;
}
