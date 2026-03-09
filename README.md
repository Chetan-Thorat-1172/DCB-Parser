# CIBIL Credit Report Parser

A deterministic, rule-based parser that converts **CIBIL Credit Report PDFs** into **clean structured JSON**.

## Architecture

```
PDF Input
    │
    ▼
┌──────────────────────┐
│  Stage 1: Extract    │  PyMuPDF Layout → JSON
│  Layout JSON         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Stage 2: Detect     │  Identify section boundaries
│  Sections            │  via known section headers
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Stage 3: Parse      │  Per-section rule-based parsers
│  Sections            │  using label→field mappings
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Stage 4: Assemble   │  Build structured CreditReport
│  Output              │  model and serialize to JSON
└──────────────────────┘
```

## Supported Sections

| Section | Fields Extracted |
|---------|-----------------|
| Consumer Information | name, date_of_birth, gender |
| CIBIL Score | score_name, score, scoring_factors |
| Identification | PAN, UID/Aadhaar |
| Telephones | type, number |
| Email Contacts | email_address |
| Addresses | address, category, residence_code, date_reported |
| Employment Information | account, type, date_reported, occupation_code, income |
| Summary | total_accounts, overdue, zero_balance, balances, enquiry counts |
| Accounts | member_name, account_number, type, dates, amounts, DPD history |
| Enquiries | member, date, purpose, amount |

## Usage

```bash
# Install
pip install -e .

# Parse a PDF
cibil-parser path/to/credit_report.pdf -o output.json

# Parse from pre-extracted layout JSON
cibil-parser --from-layout path/to/layout.json -o output.json
```

python -m cibil_parser.cli credit_sample.pdf -o output.json

## Extensibility

New report templates (Experian, Equifax, bank-specific) can be added by:
1. Creating a new template module under `templates/`
2. Registering section header patterns and field mappings
3. Adding a template detector function

## Design Principles

- **Deterministic**: Same input always produces same output
- **Rule-based**: No AI/ML — only structural rules and label mappings
- **Auditable**: Every extraction decision is traceable
- **Modular**: Each section has its own parser
- **Extensible**: Template registry supports multiple report formats
