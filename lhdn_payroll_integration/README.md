### LHDN Payroll Integration

LHDN MyInvois payroll e-Invoice compliance

### Desk Workspace Notes

In this repo's current local Desk setup (`http://localhost:8080/desk`), the user-facing workspace labels have been curated.

- The payroll compliance workspace remains `LHDN Payroll`.
- The MyInvois / Malaysia compliance area is surfaced as `E-Invoice` on Desk.
- The current Desk home also exposes curated top-level tiles including `Framework`, `ESS Mobile`, `Accounting`, `ERP Settings`, and `HR`.

When updating docs, screenshots, or test narratives, prefer these visible Desk labels over older raw workspace names from saved HTML dumps.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app lhdn_payroll_integration
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/lhdn_payroll_integration
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
