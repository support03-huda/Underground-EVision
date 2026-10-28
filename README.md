### Underground

Evision underground module 

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app underground
```

### What it does

UG Fiber ERP: tracks every Airtel underground fiber site from PO receipt (Day 0) to
punch-point-free handover within 180 days. Workspace: **Underground**.

- **UG Site** — one per node, with tabs per stage: PO → KMZ & Survey → SLD & Exceptions →
  CWIP / ROW / Job ID / VLC → Material → Execution → FF1 / PP / ATC → Closure & Billing.
- **Airtel PO** — attach the PO PDF from Airtel's email and the PO number, date, NFA, lines,
  GST and node IDs fill in; *Create / Update Sites* puts the lines on the matching UG Sites
  (by Node ID) or creates them. A rate-revision or length-amendment PO marks the replaced PO's
  lines superseded.
- **ROW Application** (one per authority), **UG Daily Progress** (one per site per day),
  **UG Material Order** / **UG Material Dispatch** (split by site), **UG Punch Point**.
- Masters, including **UG Stage SLA** (day window per stage) and **UG Settings** (alert days,
  trench depth, retention %).
- Gates refuse out-of-order steps (Job ID before ROW, VLC before Job ID approval, release
  before readiness, FF1 before testing, invoice before Billing Ready, handover with open PP).
- A nightly job (06:30) recalculates ageing and sends alert digests by email and in-app.
- Each team edits only its own part of UG Site (permission levels); Project Managers see only
  their own sites. Give users the `UG …` roles and link them as `ERP User` on **UG Employee**.

Apply changes on the server:

```bash
cd ~/frappe-bench
bench --site ug.local migrate
bench --site ug.local enable-scheduler
bench restart
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/underground
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
