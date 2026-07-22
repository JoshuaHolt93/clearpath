import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { mapSettings } from "./settings";

/**
 * Validates the settings mapper against a REAL /v1/me/settings + /v1/me
 * response captured from the API test client, not a hand-written fixture.
 *
 * The hand-written fixture in settings-workspace.test.tsx was authored to match
 * the Zod schema rather than the API, so it asserted a `plaidStatus.configured`
 * field the API has never sent. The suite stayed green while the Settings tab
 * was completely broken in production.
 *
 * Regenerate after changing the settings response:
 *   see clearpath-notes/codex-handoff-2026-07-21.md (contract probe)
 */
describe("settings contract (captured API response)", () => {
  const raw = JSON.parse(
    readFileSync(path.resolve(__dirname, "__fixtures__", "settings-api-response.json"), "utf8"),
  ) as { settings: Parameters<typeof mapSettings>[0]; me: Parameters<typeof mapSettings>[1] };

  it("maps a real response without contract errors", () => {
    const result = mapSettings(raw.settings, raw.me);
    expect(result.success ? [] : result.error.issues).toEqual([]);
  });

  it("plaid_status carries ready but not configured", () => {
    // Pins the actual API shape so a schema demanding `configured` fails here.
    const status = raw.settings.plaid_status as Record<string, unknown>;
    expect(status).toHaveProperty("ready");
    expect(status).not.toHaveProperty("configured");
  });
});
