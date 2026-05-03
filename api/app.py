import importlib.util
import logging
import os
import sys
import traceback

from flask import Flask, jsonify, request


BASE_DIR = os.path.dirname(__file__)
TAX_AGENT_PATH = os.path.join(BASE_DIR, "tax_agent.py")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

_TAX_MODULE = None
_TAX_IMPORT_ERROR = None


def load_tax_module():
    """Load the tax engine lazily so import errors cannot crash the app."""
    global _TAX_MODULE, _TAX_IMPORT_ERROR

    if _TAX_MODULE is not None:
        return _TAX_MODULE
    if _TAX_IMPORT_ERROR is not None:
        return None

    try:
        if not os.path.exists(TAX_AGENT_PATH):
            raise FileNotFoundError(f"Missing tax_agent.py at {TAX_AGENT_PATH}")

        spec = importlib.util.spec_from_file_location("tax_agent", TAX_AGENT_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("Could not create import spec for tax_agent.py")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _TAX_MODULE = module
        logger.info("Tax agent imported successfully")
        return _TAX_MODULE
    except Exception as exc:
        _TAX_IMPORT_ERROR = exc
        logger.error("Failed to import tax_agent: %s", exc)
        logger.error(traceback.format_exc())
        return None


def get_json_body():
    try:
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}
    except Exception as exc:
        logger.warning("JSON parse failed: %s", exc)
        return {}


def as_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def build_plain_answers(body):
    return {
        "monthly_salary": as_float(body.get("monthly_salary")),
        "basic_pct": as_float(body.get("basic_pct"), 40.0),
        "senior_self": as_bool(body.get("senior_self")),
        "monthly_rent": as_float(body.get("monthly_rent")),
        "is_metro": as_bool(body.get("is_metro")),
        "home_emi_monthly": as_float(body.get("home_emi_monthly")),
        "edu_emi_monthly": as_float(body.get("edu_emi_monthly")),
        "has_epf": as_bool(body.get("has_epf")),
        "ppf_annual": as_float(body.get("ppf_annual")),
        "elss_annual": as_float(body.get("elss_annual")),
        "lic_annual": as_float(body.get("lic_annual")),
        "nsc_annual": as_float(body.get("nsc_annual")),
        "fd5yr_annual": as_float(body.get("fd5yr_annual")),
        "nps_annual": as_float(body.get("nps_annual")),
        "health_self": as_float(body.get("health_self")),
        "health_parents": as_float(body.get("health_parents")),
        "senior_parents": as_bool(body.get("senior_parents")),
        "savings_interest": as_float(body.get("savings_interest")),
    }


def run_agent(plain_answers):
    module = load_tax_module()
    if module is None:
        raise RuntimeError(f"Tax agent unavailable: {_TAX_IMPORT_ERROR}")

    agent = module.TaxSavingAgent()
    percepts = agent.perceive(plain_answers)
    reasoning = agent.reason(percepts)
    action = agent.act(percepts, reasoning)
    return module, percepts, reasoning, action


def build_deductions(reasoning):
    deductions = []
    for deduction in reasoning.get("deductions", []):
        if deduction.get("amount", 0) <= 0:
            continue
        item = {
            "label": deduction.get("label", ""),
            "amount": deduction.get("amount", 0),
        }
        if "breakdown" in deduction:
            item["breakdown"] = deduction["breakdown"]
        if "note" in deduction:
            item["note"] = deduction["note"]
        deductions.append(item)
    return deductions


def build_structured_recommendations(module, percepts):
    kb = module.TAX_KNOWLEDGE_BASE
    used_80c = sum(percepts[k] for k in ["epf", "ppf", "elss", "lic", "nsc", "fd5yr"])
    gap_80c = max(0, kb["80C_LIMIT"] - used_80c)
    gap_nps = max(0, kb["NPS_EXTRA_LIMIT"] - percepts["nps"])

    recommendations = []

    if gap_80c > 2000:
        recommendations.append(
            {
                "id": "80C",
                "title": f"Invest Rs.{gap_80c:,.0f} more to max out your 80C limit",
                "gap": round(gap_80c),
                "questions": [
                    {
                        "id": "risk",
                        "text": "Do you prefer safe returns or are you okay with some market risk?",
                        "options": ["I want safe returns", "I'm okay with market risk"],
                    },
                    {
                        "id": "lock_in",
                        "text": "Can you lock in this money for at least 3 years?",
                        "options": ["Yes, I can lock it in", "No, I may need it sooner"],
                    },
                ],
            }
        )

    if gap_nps > 2000:
        recommendations.append(
            {
                "id": "NPS",
                "title": f"Put Rs.{gap_nps:,.0f} in NPS for an extra bonus deduction",
                "gap": round(gap_nps),
                "questions": [
                    {
                        "id": "nps_account",
                        "text": "Do you already have an NPS account?",
                        "options": ["Yes I have one", "No, but I can open one"],
                    },
                    {
                        "id": "monthly_comfort",
                        "text": f"Can you set aside Rs.{gap_nps // 12:,.0f}/month for NPS?",
                        "options": ["Yes, that works", "I can do a smaller amount"],
                    },
                ],
            }
        )

    if not percepts["health_self"] or percepts["health_self"] < 5000:
        recommendations.append(
            {
                "id": "HEALTH",
                "title": "Get a health insurance policy to save tax and protect your family",
                "gap": 0,
                "questions": [
                    {
                        "id": "family_size",
                        "text": "Who do you want to cover in the policy?",
                        "options": ["Just myself", "Myself + spouse", "Myself + spouse + kids"],
                    },
                    {
                        "id": "budget",
                        "text": "What's your comfortable annual premium budget?",
                        "options": ["Under Rs.6,000", "Rs.6,000 - Rs.12,000", "Rs.12,000 - Rs.25,000"],
                    },
                ],
            }
        )

    return recommendations


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = os.getenv("CORS_ORIGIN", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    return response


@app.route("/")
def home():
    return {"status": "ok", "message": "Server running"}


@app.route("/api/health", methods=["GET"])
def health():
    try:
        module = load_tax_module()
        return jsonify(
            {
                "status": "ok" if module is not None else "degraded",
                "message": "Server running",
                "agent_ready": module is not None,
                "agent_error": str(_TAX_IMPORT_ERROR) if _TAX_IMPORT_ERROR else None,
            }
        ), 200
    except Exception as exc:
        logger.error("Health endpoint failed: %s", exc)
        logger.error(traceback.format_exc())
        return jsonify({"status": "ok", "message": "Server running", "agent_ready": False}), 200


@app.route("/api/status", methods=["GET"])
def status():
    try:
        module = load_tax_module()
        return jsonify(
            {
                "service_name": "Tax Saving Recommendation Agent",
                "environment": os.getenv("VERCEL_ENV", "local"),
                "agent_status": "ready" if module is not None else "unavailable",
                "api_version": "1.0",
                "routes": {
                    "/": "GET",
                    "/api/health": "GET",
                    "/api/status": "GET",
                    "/api/calculate": "POST",
                    "/api/explore": "POST",
                },
            }
        ), 200
    except Exception as exc:
        logger.error("Status endpoint failed: %s", exc)
        logger.error(traceback.format_exc())
        return jsonify({"service_name": "Tax Saving Recommendation Agent", "agent_status": "error"}), 200


@app.route("/api/calculate", methods=["POST", "OPTIONS"])
def calculate():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        plain_answers = build_plain_answers(get_json_body())
        logger.info("Calculate request received; monthly_salary=%s", plain_answers["monthly_salary"])

        module, percepts, reasoning, action = run_agent(plain_answers)
        response_data = {
            "gross_annual": round(percepts["gross"]),
            "total_deductions": reasoning["total_old"],
            "fired_rules": reasoning["fired_rules"],
            "deductions": build_deductions(reasoning),
            "tax_old": action["tax_old"],
            "tax_new": action["tax_new"],
            "best_regime": action["best_regime"],
            "you_save": action["you_save"],
            "suggestions": action["suggestions"],
            "structured_recs": build_structured_recommendations(module, percepts),
            "original_answers": plain_answers,
        }

        logger.info("Calculate succeeded; best_regime=%s", action["best_regime"])
        return jsonify({"success": True, "data": response_data}), 200
    except Exception as exc:
        logger.error("Calculate failed: %s", exc)
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Calculation failed", "detail": str(exc)}), 200


@app.route("/api/explore", methods=["POST", "OPTIONS"])
def explore():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        body = get_json_body()
        rec_id = str(body.get("rec_id", ""))
        answers = body.get("answers", {}) if isinstance(body.get("answers", {}), dict) else {}
        original = body.get("original_answers", {}) if isinstance(body.get("original_answers", {}), dict) else {}
        plain_answers = build_plain_answers(original)

        logger.info("Explore request received; rec_id=%s", rec_id)

        module, percepts, reasoning, action = run_agent(plain_answers)
        orig_tax = action["tax_old"]["total_tax"] if action["best_regime"] == "OLD" else action["tax_new"]["total_tax"]

        kb = module.TAX_KNOWLEDGE_BASE
        used_80c = sum(percepts[k] for k in ["epf", "ppf", "elss", "lic", "nsc", "fd5yr"])
        gap_80c = max(0, kb["80C_LIMIT"] - used_80c)
        gap_nps = max(0, kb["NPS_EXTRA_LIMIT"] - percepts["nps"])

        instrument = "No specific change"
        explanation = "No matching recommendation was found."
        new_answers = dict(plain_answers)

        if rec_id == "80C":
            risk = str(answers.get("risk", "")).lower()
            lock_in = str(answers.get("lock_in", "")).lower()
            wants_market = "market" in risk
            can_lock = "yes" in lock_in

            if wants_market and can_lock:
                instrument = "ELSS Mutual Fund"
                explanation = f"ELSS has market-linked returns with a 3-year lock-in. Invest Rs.{gap_80c:,.0f} to use your 80C gap."
                new_answers["elss_annual"] += gap_80c
            elif wants_market:
                partial = min(gap_80c, 50000)
                instrument = "ELSS plus NSC"
                explanation = f"Use Rs.{partial:,.0f} in ELSS and Rs.{gap_80c - partial:,.0f} in NSC."
                new_answers["elss_annual"] += partial
                new_answers["nsc_annual"] += gap_80c - partial
            else:
                instrument = "PPF"
                explanation = f"PPF is a conservative 80C option. Invest Rs.{gap_80c:,.0f} to use the remaining limit."
                new_answers["ppf_annual"] += gap_80c

        elif rec_id == "NPS":
            monthly_ok = "yes" in str(answers.get("monthly_comfort", "")).lower()
            invest_amt = gap_nps if monthly_ok else min(gap_nps, 24000)
            instrument = "NPS Tier-I Account"
            explanation = f"NPS gives an extra deduction outside 80C. Suggested amount: Rs.{invest_amt:,.0f}."
            new_answers["nps_annual"] += invest_amt

        elif rec_id == "HEALTH":
            family = str(answers.get("family_size", "")).lower()
            budget = str(answers.get("budget", "")).lower()

            if "kids" in family:
                cover, est_premium = "Rs.10 lakh family floater", 14000
            elif "spouse" in family:
                cover, est_premium = "Rs.5 lakh family floater", 9000
            else:
                cover, est_premium = "Rs.5 lakh individual policy", 6000

            if "25,000" in budget:
                est_premium = min(est_premium, 25000)
            elif "12,000" in budget:
                est_premium = min(est_premium, 12000)
            elif "6,000" in budget:
                est_premium = min(est_premium, 6000)

            instrument = f"{cover} health insurance"
            explanation = f"A {cover} plan costs roughly Rs.{est_premium:,.0f}/year."
            new_answers["health_self"] = est_premium

        new_module, new_percepts, new_reasoning, new_action = run_agent(new_answers)
        _ = new_module, new_percepts
        new_tax = new_action["tax_old"]["total_tax"] if new_action["best_regime"] == "OLD" else new_action["tax_new"]["total_tax"]
        tax_saved = max(0, orig_tax - new_tax)

        logger.info("Explore succeeded; rec_id=%s tax_saved=%s", rec_id, tax_saved)
        return jsonify(
            {
                "success": True,
                "instrument": instrument,
                "explanation": explanation,
                "orig_tax": orig_tax,
                "new_tax": new_tax,
                "tax_saved": tax_saved,
                "new_total_deductions": new_reasoning["total_old"],
            }
        ), 200
    except Exception as exc:
        logger.error("Explore failed: %s", exc)
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": "Explore failed", "detail": str(exc)}), 200


@app.errorhandler(404)
def not_found(error):
    logger.warning("404 route not found: %s", request.path)
    return jsonify({"error": "Not Found", "message": f"Route '{request.path}' does not exist"}), 404


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.error("Unhandled Flask error: %s", error)
    logger.error(traceback.format_exc())
    return jsonify({"success": False, "error": "Internal server error"}), 200


logger.info("Tax Saving Agent API loaded")
