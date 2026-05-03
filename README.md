# Tax Saving Recommendation Agent

## Project Description

Tax Saving Recommendation Agent is a Flask + React web application that helps users estimate Indian income tax, compare old and new tax regimes, and discover possible tax-saving recommendations.

The backend contains a rule-based tax agent with a knowledge base and inference engine. The frontend provides a browser-based form and interactive tax result view.

## Folder Structure

```txt
project/
|-- api/
|   |-- app.py              # Vercel Flask entrypoint and API routes
|   |-- tax_agent.py        # Tax knowledge base and inference engine
|   `-- requirements.txt
|-- backend/
|   |-- app.py              # Local/legacy backend copy
|   |-- tax_agent.py
|   `-- requirements.txt
|-- frontend/
|   `-- index.html          # React frontend
|-- requirements.txt        # Vercel/root Python dependencies
|-- vercel.json             # Vercel routing config
`-- README.md
```

## Installation Steps

1. Clone or download the project.

2. Open a terminal in the project root:

```bash
cd project
```

3. Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

## How to Run the Project

### Run Locally

From the project root:

```bash
python -m flask --app api.app run
```

Open the website in your browser:

```txt
http://127.0.0.1:5000/
```

Useful backend routes:

```txt
GET  /api
GET  /api/health
GET  /api/status
POST /api/calculate
POST /api/explore
```

### Deploy on Vercel

The project is configured for Vercel with `vercel.json`.

Vercel routes all requests to:

```txt
api/app.py
```

After deployment:

```txt
/              serves the frontend website
/api           backend health check
/api/calculate backend tax calculation endpoint
/api/explore   backend recommendation exploration endpoint
```

## Example Input/Output

### Example Request

`POST /api/calculate`

```json
{
  "monthly_salary": 60000,
  "basic_pct": 40,
  "senior_self": false,
  "monthly_rent": 12000,
  "is_metro": false,
  "home_emi_monthly": 0,
  "edu_emi_monthly": 8000,
  "has_epf": true,
  "ppf_annual": 0,
  "elss_annual": 0,
  "lic_annual": 24000,
  "nsc_annual": 0,
  "fd5yr_annual": 0,
  "nps_annual": 0,
  "health_self": 6000,
  "health_parents": 0,
  "senior_parents": false,
  "savings_interest": 2000
}
```

### Example Response

```json
{
  "success": true,
  "data": {
    "gross_annual": 720000,
    "total_deductions": 179120,
    "best_regime": "NEW",
    "you_save": 0,
    "tax_old": {
      "taxable_income": 540880,
      "base_tax": 20676,
      "rebate": 0,
      "surcharge": 0,
      "cess": 827,
      "total_tax": 21503
    },
    "tax_new": {
      "taxable_income": 670000,
      "base_tax": 0,
      "rebate": 25000,
      "surcharge": 0,
      "cess": 0,
      "total_tax": 0
    },
    "deductions": [],
    "suggestions": [],
    "structured_recs": [],
    "fired_rules": []
  }
}
```

Actual values may vary based on the user input and tax rules in `api/tax_agent.py`.

## Notes

- The Flask app entrypoint is `api/app.py`.
- The root route `/` serves the frontend website.
- API routes are available under `/api/...`.
- The project is designed to run safely on Vercel serverless functions.
