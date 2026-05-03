# Tax Saving Recommendation Agent — AIKR S2026

## Architecture

```
project/
├── backend/
│   ├── tax_agent.py      ← AI Agent (Knowledge Base + Inference Engine)
│   ├── app.py            ← Flask REST API server
│   └── requirements.txt
└── frontend/
    └── index.html        ← React UI (calls the backend API)
```

The **Python agent** and the **React frontend** are completely separate.
They communicate through a REST API:

```
React (browser)  →  POST /api/calculate  →  Flask  →  TaxSavingAgent  →  JSON response
```

---

## How to Run

### Step 1 — Start the Python Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The API server starts at: `http://localhost:5000`

You can verify it's running:
```
GET http://localhost:5000/api/health
```

### Step 2 — Open the React Frontend

Just open the file in your browser:
```
frontend/index.html
```
(double-click it, or drag it into Chrome/Firefox)

The frontend will automatically call `http://localhost:5000/api/calculate` when you submit.

---

## API Reference

### POST /api/calculate

**Request Body (JSON):**
```json
{
  "monthly_salary":   60000,
  "basic_pct":        40,
  "senior_self":      false,
  "monthly_rent":     12000,
  "is_metro":         false,
  "home_emi_monthly": 0,
  "edu_emi_monthly":  8000,
  "has_epf":          true,
  "ppf_annual":       0,
  "elss_annual":      0,
  "lic_annual":       24000,
  "nsc_annual":       0,
  "fd5yr_annual":     0,
  "nps_annual":       0,
  "health_self":      6000,
  "health_parents":   0,
  "senior_parents":   false,
  "savings_interest": 2000
}
```

**Response (JSON):**
```json
{
  "success": true,
  "data": {
    "gross_annual": 720000,
    "total_deductions": 289360,
    "best_regime": "OLD",
    "you_save": 0,
    "tax_old": { "taxable_income": 430640, "base_tax": 0, "rebate": 12500, "cess": 0, "total_tax": 0 },
    "tax_new": { "taxable_income": 670000, "base_tax": 0, "rebate": 25000, "cess": 0, "total_tax": 0 },
    "deductions": [...],
    "suggestions": [...],
    "fired_rules": ["STANDARD_DEDUCTION", "HRA", "80C", "80D", "80E", "80TTA"]
  }
}
```

---

## AI Tool Usage Declaration

| Field | Details |
|---|---|
| AI Tool Used | Claude (Anthropic) |
| Purpose | Code structure, docstrings, rule verification |
| AI-Generated | Initial scaffold, docstrings |
| Self-Written | Full tax logic, KB rules, inference engine, API, UI |
