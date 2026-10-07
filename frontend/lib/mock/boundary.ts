/**
 * MOCK DATA for the boundary page's design preview (development only).
 *
 * The real boundary and sync API exists (backend/app/connectors/admin.py);
 * these fixtures stay only until /admin/boundary is wired to it. "In
 * boundary" entries mirror the seed's boundary table (backend/app/seed.py);
 * the others stand for channels and folders a connector can see but the
 * admin has not allowed, like the seed's HR folder.
 */

export type MockScope = {
  scopeId: string;
  title: string;
  scopeType: "channel" | "folder";
  detail: string;
  inBoundary: boolean;
};

export type MockSource = { source: "slack" | "drive"; label: string; scopes: MockScope[] };

export const MOCK_SOURCES: MockSource[] = [
  {
    source: "slack",
    label: "Slack",
    scopes: [
      { scopeId: "C_PAYONCALL", title: "#payments-oncall", scopeType: "channel", detail: "private", inBoundary: true },
      { scopeId: "C_ENG", title: "#eng", scopeType: "channel", detail: "public", inBoundary: true },
      { scopeId: "C_SECURITY", title: "#security-incidents", scopeType: "channel", detail: "private", inBoundary: true },
      { scopeId: "C_RANDOM", title: "#random", scopeType: "channel", detail: "public", inBoundary: false },
    ],
  },
  {
    source: "drive",
    label: "Google Drive",
    scopes: [
      { scopeId: "F_ENG", title: "Engineering", scopeType: "folder", detail: "folder", inBoundary: true },
      { scopeId: "F_SEC", title: "Security", scopeType: "folder", detail: "folder", inBoundary: true },
      { scopeId: "F_HR", title: "HR", scopeType: "folder", detail: "folder", inBoundary: false },
    ],
  },
];
