"""
app.py — Flask API Server for Tax Saving Recommendation Agent
=============================================================
Endpoints:
  GET  /api/health       — health check
  POST /api/calculate    — full tax analysis from plain-language form data
  POST /api/explore      — iterative recommendation exploration + live recalculation
"""

from flask import Flask, request, jsonify
from tax_agent import TaxSavingAgent, TAX_KNOWLEDGE_BASE, InferenceEngine

app = Flask(__name__)

# ── CORS ─────────────────────────────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ── HEALTH ───────────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "agent": "TaxSavingAgent", "fy": "2024-25"})


# ── CALCULATE ─────────────────────────────────────────────────────────────────
@app.route("/api/calculate", methods=["POST", "OPTIONS"])
def calculate():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    body = request.get_json(force=True)

    plain_answers = {
        "monthly_salary":   float(body.get("monthly_salary",   0)),
        "basic_pct":        float(body.get("basic_pct",        40)),
        "senior_self":      bool(body.get("senior_self",       False)),
        "monthly_rent":     float(body.get("monthly_rent",     0)),
        "is_metro":         bool(body.get("is_metro",          False)),
        "home_emi_monthly": float(body.get("home_emi_monthly", 0)),
        "edu_emi_monthly":  float(body.get("edu_emi_monthly",  0)),
        "has_epf":          bool(body.get("has_epf",           False)),
        "ppf_annual":       float(body.get("ppf_annual",       0)),
        "elss_annual":      float(body.get("elss_annual",      0)),
        "lic_annual":       float(body.get("lic_annual",       0)),
        "nsc_annual":       float(body.get("nsc_annual",       0)),
        "fd5yr_annual":     float(body.get("fd5yr_annual",     0)),
        "nps_annual":       float(body.get("nps_annual",       0)),
        "health_self":      float(body.get("health_self",      0)),
        "health_parents":   float(body.get("health_parents",   0)),
        "senior_parents":   bool(body.get("senior_parents",    False)),
        "savings_interest": float(body.get("savings_interest", 0)),
    }

    try:
        agent     = TaxSavingAgent()
        percepts  = agent.perceive(plain_answers)
        reasoning = agent.reason(percepts)
        action    = agent.act(percepts, reasoning)

        deduction_list = []
        for d in reasoning["deductions"]:
            if d["amount"] > 0:
                item = {"label": d["label"], "amount": d["amount"]}
                if "breakdown" in d: item["breakdown"] = d["breakdown"]
                if "note"      in d: item["note"]      = d["note"]
                deduction_list.append(item)

        # ── Build structured recommendations ─────────────────────────────
        # Each recommendation carries enough context for the explore engine
        kb   = TAX_KNOWLEDGE_BASE
        p    = percepts
        used_80c = sum(p[k] for k in ["epf","ppf","elss","lic","nsc","fd5yr"])
        gap_80c  = max(0, kb["80C_LIMIT"]  - used_80c)
        gap_nps  = max(0, kb["NPS_EXTRA_LIMIT"] - p["nps"])

        structured_recs = []

        if gap_80c > 2000:
            structured_recs.append({
                "id":      "80C",
                "title":   f"Invest ₹{gap_80c:,.0f} more to max out your 80C limit",
                "gap":     round(gap_80c),
                "questions": [
                    {
                        "id":      "risk",
                        "text":    "Do you prefer safe returns or are you okay with some market risk?",
                        "options": ["I want safe returns", "I'm okay with market risk"]
                    },
                    {
                        "id":      "lock_in",
                        "text":    "Can you lock in this money for at least 3 years?",
                        "options": ["Yes, I can lock it in", "No, I may need it sooner"]
                    }
                ]
            })

        if gap_nps > 2000:
            structured_recs.append({
                "id":      "NPS",
                "title":   f"Put ₹{gap_nps:,.0f} in NPS for an extra bonus deduction",
                "gap":     round(gap_nps),
                "questions": [
                    {
                        "id":      "nps_account",
                        "text":    "Do you already have an NPS account?",
                        "options": ["Yes I have one", "No, but I can open one"]
                    },
                    {
                        "id":      "monthly_comfort",
                        "text":    f"Can you set aside ₹{gap_nps//12:,.0f}/month for NPS?",
                        "options": ["Yes, that works", "I can do a smaller amount"]
                    }
                ]
            })

        if not p["health_self"] or p["health_self"] < 5000:
            structured_recs.append({
                "id":      "HEALTH",
                "title":   "Get a health insurance policy to save tax + protect your family",
                "gap":     0,
                "questions": [
                    {
                        "id":      "family_size",
                        "text":    "Who do you want to cover in the policy?",
                        "options": ["Just myself", "Myself + spouse", "Myself + spouse + kids"]
                    },
                    {
                        "id":      "budget",
                        "text":    "What's your comfortable annual premium budget?",
                        "options": ["Under ₹6,000", "₹6,000 – ₹12,000", "₹12,000 – ₹25,000"]
                    }
                ]
            })

        if p["monthly_rent"] > 0 and p["hra_received"] == 0:
            structured_recs.append({
                "id":      "HRA",
                "title":   "Ask your employer to add HRA to your salary — saves rent tax",
                "gap":     0,
                "questions": [
                    {
                        "id":      "employer_type",
                        "text":    "What kind of employer do you work for?",
                        "options": ["Private company", "Government / PSU", "Own business / freelance"]
                    }
                ]
            })

        response_data = {
            "gross_annual":      round(p["gross"]),
            "total_deductions":  reasoning["total_old"],
            "fired_rules":       reasoning["fired_rules"],
            "deductions":        deduction_list,
            "tax_old":           action["tax_old"],
            "tax_new":           action["tax_new"],
            "best_regime":       action["best_regime"],
            "you_save":          action["you_save"],
            "suggestions":       action["suggestions"],
            "structured_recs":   structured_recs,
            # pass original answers back so explore can recalculate
            "original_answers":  plain_answers,
        }

        return jsonify({"success": True, "data": response_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── EXPLORE ───────────────────────────────────────────────────────────────────
@app.route("/api/explore", methods=["POST", "OPTIONS"])
def explore():
    """
    Called when user answers the deep questions for a recommendation.
    Receives:
      - rec_id          : which recommendation ("80C", "NPS", "HEALTH", "HRA")
      - answers         : { question_id: chosen_option }
      - original_answers: the user's original form data
    Returns:
      - instrument      : what we specifically recommend
      - explanation     : plain-language why
      - new_tax         : recalculated tax after applying the recommendation
      - original_tax    : tax before (for comparison)
      - tax_saved       : the difference
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    body            = request.get_json(force=True)
    rec_id          = body.get("rec_id")
    q_answers       = body.get("answers", {})
    orig            = body.get("original_answers", {})

    try:
        agent    = TaxSavingAgent()
        percepts = agent.perceive({k: float(v) if isinstance(v, (int,float)) else v for k,v in orig.items()})
        reasoning= agent.reason(percepts)
        action   = agent.act(percepts, reasoning)
        orig_tax = action["tax_old"]["total_tax"] if action["best_regime"] == "OLD" else action["tax_new"]["total_tax"]

        kb       = TAX_KNOWLEDGE_BASE
        used_80c = sum(percepts[k] for k in ["epf","ppf","elss","lic","nsc","fd5yr"])
        gap_80c  = max(0, kb["80C_LIMIT"]  - used_80c)
        gap_nps  = max(0, kb["NPS_EXTRA_LIMIT"] - percepts["nps"])

        instrument  = ""
        explanation = ""
        new_answers = dict(orig)

        # ── 80C Recommendation Logic ─────────────────────────────────────
        if rec_id == "80C":
            risk     = q_answers.get("risk", "")
            lock_in  = q_answers.get("lock_in", "")
            wants_market = "market" in risk.lower()
            can_lock     = "yes" in lock_in.lower()

            if wants_market and can_lock:
                instrument  = "ELSS Mutual Fund"
                explanation = (
                    f"ELSS is perfect for you — it gives market-linked returns "
                    f"with only a 3-year lock-in. Invest ₹{gap_80c:,.0f} in ELSS "
                    f"to fully use your 80C limit."
                )
                new_answers["elss_annual"] = float(orig.get("elss_annual", 0)) + gap_80c

            elif wants_market and not can_lock:
                partial = min(gap_80c, 50000)
                instrument  = "ELSS (partial) + NSC"
                explanation = (
                    f"Since you need some liquidity, invest ₹{partial:,.0f} in ELSS "
                    f"and the remaining ₹{gap_80c - partial:,.0f} in NSC (5-year, "
                    f"post office, guaranteed returns)."
                )
                new_answers["elss_annual"] = float(orig.get("elss_annual", 0)) + partial
                new_answers["nsc_annual"]  = float(orig.get("nsc_annual",  0)) + (gap_80c - partial)

            else:
                instrument  = "PPF (Public Provident Fund)"
                explanation = (
                    f"PPF is the safest 80C option — government-backed, "
                    f"tax-free returns (~7.1%), 15-year account but partially "
                    f"withdrawable after 7 years. Invest ₹{gap_80c:,.0f} in PPF."
                )
                new_answers["ppf_annual"] = float(orig.get("ppf_annual", 0)) + gap_80c

        # ── NPS Recommendation Logic ─────────────────────────────────────
        elif rec_id == "NPS":
            monthly_ok = "yes" in q_answers.get("monthly_comfort", "").lower()
            invest_amt = gap_nps if monthly_ok else min(gap_nps, 24000)
            instrument  = "NPS Tier-I Account"
            explanation = (
                f"NPS gives you an EXTRA ₹{invest_amt:,.0f} deduction completely "
                f"separate from your 80C limit. That's ₹{invest_amt//12:,.0f}/month. "
                f"Returns are market-linked but locked until retirement (partial "
                f"withdrawal allowed after 3 years for specific needs)."
            )
            new_answers["nps_annual"] = float(orig.get("nps_annual", 0)) + invest_amt

        # ── Health Insurance Logic ────────────────────────────────────────
        elif rec_id == "HEALTH":
            family   = q_answers.get("family_size", "")
            budget   = q_answers.get("budget", "")

            if "kids" in family.lower():
                cover       = "₹10 lakh family floater"
                est_premium = 14000
            elif "spouse" in family.lower():
                cover       = "₹5 lakh family floater"
                est_premium = 9000
            else:
                cover       = "₹5 lakh individual policy"
                est_premium = 6000

            if "25,000" in budget:     est_premium = min(est_premium, 25000)
            elif "12,000" in budget:   est_premium = min(est_premium, 12000)
            elif "6,000"  in budget:   est_premium = min(est_premium, 6000)

            instrument  = f"{cover} health insurance"
            explanation = (
                f"A {cover} plan costs roughly ₹{est_premium:,.0f}/year. "
                f"This gives you medical cover AND a tax deduction under Sec 80D. "
                f"Look at Star Health, HDFC Ergo, or Niva Bupa for competitive rates."
            )
            new_answers["health_self"] = est_premium

        # ── HRA Logic ────────────────────────────────────────────────────
        elif rec_id == "HRA":
            emp = q_answers.get("employer_type", "")
            if "government" in emp.lower():
                instrument  = "Salary restructuring via pay commission"
                explanation = (
                    "Government employees receive HRA as part of the pay structure. "
                    "Check with your accounts department if HRA is being correctly "
                    "reflected in your Form 16."
                )
            elif "business" in emp.lower() or "freelance" in emp.lower():
                instrument  = "Rent receipts under self-employed HRA rules"
                explanation = (
                    "As a self-employed person, you cannot claim HRA. However, "
                    "you can claim rent paid as a business expense if your office "
                    "is at home. Consult a CA for this."
                )
            else:
                instrument  = "Salary restructuring — request HR to add HRA"
                explanation = (
                    "Ask your HR or payroll team to restructure your CTC to include "
                    "an HRA component (typically 40–50% of basic). This is a one-time "
                    "change that saves you significant tax every year on your rent."
                )

        # ── Recalculate with new investment applied ───────────────────────
        new_plain = {}
        for k, v in new_answers.items():
            try:    new_plain[k] = float(v)
            except: new_plain[k] = v

        new_percepts  = agent.perceive(new_plain)
        new_reasoning = agent.reason(new_percepts)
        new_action    = agent.act(new_percepts, new_reasoning)
        new_tax       = new_action["tax_old"]["total_tax"] if new_action["best_regime"] == "OLD" else new_action["tax_new"]["total_tax"]
        tax_saved     = max(0, orig_tax - new_tax)

        return jsonify({
            "success":    True,
            "instrument": instrument,
            "explanation":explanation,
            "orig_tax":   orig_tax,
            "new_tax":    new_tax,
            "tax_saved":  tax_saved,
            "new_total_deductions": new_reasoning["total_old"],
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("This module is import-only for serverless deployment.")
