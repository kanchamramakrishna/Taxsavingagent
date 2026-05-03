"""
app.py — Flask API Server for Tax Saving Recommendation Agent (Vercel-Safe)
===========================================================================
Endpoints:
  GET  /                 — health check (always works)
  GET  /api/health       — detailed health check
  POST /api/calculate    — full tax analysis from plain-language form data
  POST /api/explore      — iterative recommendation exploration + live recalculation
  GET  /api/status       — service status
"""

import logging
import sys
import traceback
from flask import Flask, request, jsonify

# ── LOGGING SETUP ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ── IMPORT AGENT (with error handling) ────────────────────────────────────────
try:
    from tax_agent import TaxSavingAgent, TAX_KNOWLEDGE_BASE, InferenceEngine
    logger.info("✓ Tax agent imported successfully")
    AGENT_READY = True
except Exception as e:
    logger.error(f"✗ Failed to import tax_agent: {str(e)}")
    logger.error(traceback.format_exc())
    AGENT_READY = False

# ── FLASK APP INITIALIZATION ─────────────────────────────────────────────────
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
logger.info("✓ Flask app initialized")

# ── CORS MIDDLEWARE ──────────────────────────────────────────────────────────
@app.after_request
def add_cors(response):
    """Add CORS headers to all responses"""
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    response.headers["Content-Type"] = "application/json"
    return response

# ── ROOT ROUTE (Vercel health check) ────────────────────────────────────────
@app.route("/", methods=["GET", "HEAD"])
def root():
    """Root route - always returns success"""
    try:
        return jsonify({
            "service": "Tax Saving Agent API",
            "version": "1.0",
            "status": "operational" if AGENT_READY else "degraded",
            "endpoints": [
                "/api/health",
                "/api/calculate",
                "/api/explore",
                "/api/status"
            ]
        }), 200
    except Exception as e:
        logger.error(f"Root route error: {str(e)}")
        return jsonify({"error": "Internal error", "message": str(e)}), 500

# ── HEALTH CHECK (simple) ────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint"""
    try:
        response = {
            "status": "ok" if AGENT_READY else "degraded",
            "agent": "TaxSavingAgent",
            "fy": "2024-25",
            "agent_ready": AGENT_READY
        }
        status_code = 200 if AGENT_READY else 503
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ── SERVICE STATUS ───────────────────────────────────────────────────────────
@app.route("/api/status", methods=["GET"])
def status():
    """Service status endpoint"""
    try:
        return jsonify({
            "service_name": "Tax Saving Recommendation Agent",
            "environment": "vercel",
            "agent_status": "ready" if AGENT_READY else "failed",
            "api_version": "1.0",
            "routes": {
                "/api/health": "GET",
                "/api/calculate": "POST",
                "/api/explore": "POST"
            }
        }), 200
    except Exception as e:
        logger.error(f"Status endpoint error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ── CALCULATE ENDPOINT ───────────────────────────────────────────────────────
@app.route("/api/calculate", methods=["POST", "OPTIONS"])
def calculate():
    """
    Main tax calculation endpoint
    Accepts JSON with tax information and returns recommendations
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        # Ensure agent is ready
        if not AGENT_READY:
            return jsonify({
                "success": False,
                "error": "Agent not initialized. Check server logs."
            }), 503

        # Safe JSON parsing
        try:
            body = request.get_json(force=False)
            if body is None:
                body = {}
        except Exception as e:
            logger.warning(f"JSON parse error: {str(e)}")
            body = {}

        # Extract and validate input data
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

        logger.info(f"Received calculation request with salary: {plain_answers['monthly_salary']}")

        # Run agent
        agent     = TaxSavingAgent()
        percepts  = agent.perceive(plain_answers)
        reasoning = agent.reason(percepts)
        action    = agent.act(percepts, reasoning)

        # Build deduction list
        deduction_list = []
        for d in reasoning["deductions"]:
            if d["amount"] > 0:
                item = {"label": d["label"], "amount": d["amount"]}
                if "breakdown" in d: item["breakdown"] = d["breakdown"]
                if "note"      in d: item["note"]      = d["note"]
                deduction_list.append(item)

        # Build structured recommendations
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
            "original_answers":  plain_answers,
        }

        logger.info(f"Calculation successful. Best regime: {action['best_regime']}")
        return jsonify({"success": True, "data": response_data}), 200

    except ValueError as e:
        logger.error(f"Value error in calculate: {str(e)}")
        return jsonify({"success": False, "error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error in calculate: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Internal server error"}), 500


# ── EXPLORE ENDPOINT ─────────────────────────────────────────────────────────
@app.route("/api/explore", methods=["POST", "OPTIONS"])
def explore():
    """
    Exploration endpoint for deeper recommendations
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        # Ensure agent is ready
        if not AGENT_READY:
            return jsonify({
                "success": False,
                "error": "Agent not initialized"
            }), 503

        # Safe JSON parsing
        try:
            body = request.get_json(force=False)
            if body is None:
                body = {}
        except Exception as e:
            logger.warning(f"JSON parse error in explore: {str(e)}")
            body = {}

        rec_id  = body.get("rec_id", "")
        q_answers = body.get("answers", {})
        orig = body.get("original_answers", {})

        logger.info(f"Explore request for recommendation: {rec_id}")

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

        # ── 80C Logic ────────────────────────────────────────────────
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
                    f"and the remaining ₹{gap_80c - partial:,.0f} in NSC (5-year)."
                )
                new_answers["elss_annual"] = float(orig.get("elss_annual", 0)) + partial
                new_answers["nsc_annual"]  = float(orig.get("nsc_annual",  0)) + (gap_80c - partial)

            else:
                instrument  = "PPF (Public Provident Fund)"
                explanation = (
                    f"PPF is the safest 80C option — government-backed, "
                    f"tax-free returns (~7.1%), 15-year account. Invest ₹{gap_80c:,.0f}."
                )
                new_answers["ppf_annual"] = float(orig.get("ppf_annual", 0)) + gap_80c

        # ── NPS Logic ────────────────────────────────────────────────
        elif rec_id == "NPS":
            monthly_ok = "yes" in q_answers.get("monthly_comfort", "").lower()
            invest_amt = gap_nps if monthly_ok else min(gap_nps, 24000)
            instrument  = "NPS Tier-I Account"
            explanation = (
                f"NPS gives you an EXTRA ₹{invest_amt:,.0f} deduction completely "
                f"separate from your 80C limit."
            )
            new_answers["nps_annual"] = float(orig.get("nps_annual", 0)) + invest_amt

        # ── Health Insurance Logic ───────────────────────────────────
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
            explanation = f"A {cover} plan costs roughly ₹{est_premium:,.0f}/year."
            new_answers["health_self"] = est_premium

        # ── HRA Logic ────────────────────────────────────────────────
        elif rec_id == "HRA":
            emp = q_answers.get("employer_type", "")
            if "government" in emp.lower():
                instrument  = "Salary restructuring via pay commission"
                explanation = "Check with your accounts department for HRA reflection."
            elif "business" in emp.lower() or "freelance" in emp.lower():
                instrument  = "Rent receipts under self-employed HRA rules"
                explanation = "You can claim rent as a business expense if office is at home."
            else:
                instrument  = "Salary restructuring — request HR to add HRA"
                explanation = "Ask HR to include HRA in your CTC (typically 40–50% of basic)."

        # ── Recalculate with new investment ──────────────────────────
        new_plain = {}
        for k, v in new_answers.items():
            try:    new_plain[k] = float(v)
            except: new_plain[k] = v

        new_percepts  = agent.perceive(new_plain)
        new_reasoning = agent.reason(new_percepts)
        new_action    = agent.act(new_percepts, new_reasoning)
        new_tax       = new_action["tax_old"]["total_tax"] if new_action["best_regime"] == "OLD" else new_action["tax_new"]["total_tax"]
        tax_saved     = max(0, orig_tax - new_tax)

        logger.info(f"Explore complete. Tax saved: ₹{tax_saved}")

        return jsonify({
            "success":    True,
            "instrument": instrument,
            "explanation":explanation,
            "orig_tax":   orig_tax,
            "new_tax":    new_tax,
            "tax_saved":  tax_saved,
            "new_total_deductions": new_reasoning["total_old"],
        }), 200

    except ValueError as e:
        logger.error(f"Value error in explore: {str(e)}")
        return jsonify({"success": False, "error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error in explore: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Internal server error"}), 500


# ── ERROR HANDLERS ───────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logger.warning(f"404 - Route not found: {request.path}")
    return jsonify({
        "error": "Not Found",
        "message": f"Route '{request.path}' does not exist",
        "available_routes": ["/", "/api/health", "/api/calculate", "/api/explore"]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 - Internal server error: {str(error)}")
    return jsonify({
        "error": "Internal Server Error",
        "message": "An unexpected error occurred"
    }), 500

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    logger.warning(f"405 - Method not allowed: {request.method} {request.path}")
    return jsonify({
        "error": "Method Not Allowed",
        "message": f"The {request.method} method is not allowed for this endpoint"
    }), 405


# ── STARTUP LOGGING ──────────────────────────────────────────────────────────
logger.info("="*60)
logger.info("Tax Saving Agent API - Vercel Edition")
logger.info("="*60)
logger.info(f"Agent Status: {'✓ Ready' if AGENT_READY else '✗ Failed'}")
logger.info("Available endpoints:")
logger.info("  GET  /")
logger.info("  GET  /api/health")
logger.info("  GET  /api/status")
logger.info("  POST /api/calculate")
logger.info("  POST /api/explore")
logger.info("="*60)
