// Friendly names for the backend's types. schema.d.ts is generated from the
// backend's OpenAPI schema: never edit it by hand, regenerate it with
// `npm run gen:api-types` (backend running locally with APP_ENV=development,
// so the development-only routes are included).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type QueryRequest = Schemas["QueryRequest"];
export type QueryResponse = Schemas["QueryResponse"];
export type Citation = Schemas["CitationOut"];
export type Me = Schemas["MeResponse"];
export type DevUser = Schemas["DevUser"];

// The backend types `source` as a plain string; these are the values it uses
// (documents.source CHECK constraint, migration 0002).
export type SourceName = "slack" | "drive" | "jira" | "confluence";
