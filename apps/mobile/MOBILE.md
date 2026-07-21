# ClearPath Mobile (Expo) — Architecture & Handoff

**Status:** Phase 5 scaffolding slice. This establishes the foundation — project
config, the monorepo integration, secure session storage, a typed API client,
the auth context, and the first end-to-end screen (login → home). It is
**not yet runtime-verified on a device and has no CI lane** (see
[Verification & CI](#verification--ci)). Everything here is written to be
correct-by-construction against the shared contracts and the FastAPI backend.

The goal of this document is that a mobile developer (or Codex, or a future
session) can pick this up and ship a genuinely great mobile experience without
re-deriving decisions. Read it top to bottom once.

---

## 1. What the mobile app is

A native iOS/Android app (Expo managed workflow, React Native, Expo Router)
that is a **first-class client of the same FastAPI backend** the web app uses.
It reuses the shared monorepo packages so the API contract is identical across
web and mobile:

- `@clearpath/api-client` — the generated, typed openapi-fetch client (one source
  of truth for every request/response shape; regenerated from the API's OpenAPI).
- `@clearpath/validation` — the shared Zod schemas/contracts.
- `@clearpath/design-tokens` — shared design language (see [Design system](#6-design-system)).

### The one architectural difference from web: no BFF, bearer tokens

| | Web (`apps/web`) | Mobile (`apps/mobile`) |
|---|---|---|
| Server tier | Next.js BFF routes (`app/api/**`) | **None** — the app calls the API directly |
| Session transport | httpOnly session **cookie**, forwarded by the BFF | **JWT `Authorization: Bearer`** header |
| Token storage | Browser cookie (managed by the server) | **Device secure enclave** (iOS Keychain / Android Keystore) via `expo-secure-store` |
| CSRF | Cookie-based concern | N/A (bearer tokens aren't sent ambiently) |

The FastAPI `get_principal` dependency already accepts `Authorization: Bearer
<token>` (see `apps/api/app/dependencies.py`), and `POST /v1/auth/login` returns
an `access_token`. So mobile is fully supported by the existing backend — **no
API changes are needed** for the auth foundation.

This is why there is no `app/api/**` folder here like there is on web: the
screens talk to `clearPathClient()` directly.

---

## 2. Directory structure

```
apps/mobile/
  app/                      # Expo Router (file-based routes)
    _layout.tsx             # Root: SafeAreaProvider + AuthProvider + Stack
    index.tsx               # Launch gate: spinner → redirect to (app) or (auth)
    (auth)/
      login.tsx             # Login screen (implemented)
    (app)/
      index.tsx             # Authenticated home (implemented, minimal)
  lib/
    api.ts                  # Typed client + bearer middleware + apiErrorMessage
    session-store.ts        # Secure token save/load/clear (Keychain/Keystore)
    auth-context.tsx        # AuthProvider/useAuth: signIn, signOut, refresh, session state
    theme.ts                # Minimal theme (to be sourced from design-tokens later)
  app.json                  # Expo config (name, scheme, plugins, extra.clearpathApiUrl)
  babel.config.js           # babel-preset-expo
  metro.config.js           # monorepo-aware Metro (watches workspace root, symlinks)
  tsconfig.json             # extends expo/tsconfig.base, @/* path alias
  package.json              # Expo deps + workspace refs to @clearpath/*
  MOBILE.md                 # this document
```

---

## 3. Setup & running (activation)

The mobile app is intentionally **excluded from the pnpm workspace** right now
(`pnpm-workspace.yaml` lists `apps/web` and `packages/*`, not `apps/mobile`).
This keeps the web/domain CI jobs' `pnpm install --frozen-lockfile` green,
because adding the React Native / Expo dependency tree requires regenerating the
lockfile. **Activation is a deliberate, one-time step:**

1. **Add mobile to the workspace.** In `pnpm-workspace.yaml`, add `- "apps/mobile"`
   under `packages:`.
2. **Install.** From the repo root: `pnpm install`. This resolves the Expo/RN
   tree and links the `@clearpath/*` workspace packages into the app. Commit the
   updated `pnpm-lock.yaml`.
3. **Verify the shared packages resolve.** `pnpm --filter @clearpath/mobile typecheck`.
   (Until this is done, editors will flag the `expo-*` / `react-native` imports as
   unresolved — that's expected for the un-installed scaffold.)
4. **Run it.** From `apps/mobile`:
   - `pnpm start` then press `i` (iOS simulator, macOS only) / `a` (Android
     emulator) / `w` (web preview), or scan the QR with Expo Go.
5. **Point it at the API.** Start the FastAPI backend (`apps/api`) on
   `127.0.0.1:8000`. The base URL resolves in this order:
   `EXPO_PUBLIC_API_URL` env → `app.json` `extra.clearpathApiUrl` → the
   `127.0.0.1:8000` default. **On a physical device, `127.0.0.1` is the phone**,
   not your dev machine — set `EXPO_PUBLIC_API_URL` to your machine's LAN IP
   (e.g. `http://192.168.1.20:8000`), or use a tunnel.

### Seeding a demo login
The backend has a demo account (`clearpath seed-demo`):
`demo@clearpath.local` / `SampleVault123!`. Note: that user was seeded with MFA
skipped, so `next_step` will be `dashboard` after login — a clean happy path for
first testing.

---

## 4. Auth flow

`login.tsx` → `useAuth().signIn(email, password, staySignedIn)`:

1. `POST /v1/auth/login` with `{ email, password, stay_signed_in }`.
2. On success the API returns `AuthLoginResponse`: `access_token`, `mfa_verified`,
   `requires_mfa`, `next_step`, `user`, `principal`.
3. The token is written to the secure enclave (`saveSessionToken`).
4. Routing is driven by `next_step` (enum: `mfa_verify`, `mfa_setup`,
   `select_plan`, `onboarding`, `dashboard`). Only a **fully MFA-verified** token
   grants resource access; the home screen loads `/v1/me` to confirm.

**On launch**, `AuthProvider.refresh()` reads the stored token and calls
`/v1/me`; a valid token → signed-in, a rejected/expired token → signed-out. The
API client middleware clears the token on any `401`.

**Not yet built (follow-up slices), all backed by existing API endpoints:**
`mfa_verify` / `mfa_setup` (`/v1/auth/mfa/*`), `select_plan` (`/v1/billing/*`),
`onboarding` (`/v1/onboarding/*`), registration (`/v1/auth/register`), and
password reset (`/v1/auth/password-reset/*`). The `next_step` routing contract is
already visible in `login.tsx` (it surfaces the pending step) so wiring each
screen is mechanical.

---

## 5. Screen roadmap (build order)

Every screen maps to an existing web workspace and the same API endpoints, so
the data contracts are already settled in `@clearpath/api-client`. Suggested
order, chosen for user value and dependency:

| # | Screen | API | Web reference | Notes for a great UX |
|---|---|---|---|---|
| 0 | **Login** ✅ | `POST /v1/auth/login` | `apps/web/app/login` | Done. Add biometric unlock next (see §7). |
| 1 | **MFA verify/setup** | `/v1/auth/mfa/*` | web mfa screens | TOTP + email code; large tap targets, autofill OTP. |
| 2 | **Register + onboarding** | `/v1/auth/register`, `/v1/onboarding/*` | web register/onboarding | Multi-step, save-as-you-go, native pickers. |
| 3 | **Today / Dashboard** | `GET /v1/dashboard` | web dashboard | The home surface — safe-to-spend hero, accounts, budgets, upcoming cash, insights. Pull-to-refresh. |
| 4 | **Transactions** | `/v1/transactions*` | web transactions | Infinite scroll, swipe to categorize, native search. |
| 5 | **Budgets / Monthly plan** | `/v1/monthly-plan`, `/v1/budgets*` | web monthly-plan | Section tabs; progress rings. |
| 6 | **Cash projections** | `/v1/cash-projections*` | web cash-projections | Chart; the calendar-feed value prop shines on mobile. |
| 7 | **Subscriptions** | `/v1/subscriptions*` | web subscriptions | Detected vs manual; manage-links open in-app browser. |
| 8 | **Goals / Loans / Retirement** | `/v1/goals`, `/v1/loan-plans*`, `/v1/retirement-plan*` | web equivalents | Feature-gated (see `me.feature_access`). |
| 9 | **Subscriptions/AI planner** | `/v1/planner/*` | web planner | Premier gating; streaming-feel responses. |
| 10 | **Settings + billing** | `/v1/me/settings`, `/v1/billing/*` | web settings/billing | Billing → Stripe-hosted pages via in-app browser (card data never touches the app — same PCI SAQ-A boundary as web). |
| 11 | **Plaid Link (native)** | `/v1/plaid/*` | web plaid | Use `react-native-plaid-link-sdk`; the token/consent flow mirrors decision 12. |

**Feature gating:** `/v1/me` returns `feature_access[]` (feature, enabled,
hidden, required_plan). Gate nav and screens on it exactly as the web app does,
so plan tiers behave identically.

---

## 6. Design system

`lib/theme.ts` is a deliberately small placeholder that matches the web
landing/auth palette (accent `#2d6cdf`, neutrals). **Next step:** source it from
`@clearpath/design-tokens` so web and mobile share one visual language — export
the raw token values from that package (they currently target CSS) and map them
to a React Native theme object here. Keep spacing on the 8pt grid
(`theme.spacing(n)`), respect the OS light/dark setting (`userInterfaceStyle:
automatic` is already set), and prefer native components/gestures over
web-like layouts.

---

## 7. UX principles for a great mobile experience

These are the things that make the app feel native rather than a wrapped
website — worth doing deliberately:

- **Biometric unlock.** After first login, offer Face ID / fingerprint
  (`expo-local-authentication`) to re-authorize using the stored token, instead
  of retyping the password. The token already lives in the enclave.
- **Pull-to-refresh + optimistic UI** on data screens; never a full-screen
  spinner after the first load.
- **Offline-tolerant reads.** Cache the last dashboard/transactions payload so a
  cold launch shows something instantly, then refreshes.
- **Native affordances.** Swipe actions on transactions, bottom-sheet modals,
  haptics on key confirmations, system share sheet for exports.
- **Push notifications** (`expo-notifications`) for cash-projection warnings and
  budget thresholds — a big reason people keep a finance app installed.
- **Deep links** (`scheme: clearpath`) for the household-invite accept flow and
  Stripe/Plaid returns — the `scheme` is already configured.
- **Keep money off the device.** Billing and Plaid credential entry happen on
  Stripe-/Plaid-hosted surfaces opened via an in-app browser, preserving the
  same PCI SAQ-A and no-custody boundaries the backend enforces.
- **Accessibility.** Dynamic type, VoiceOver/TalkBack labels, ≥44pt targets.

---

## 8. Verification & CI

**Current state:** this scaffold has **not** been run in a simulator and is
**not** covered by CI. That is expected for a first scaffolding slice and is
called out honestly so no one assumes green.

To close the gap:

1. **Activate** into the workspace (§3) and confirm
   `pnpm --filter @clearpath/mobile typecheck` passes (the app's TS is written
   against the shared contracts; the Expo/RN imports only resolve post-install).
2. **Add a mobile CI job** to `.github/workflows/api.yml` mirroring the `web`
   job: install, `typecheck`, `lint`, and `test` (jest). Do **not** add a native
   build to the PR lane — use **EAS Build** on demand/release.
3. **Add jest** (`jest-expo` preset) and unit-test the pure logic first:
   `lib/session-store` (mock `expo-secure-store`), `lib/api` error mapping, and
   `auth-context` reducer behavior.
4. **Manual device pass:** iOS simulator + Android emulator + one physical device
   (for the LAN API URL and secure-store enclave behavior).

---

## 9. Accounts, tooling & Windows development

You do **not** need any paid account to build and test the bulk of this app.
Here's exactly what each account/tool is for and *when* to get it.

### Apple Developer Program — ~$99/year
Needed for: installing a **custom dev client / native build on a physical
iPhone**, **TestFlight** beta distribution, and **App Store** submission. NOT
needed for the iOS Simulator (macOS-only, free) or for **Expo Go on a real
iPhone** (free). Buy it when you're ready to test native-module features on a
real iPhone or start a beta. **Start enrollment early** — Apple does identity
verification and it can take a day to (for a business/D-U-N-S entity) up to a
couple of weeks; there's no downside to having it ready ahead of time.

### Google Play Developer — $25 one-time
Needed for: Play Console **test tracks** (internal/closed/open) and **store
submission**. NOT needed for local/dev-client/APK testing or the Android
emulator. **Gotcha:** newer *personal* Play accounts must run a **closed test
with ~20 testers for ~14 days before promoting to production** — a real 2-week
tax on *launch* (not dev). Verify the current Play policy when you enroll and
plan the launch timeline around it.

### Expo / EAS — free for development; no paid subscription required
- The **Expo SDK, Expo Go, Expo Router, and CLI are free/open-source.**
  Everything in this scaffold runs on that with no account.
- An **Expo account is free.** You only need it (reactivated) to use **EAS**
  (cloud Build / Submit / Update). EAS has a **free tier**; a paid EAS plan only
  matters for build *priority* or higher build volume.
- You can avoid EAS entirely by building **locally** (`eas build --local` /
  `expo run:*`) — but see the Windows note for the iOS caveat.
- **Bottom line:** reactivate the free Expo account when you reach EAS cloud
  builds; do not pay for a subscription for dev/test.

### Developing on Windows (this repo's dev machine)
Windows **cannot run the iOS Simulator** (macOS/Xcode only). This shapes the iOS
path:
- **iOS dev loop:** use **Expo Go on a physical iPhone** (free; connects to the
  Windows PC over LAN or an Expo tunnel).
- **iOS binaries** (dev client, TestFlight, store): use **EAS Build in the
  cloud** (compiles iOS without a Mac) — which is the point where the **Apple
  Developer account becomes necessary**. So on Windows the Apple account matters
  a bit sooner if you want native-module testing on a real iPhone beyond Expo Go.
- **Android** is unaffected: the emulator runs on Windows; no account needed
  until Play testing.
- Optional: a Mac or a cloud-Mac service if you want a local iOS simulator — not
  required.

### "When to buy" summary
| Milestone | Apple ($99/yr) | Google Play ($25) | Expo account |
|---|---|---|---|
| Scaffold + screen dev (Expo Go / emulator) | no | no | no |
| First EAS cloud build | no | no | free acct |
| Native-module test on real iPhone (Windows -> EAS) | **yes** | no | free acct |
| Beta (TestFlight / Play internal test) | **yes** | **yes** | free acct |
| Store submission | yes | yes | free acct |

---

## 10. Build & release (later)

- Use **EAS Build** (`eas build`) for store binaries; keep it out of PR CI.
- Config per environment via EAS profiles / `EXPO_PUBLIC_API_URL`
  (dev → staging → prod API).
- Bundle identifiers are set: iOS `com.clearpathfinance.app`, Android
  `com.clearpathfinance.app`.
- App Store review notes: the app reads financial data (Plaid) and uses
  Stripe-hosted billing; no card data or money movement in-app (see the
  no-custody + PCI SAQ-A policies ported to the web app).

---

## 11. Decisions & risks (for the drift-check / cutover)

- **Bearer-token session** (vs web cookies) is the deliberate mobile model; it
  uses only existing API capabilities. If the API ever shortens token lifetime or
  adds refresh tokens, add a refresh flow here.
- **`ETHICS_POLICY_VERSION`, plan tiers, and feature gating** come from the API
  (`/v1/me`), so mobile inherits them automatically — no duplication.
- **Excluded-from-workspace** is a CI-safety choice, not a permanent one; activate
  it as the first real mobile slice. Until then, `pnpm-lock.yaml` is unaffected.
- **No runtime verification yet** — treat every screen as "written, not proven"
  until the device pass in §8.
