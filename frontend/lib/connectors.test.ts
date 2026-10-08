import { describe, expect, it } from "vitest";

import { connectedLabel, isConnectorId, oauthErrorMessage } from "./connectors";

describe("oauthErrorMessage", () => {
  it.each(["access_denied", "provider_error", "invalid_state", "account_mismatch", "no_company", "missing_permission"])(
    "the backend's %s code has a message",
    (code) => {
      expect(oauthErrorMessage(code)).toBeTruthy();
    },
  );

  it.each([
    ["<script>alert(1)</script>"],
    ["constructor"],
    ["__proto__"],
    ["Your account is locked, call 555"],
    [""],
    [undefined],
  ])("%j shows nothing, so a crafted link cannot put text on the page", (code) => {
    expect(oauthErrorMessage(code)).toBeUndefined();
  });

  it("a repeated parameter shows nothing", () => {
    expect(oauthErrorMessage(["access_denied", "provider_error"])).toBeUndefined();
  });
});

describe("connectedLabel", () => {
  it("names the three OAuth providers", () => {
    expect(connectedLabel("google")).toBe("Google Drive");
    expect(connectedLabel("slack")).toBe("Slack");
    expect(connectedLabel("atlassian")).toBe("Jira and Confluence");
  });

  it("ignores anything else", () => {
    expect(connectedLabel("evil")).toBeUndefined();
    expect(connectedLabel(["google"])).toBeUndefined();
  });
});

describe("isConnectorId", () => {
  it("accepts the four connectors", () => {
    for (const id of ["drive", "slack", "jira", "confluence"]) expect(isConnectorId(id)).toBe(true);
  });

  it("refuses anything that could change the backend path", () => {
    for (const id of ["", "drive/../x", "drive?x=1", "../health", "DRIVE", "toString", 5, null, undefined]) {
      expect(isConnectorId(id)).toBe(false);
    }
  });
});
