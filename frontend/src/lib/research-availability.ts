// Private workbench requires a service; other deployments show the public atlas.
export const researchEnabled =
  process.env.NODE_ENV === "development" ||
  Boolean(process.env.NEXT_PUBLIC_RESEARCH_API_URL?.trim());
