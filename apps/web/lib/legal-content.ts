// Public legal policy content ported verbatim from Flask policies.py at
// 92ccdbc (PRIVACY_POLICY, TERMS_OF_SERVICE). Route-map classifies these as
// web-only static content; they carry no API endpoint.

const CONTACT_EMAIL = "clearpathfinance1@proton.me";
const PUBLIC_LEGAL_POLICY_VERSION = "2026.05.14";

export type LegalPolicy = {
  title: string;
  version: string;
  effectiveDate: string;
  intro: string;
  contact?: string;
  sections: { heading: string; items: string[] }[];
};

export const PRIVACY_POLICY: LegalPolicy = {
  title: "ClearPath Privacy Policy",
  version: PUBLIC_LEGAL_POLICY_VERSION,
  effectiveDate: "2026-05-14",
  contact: `Contact ClearPath Finance at ${CONTACT_EMAIL} to submit privacy, access, correction, export, or deletion requests.`,
  intro:
    "ClearPath Finance provides personal finance planning tools for households. This Privacy Policy explains how ClearPath collects, uses, protects, shares, retains, and deletes information, including Plaid-connected bank data and user-entered financial planning data.",
  sections: [
    {
      heading: "Information We Collect",
      items: [
        "Account information such as email address, household name, authentication metadata, MFA status, policy acknowledgements, and security logs.",
        "Financial planning information you enter, including income assumptions, expenses, budgets, goals, debt, loan, mortgage, retirement, tax-planning settings, notes, and forecast items.",
        "Plaid-connected bank data when you choose to connect an institution, including account names, account type, institution, balances, transaction dates, amounts, merchant or description text, categories, pending status, and Plaid identifiers needed to sync data.",
        "CSV-imported transaction and account data that you upload directly.",
        "Billing status and Stripe identifiers if paid billing is enabled; ClearPath does not collect or store card numbers, CVV/CVC, or payment-card expiration details.",
      ],
    },
    {
      heading: "How We Use Financial Data",
      items: [
        "To provide disclosed product features such as dashboard summaries, transactions, budgets, subscriptions, goals, forecasts, analytics, account settings, and bank-account sync.",
        "To categorize transactions, detect consumer subscriptions, calculate safe-to-spend amounts, estimate cash flow, show net worth, and generate rules-based guidance.",
        "To maintain security, prevent fraud or unauthorized access, troubleshoot sync/import problems, and comply with applicable legal, security, and audit obligations.",
        "ClearPath does not sell Plaid-connected bank data or use it for unrelated billing, advertising, or non-product purposes.",
      ],
    },
    {
      heading: "Plaid And Connected Bank Data",
      items: [
        "Plaid is used only when you choose to connect a financial institution. Plaid may collect credentials or authentication information on Plaid-hosted surfaces according to Plaid's own policies.",
        "ClearPath stores encrypted Plaid access tokens and Plaid-linked account/transaction identifiers so it can refresh account and transaction data for your account.",
        "You can disconnect institutions or remove ignored accounts from Settings. Removing a connection may delete locally synced accounts and transactions tied to that institution.",
        "Live bank data may not update in real time. Sync timing can depend on Plaid, the financial institution, product settings, and any manual sync or background job configuration.",
      ],
    },
    {
      heading: "Sharing And Service Providers",
      items: [
        "ClearPath uses service providers only as needed to operate the product, such as Plaid for bank connectivity and Stripe for hosted billing if billing is enabled.",
        "ClearPath may disclose limited information when required by law, to protect users or the service, to investigate abuse or security events, or with your direction.",
        "ClearPath does not sell personal financial data.",
      ],
    },
    {
      heading: "Security",
      items: [
        "ClearPath uses authentication, MFA, CSRF protection, least-privilege ownership checks, security headers, HTTPS controls in production, encrypted Plaid tokens, and encrypted customer text fields where configured.",
        "No security control is perfect. You are responsible for protecting your password, MFA recovery codes, connected devices, and account access.",
        `Report suspected unauthorized access, inaccurate data, or security concerns to ClearPath Finance at ${CONTACT_EMAIL}.`,
      ],
    },
    {
      heading: "Retention, Access, Correction, And Deletion",
      items: [
        "ClearPath retains account and financial data while your account is active or as needed for the product, security, legal, backup, audit, or dispute-resolution purposes.",
        `You may request access, correction, export, or deletion of your account information by contacting ClearPath Finance at ${CONTACT_EMAIL}.`,
        "Deletion requests may be limited where retention is required for security logs, fraud prevention, legal obligations, backups, billing records, or dispute resolution.",
        "Disconnecting a Plaid institution stops future sync for that institution, but previously stored data may remain until removed or deleted according to app controls and retention requirements.",
      ],
    },
  ],
};

export const TERMS_OF_SERVICE: LegalPolicy = {
  title: "ClearPath Terms Of Service",
  version: PUBLIC_LEGAL_POLICY_VERSION,
  effectiveDate: "2026-05-14",
  intro:
    "These Terms of Service govern your use of ClearPath Finance. By creating an account or using ClearPath, you agree to use the service lawfully, responsibly, and only for personal finance organization and planning.",
  sections: [
    {
      heading: "Acceptable Use",
      items: [
        "Use ClearPath only for lawful personal or household financial organization, budgeting, forecasting, and planning.",
        "Do not attempt to access, copy, test, disrupt, reverse engineer, scrape, or interfere with another user's account, financial data, Plaid connection, billing records, or security controls.",
        "Do not upload malicious files, submit false or unlawful data, bypass authentication or MFA, misuse APIs, or use ClearPath to facilitate fraud, harassment, or illegal activity.",
      ],
    },
    {
      heading: "Financial Information Limitations",
      items: [
        "ClearPath provides informational budgeting tools, calculations, forecasts, and rules-based guidance only.",
        "ClearPath does not provide investment, legal, tax, accounting, credit, insurance, or financial advice and does not guarantee any financial outcome.",
        "Forecasts, safe-to-spend calculations, tax estimates, loan scenarios, subscription detection, retirement views, insights, and goals may be incomplete, delayed, inaccurate, or based on assumptions you should review.",
        "Consult a licensed professional before making financial, investment, tax, legal, lending, insurance, or retirement decisions.",
      ],
    },
    {
      heading: "Plaid, Bank Connectivity, And User Responsibilities",
      items: [
        "Bank connectivity is optional and depends on Plaid, your institution, network availability, and the permissions you grant.",
        "You are responsible for reviewing connected accounts, imported transactions, categories, balances, subscriptions, budgets, taxes, goals, and forecasts for accuracy.",
        "You may disconnect institutions through ClearPath settings where supported. Some institution or Plaid limitations may affect sync, account availability, or update timing.",
        "You authorize ClearPath to use Plaid-connected data only for disclosed product purposes such as dashboards, transactions, subscriptions, budgets, forecasts, account sync, and settings.",
      ],
    },
    {
      heading: "Accounts, Security, And Termination",
      items: [
        "You are responsible for maintaining the confidentiality of your password, MFA device, recovery codes, and account session.",
        "ClearPath may suspend or terminate access if your account appears compromised, violates these Terms, creates security risk, or is used unlawfully.",
        `You may stop using ClearPath at any time and may request account deletion by contacting ClearPath Finance at ${CONTACT_EMAIL}.`,
        "Some records may be retained as necessary for legal, security, backup, audit, billing, or dispute-resolution purposes.",
      ],
    },
    {
      heading: "Billing And Third-Party Services",
      items: [
        "If paid features are enabled, payment collection and payment-method updates are handled only on Stripe-hosted pages.",
        "ClearPath does not collect or store raw card numbers, CVV/CVC, or card expiration details.",
        "Third-party services such as Plaid and Stripe are governed by their own terms and privacy policies in addition to these Terms.",
      ],
    },
    {
      heading: "Liability Boundaries",
      items: [
        "ClearPath is provided as-is and as-available, without warranties that the service will be uninterrupted, error-free, perfectly accurate, or suitable for every financial situation.",
        "To the maximum extent permitted by law, ClearPath is not liable for indirect, incidental, consequential, special, punitive, lost-profit, lost-data, financial-loss, or reliance damages arising from use of the service.",
        "You remain responsible for final financial decisions, account management, payments, taxes, debts, investments, and professional-advice decisions.",
      ],
    },
    {
      heading: "Changes To These Terms",
      items: [
        "ClearPath may update these Terms as the product, legal requirements, security controls, or third-party integrations change.",
        "Material updates may require renewed acknowledgement before continued use of authenticated product areas.",
      ],
    },
    {
      heading: "Contact Us",
      items: [
        `Questions about these Terms, your account, billing, or security concerns can be sent to ClearPath Finance at ${CONTACT_EMAIL}.`,
      ],
    },
  ],
};
