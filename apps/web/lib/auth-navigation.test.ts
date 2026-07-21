import { existsSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { AUTH_NEXT_STEP_PATHS } from "./auth-navigation";

const appDir = path.resolve(__dirname, "..", "app");

/**
 * Every auth next_step the API can return must resolve to a real page.
 *
 * `select_plan` previously mapped to /select-plan, which had no page: the API
 * returns that step for any user without a selected plan, so every newly
 * registered user hit a 404 immediately after MFA setup.
 */
describe("AUTH_NEXT_STEP_PATHS", () => {
  it.each(Object.entries(AUTH_NEXT_STEP_PATHS))(
    "%s -> %s has a page",
    (_step, route) => {
      const pageFile = path.join(appDir, route.replace(/^\//, ""), "page.tsx");
      expect(existsSync(pageFile), `missing ${path.relative(appDir, pageFile)}`).toBe(true);
    },
  );

  it("covers every step the API can return", () => {
    // Mirrors app/services/auth_service.py::_next_step_for_subject.
    expect(Object.keys(AUTH_NEXT_STEP_PATHS).sort()).toEqual(
      ["dashboard", "mfa_setup", "mfa_verify", "onboarding", "select_plan"].sort(),
    );
  });
});
