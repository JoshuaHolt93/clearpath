// Ethics + security/compliance policy content ported from Flask policies.py at
// 92ccdbc (ethics.html, INFORMATION_REQUIREMENTS_POLICY, PCI_SAQ_A_POLICY,
// MTL_IMPACT_REGISTER). Route-map classifies these as web-only static content.

import type { LegalPolicy } from "./legal-content";

const CONTACT_EMAIL = "clearpathfinance1@proton.me";

export const ETHICS_POLICY: LegalPolicy = {
  title: "ClearPath Ethics, Terms, and Privacy Policy",
  version: "2026-01",
  effectiveDate: "2026-01-01",
  intro:
    "ClearPath Finance exists to help households make clearer financial decisions. This policy complements the public Terms of Service and Privacy Policy so users can review one practical ethics commitment alongside launch-ready legal policies.",
  contact: `Report suspected security issues, inaccurate financial behavior, privacy concerns, or unethical use of the application to ClearPath Finance at ${CONTACT_EMAIL}.`,
  sections: [
    {
      heading: "Integrity And Ethical Conduct",
      items: [
        "ClearPath should present financial information honestly, avoid deceptive design, and make calculations understandable. Users are expected to provide accurate information, use the app lawfully, and avoid attempting to access another person's account or financial data.",
      ],
    },
    {
      heading: "Privacy And Security Responsibilities",
      items: [
        "Financial data deserves careful handling. ClearPath is designed to protect user information through authentication, authorization checks, encryption controls, and auditability. Users are responsible for protecting their passwords, reviewing connected accounts, and reporting suspicious access.",
      ],
    },
    {
      heading: "Conflicts Of Interest",
      items: [
        "ClearPath should prioritize the user's financial clarity over hidden incentives. Any future recommendations, integrations, referrals, or partner relationships should be disclosed plainly when they could influence user decisions.",
      ],
    },
    {
      heading: "Reporting Concerns",
      items: [
        "Users should report suspected security issues, inaccurate financial behavior, privacy concerns, or unethical use of the application to ClearPath Finance.",
      ],
    },
    {
      heading: "Acknowledgement",
      items: [
        "By acknowledging this policy, you confirm that you have reviewed these commitments and agree to use ClearPath in a lawful, ethical, and security-conscious manner. Signed-in users can acknowledge the current policy version from Settings.",
      ],
    },
  ],
};

export const INFORMATION_REQUIREMENTS_POLICY: LegalPolicy = {
  title: "Information Requirements for Security Practices",
  version: "2026.05.13",
  effectiveDate: "2026-05-13",
  owner: "ClearPath Finance Security Owner",
  reviewCadence: "Reviewed at least annually and after material security, product, or vendor changes.",
  sections: [
    {
      heading: "Identity And Access Information",
      summary:
        "ClearPath maintains the information needed to authenticate users, enforce account ownership, monitor privileged access, and investigate unauthorized access attempts.",
      items: [
        "User account identifiers, authentication metadata, and admin status are maintained to support access control.",
        "Login attempt and privileged access records are retained to support security review and incident investigation.",
        "Access checks must use user-scoped identifiers before financial records are displayed or changed.",
      ],
    },
    {
      heading: "Financial Data Protection Information",
      summary:
        "ClearPath tracks the security-relevant information needed to protect financial accounts, transactions, plans, goals, subscriptions, and Plaid-linked records.",
      items: [
        "Account, transaction, planning, subscription, and Plaid records must remain associated with the owning user.",
        "Sensitive customer text fields and Plaid access tokens require configured encryption controls before production use.",
        "Security-relevant changes to financial data should be attributable to an authenticated user or explicit background job scope.",
      ],
    },
    {
      heading: "Configuration And Operational Security Information",
      summary:
        "ClearPath defines and reviews the configuration values required to operate safely in development and production environments.",
      items: [
        "Production configuration must include stable secrets, HTTPS enforcement, secure cookies, and required encryption keys.",
        "Database migrations and startup schema controls must be reviewed before production deployment.",
        "Background jobs must be explicitly scoped to users, accounts, or an intentional all-user operation.",
      ],
    },
    {
      heading: "Vendor And Integration Information",
      summary:
        "ClearPath maintains the information needed to evaluate, configure, and monitor external integrations such as Plaid.",
      items: [
        "Plaid environment, credentials, products, and token-encryption configuration are tracked as security-sensitive settings.",
        "Connected institutions and ignored accounts must remain visible to the user for review and removal.",
        "Integration errors and sync outcomes should be handled without exposing sensitive tokens or unrelated user data.",
      ],
    },
    {
      heading: "Review, Retention, And Evidence",
      summary:
        "ClearPath keeps policy, acknowledgement, test, and audit evidence that supports periodic security review.",
      items: [
        "Policy versions and effective dates are maintained in code for deterministic review evidence.",
        "Automated tests verify key security controls before changes are accepted.",
        "Security control evidence should be reviewed when policy versions change or before production release.",
      ],
    },
  ],
};

export const PCI_SAQ_A_POLICY: LegalPolicy = {
  title: "PCI SAQ-A Cardholder Data Handling Policy",
  version: "2026.05.14",
  effectiveDate: "2026-05-14",
  owner: "ClearPath Finance Security And Compliance Owner",
  reviewCadence: "Reviewed at least annually, after Stripe billing changes, and before any production billing launch.",
  scope:
    "ClearPath is intended to remain in PCI SAQ-A scope by using Stripe-hosted Checkout and Stripe Billing Portal for all payment-card entry and updates. Stripe is the sole cardholder-data service provider; ClearPath must review Stripe's current Attestation of Compliance (AOC) at least annually and retain evidence of the review.",
  sections: [
    {
      heading: "Stripe-Only Card Handling",
      summary: "ClearPath users must enter or update payment-card details only on Stripe-hosted Checkout or Billing Portal pages.",
      items: [
        "ClearPath application pages must not render direct PAN, CVV/CVC, card-number, expiration-date, or equivalent card collection fields.",
        "Billing POST routes must reject submitted PAN, card-number, CVV/CVC, security-code, and expiration-field payloads before creating Stripe sessions or processing billing logic.",
        "ClearPath may persist only non-cardholder billing references such as Stripe customer id, Stripe subscription id, billing status, and configured Stripe price id.",
      ],
    },
    {
      heading: "No ClearPath Cardholder Data Processing",
      summary: "ClearPath servers must not receive, store, process, transmit, log, flash, serialize, or display PAN/CVV/cardholder data.",
      items: [
        "Application logging sanitizes card-shaped payloads and billing endpoints reject direct card submissions.",
        "Database models must not add PAN, CVV/CVC, full card number, track data, or raw payment-method fields.",
        "Error responses and user-facing messages must not echo submitted card values.",
      ],
    },
    {
      heading: "MFA And Privileged Payment Access",
      summary: "Payment administration access requires strong authentication outside ClearPath as well as inside the application.",
      items: [
        "All Stripe Dashboard users for ClearPath must have MFA enabled.",
        "All business bank accounts used for payouts, settlement, or operating funds must require MFA where supported by the financial institution.",
        "ClearPath application users are prompted to set up MFA and may opt out during account setup; users who enable MFA must complete it before accessing authenticated app areas.",
      ],
    },
    {
      heading: "Evidence And Annual Review",
      summary: "ClearPath maintains lightweight evidence for SAQ-A scope and Stripe service-provider oversight.",
      items: [
        "Automated tests must verify Stripe-hosted Checkout and Billing Portal flows remain the only payment-method entry/update paths.",
        "Automated tests must verify billing routes reject direct card data and templates do not render direct card inputs.",
        "The Stripe AOC review, Stripe Dashboard MFA confirmation, and business-bank MFA confirmation should be reviewed at least annually.",
      ],
    },
  ],
};

export const MONEY_TRANSMISSION_POLICY: LegalPolicy = {
  title: "No-Custody Money Transmission Scope Policy",
  version: "2026.05.16",
  effectiveDate: "2026-05-16",
  owner: "ClearPath Finance Compliance Owner",
  reviewCadence:
    "Reviewed before launch, at least annually, and before any balances, transfers, payment initiation, custody, wallet, stored-value, or third-party money movement feature ships.",
  scope:
    "ClearPath is a read-only personal finance planning product. ClearPath does not hold customer funds, move funds, initiate transfers, provide stored value, operate a wallet, or take custody of customer assets.",
  note:
    "Launch blocker: any feature that could enable balances as actionable funds, transfers, payment initiation, wallets, stored value, custody, or third-party money movement is blocked from launch until reviewed by qualified fintech counsel and approved by the compliance owner.",
  sections: [
    {
      heading: "Current Non-Money-Transmission Features",
      summary: "These shipped capabilities are read-only or hosted-billing and do not move or custody customer funds.",
      items: [
        "Dashboard And Budget Visibility — displays user-owned account, transaction, budget, goal, forecast, and analytics information for household planning. No funds are held, transferred, stored, or initiated by ClearPath.",
        "Plaid Account And Transaction Sync — uses Plaid-connected data to import account, balance, and transaction information for disclosed budgeting, subscription, planning, and settings purposes. Read-only data access does not authorize ClearPath to move, debit, credit, or custody customer funds.",
        "Forecasts, Goals, And Quick Planning — provides informational cash-flow forecasts, goal tracking, loan scenarios, tax estimates, subscription insights, and planning worksheets. Recommendations and calculations are informational only and do not execute payments or transfers.",
        "Stripe-Hosted Subscription Billing — uses Stripe-hosted Checkout and Billing Portal for ClearPath subscription payments when billing is enabled. Stripe is the payment processor for ClearPath fees; ClearPath does not collect card data or transmit customer funds between user accounts.",
      ],
    },
    {
      heading: "Future Or Prohibited Capabilities (Counsel Review Required)",
      summary: "Each of these is blocked from launch until reviewed by qualified fintech counsel and approved by the compliance owner.",
      items: [
        "Account Balances As Actionable Funds — treating displayed balances as funds users can move, allocate, reserve, sweep, spend, or disburse through ClearPath.",
        "Transfers — any ACH, RTP, wire, card, bank-to-bank, account-to-account, pull, push, sweep, or internal transfer capability.",
        "Payment Initiation — initiating bill payments, loan payments, subscription cancellation payments/refunds, merchant payments, or debt-paydown payments on behalf of users.",
        "Wallets Or Stored Value — maintaining a wallet balance, stored value, prepaid balance, ClearPath credit, user ledger balance, or redeemable value.",
        "Custody — holding, controlling, pooling, safeguarding, escrowing, or otherwise taking custody of customer cash, securities, crypto, or other assets.",
        "Third-Party Money Movement — moving money to, from, or between third parties, family members, advisors, merchants, lenders, billers, or external accounts.",
      ],
    },
  ],
};
