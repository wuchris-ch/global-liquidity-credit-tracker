// A hosted frontend must have a configured research service before exposing it.
export const researchEnabled =
  process.env.NODE_ENV === "development" ||
  Boolean(process.env.NEXT_PUBLIC_RESEARCH_API_URL?.trim());
