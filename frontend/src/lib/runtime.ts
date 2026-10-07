const configuredApiBase = import.meta.env.VITE_API_BASE?.trim();

if (import.meta.env.PROD && !configuredApiBase) {
  throw new Error("VITE_API_BASE is required for production builds");
}

export const API_BASE = (
  configuredApiBase ?? "http://localhost:8000"
).replace(/\/$/, "");

export const PAPER_API_BASE = (
  import.meta.env.VITE_PAPER_API_BASE?.trim() || API_BASE
).replace(/\/$/, "");

export const INSTITUTION_API_BASE = (
  import.meta.env.VITE_INSTITUTION_API_BASE?.trim() || API_BASE
).replace(/\/$/, "");

// Mock data is a local-development aid only. A production build must always
// fail closed against its configured API instead of rendering sample records.
export const USE_MOCK =
  import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true";
