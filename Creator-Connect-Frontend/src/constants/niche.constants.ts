export const NICHE_OPTIONS = [
    "Any",
    "Fashion",
    "Beauty",
    "Fitness",
    "Food",
    "Travel",
    "Tech",
    "Gaming",
    "Entertainment",
    "Music",
    "Photography",
    "Finance",
] as const;

export type NicheOption = typeof NICHE_OPTIONS[number];
