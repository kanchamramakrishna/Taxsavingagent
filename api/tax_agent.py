"""
Tax Saving Recommendation Agent - AIKR S2026 Project
=====================================================
Agent Type   : Goal-Based + Knowledge Representation Agent
AI Technique : Rule-Based Reasoning + Forward Chaining Inference Engine
Domain       : Indian Income Tax (FY 2024-25 / AY 2025-26)
Language     : Python 3

Design Philosophy:
  The user answers in PLAIN LANGUAGE — monthly numbers, yes/no questions,
  everyday descriptions. The agent handles ALL tax law internally.
  No section numbers, no jargon, no tax knowledge required from the user.

AI Tool Usage Declaration:
  - AI Tool Used: Claude (Anthropic)
  - Purpose: Code structure suggestions and tax rule verification
  - AI-Generated Components: Initial scaffold, docstrings
  - Self-Written Components: Full tax logic, knowledge base rules,
                             inference engine, plain-language CLI, test scenarios
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: KNOWLEDGE BASE  (Indian Income Tax Act — hidden from user)
# ─────────────────────────────────────────────────────────────────────────────

TAX_KNOWLEDGE_BASE = {

    # Section 80C — max ₹1,50,000
    "80C_LIMIT": 150000,

    # Section 80CCD(1B) — extra NPS on top of 80C
    "NPS_EXTRA_LIMIT": 50000,

    # Section 80D — health insurance
    "80D": {
        "self_below_60":    25000,
        "self_senior":      50000,
        "parents_below_60": 25000,
        "parents_senior":   50000,
    },

    # Section 24(b) — home loan interest
    "HOME_LOAN_INTEREST_LIMIT": 200000,

    # Standard Deduction for salaried
    "STANDARD_DEDUCTION": 50000,

    # Section 80TTA / 80TTB — savings interest
    "80TTA_LIMIT": 10000,   # for non-seniors
    "80TTB_LIMIT": 50000,   # for seniors

    # HRA: exemption = min(HRA received, rent - 10% basic, 50%/40% of basic)
    "HRA_METRO_PCT":    0.50,
    "HRA_NONMETRO_PCT": 0.40,
    "HRA_BASIC_PCT":    0.10,   # rent - 10% basic threshold

    # EPF: employee contributes 12% of basic salary
    "EPF_PCT": 0.12,

    # HRA component assumed at 20% of gross CTC (industry standard)
    "HRA_OF_GROSS_PCT": 0.20,

    # EMI split assumption: ~70% interest, ~30% principal (early loan years)
    "EMI_INTEREST_PCT":   0.70,
    "EMI_PRINCIPAL_PCT":  0.30,

    # Education loan: ~60% of EMI goes to interest
    "EDU_INTEREST_PCT": 0.60,

    # Old Regime Tax Slabs
    "TAX_SLABS_OLD": [
        {"min": 0,       "max": 250000,       "rate": 0.00},
        {"min": 250001,  "max": 500000,        "rate": 0.05},
        {"min": 500001,  "max": 1000000,       "rate": 0.20},
        {"min": 1000001, "max": float("inf"),  "rate": 0.30},
    ],

    # New Regime Tax Slabs
    "TAX_SLABS_NEW": [
        {"min": 0,       "max": 300000,        "rate": 0.00},
        {"min": 300001,  "max": 600000,        "rate": 0.05},
        {"min": 600001,  "max": 900000,        "rate": 0.10},
        {"min": 900001,  "max": 1200000,       "rate": 0.15},
        {"min": 1200001, "max": 1500000,       "rate": 0.20},
        {"min": 1500001, "max": float("inf"),  "rate": 0.30},
    ],

    # Rebate u/s 87A
    "REBATE_OLD": {"limit": 500000, "amount": 12500},
    "REBATE_NEW": {"limit": 700000, "amount": 25000},

    # Surcharge
    "SURCHARGE": [
        {"min": 5000000,  "max": 10000000,      "rate": 0.10},
        {"min": 10000001, "max": 20000000,       "rate": 0.15},
        {"min": 20000001, "max": 50000000,       "rate": 0.25},
        {"min": 50000001, "max": float("inf"),   "rate": 0.37},
    ],

    "CESS": 0.04,
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: INFERENCE ENGINE  (Forward Chaining Rule-Based Reasoner)
# ─────────────────────────────────────────────────────────────────────────────

class InferenceEngine:
    """
    Forward Chaining Inference Engine.
    Each rule() method checks a condition from working memory,
    fires if applicable, and asserts a new deduction fact.
    All tax law is encapsulated here — invisible to the user.
    """

    def __init__(self, kb: dict):
        self.kb           = kb
        self.working_mem  = {}   # derived facts
        self.fired_rules  = []   # audit trail of rules that fired

    def assert_fact(self, key, value):
        self.working_mem[key] = value

    def _fire(self, rule_name: str, amount: float) -> float:
        if amount > 0:
            self.fired_rules.append(rule_name)
        return round(amount, 2)

    # ── Tax slab calculation ─────────────────────────────────────────────

    def _slab_tax(self, taxable: float, regime: str) -> float:
        slabs = self.kb["TAX_SLABS_OLD"] if regime == "old" else self.kb["TAX_SLABS_NEW"]
        tax = 0.0
        for slab in slabs:
            if taxable <= slab["min"] - 1:
                break
            in_slab = min(taxable, slab["max"]) - (slab["min"] - 1)
            tax    += max(0, in_slab) * slab["rate"]
        return tax

    def calculate_tax(self, gross: float, deductions: float, regime: str) -> dict:
        taxable  = max(0.0, gross - deductions)
        base_tax = self._slab_tax(taxable, regime)

        rebate_rule = self.kb[f"REBATE_{regime.upper()}"]
        rebate      = rebate_rule["amount"] if taxable <= rebate_rule["limit"] else 0
        base_tax    = max(0.0, base_tax - rebate)

        surcharge = 0.0
        for tier in self.kb["SURCHARGE"]:
            if tier["min"] <= gross <= tier["max"]:
                surcharge = base_tax * tier["rate"]
                break

        cess      = (base_tax + surcharge) * self.kb["CESS"]
        total_tax = base_tax + surcharge + cess

        return {
            "taxable_income": round(taxable),
            "base_tax":       round(base_tax),
            "rebate":         round(rebate),
            "surcharge":      round(surcharge),
            "cess":           round(cess),
            "total_tax":      round(total_tax),
        }

    # ── Deduction Rules ──────────────────────────────────────────────────

    def rule_standard_deduction(self) -> dict:
        """Rule: All salaried employees get ₹50,000 standard deduction."""
        amt = self.kb["STANDARD_DEDUCTION"]
        return {"label": "Standard Deduction (automatic for all employees)",
                "amount": self._fire("STANDARD_DEDUCTION", amt)}

    def rule_hra(self, basic: float, hra_received: float,
                 monthly_rent: float, is_metro: bool) -> dict:
        """Rule: HRA exemption — minimum of 3 values (Sec 10(13A))."""
        if monthly_rent <= 0 or hra_received <= 0:
            return {"label": "Rent Exemption (HRA)", "amount": 0,
                    "note": "Not renting / no HRA in salary"}
        annual_rent = monthly_rent * 12
        metro_pct   = self.kb["HRA_METRO_PCT"] if is_metro else self.kb["HRA_NONMETRO_PCT"]
        exempt      = max(0.0, min(
            hra_received,
            annual_rent - self.kb["HRA_BASIC_PCT"] * basic,
            metro_pct * basic,
        ))
        return {"label": "Rent Exemption (HRA)",
                "amount": self._fire("HRA", exempt),
                "note": f"Metro rate: {int(metro_pct*100)}% of basic"}

    def rule_investments_80c(self, epf: float, ppf: float, elss: float,
                             lic: float, nsc: float, fd5yr: float) -> dict:
        """Rule: All 80C investments combined, capped at ₹1,50,000."""
        total = epf + ppf + elss + lic + nsc + fd5yr
        capped = min(total, self.kb["80C_LIMIT"])
        breakdown = {
            "PF / EPF (auto-deducted by employer)": round(epf),
            "PPF":  round(ppf),  "ELSS": round(elss),
            "LIC":  round(lic),  "NSC":  round(nsc),
            "5-Year Tax FD": round(fd5yr),
        }
        return {"label": "Your Investments (Sec 80C)",
                "amount": self._fire("80C", capped),
                "breakdown": {k: v for k, v in breakdown.items() if v > 0},
                "note": f"Total investments ₹{total:,.0f} — capped at ₹1,50,000"}

    def rule_nps_extra(self, nps_amount: float) -> dict:
        """Rule: Extra NPS deduction beyond 80C (Sec 80CCD(1B))."""
        capped = min(nps_amount, self.kb["NPS_EXTRA_LIMIT"])
        return {"label": "NPS Extra Deduction",
                "amount": self._fire("80CCD_1B", capped),
                "note": "Extra ₹50,000 deduction beyond all other investments"}

    def rule_health_insurance(self, self_premium: float, parent_premium: float,
                              senior_self: bool, senior_parents: bool) -> dict:
        """Rule: Health insurance premium deduction (Sec 80D)."""
        self_limit   = self.kb["80D"]["self_senior"]    if senior_self    else self.kb["80D"]["self_below_60"]
        parent_limit = self.kb["80D"]["parents_senior"] if senior_parents else self.kb["80D"]["parents_below_60"]
        self_ded     = min(self_premium, self_limit)
        parent_ded   = min(parent_premium, parent_limit)
        total        = self_ded + parent_ded
        return {"label": "Health Insurance Premium",
                "amount": self._fire("80D", total),
                "breakdown": {
                    "Your / family policy": round(self_ded),
                    "Parents' policy":      round(parent_ded),
                }}

    def rule_home_loan(self, monthly_emi: float, existing_80c_used: float) -> dict:
        """Rule: Home loan interest (Sec 24b) and principal (adds to 80C)."""
        if monthly_emi <= 0:
            return {"label": "Home Loan", "amount": 0}
        annual_emi    = monthly_emi * 12
        interest_part = min(annual_emi * self.kb["EMI_INTEREST_PCT"],
                            self.kb["HOME_LOAN_INTEREST_LIMIT"])
        principal_gap = max(0, self.kb["80C_LIMIT"] - existing_80c_used)
        principal_part= min(annual_emi * self.kb["EMI_PRINCIPAL_PCT"], principal_gap)
        return {"label": "Home Loan Interest",
                "amount": self._fire("24B", interest_part),
                "principal_for_80c": round(principal_part),
                "note": "Interest portion of your EMI (auto-calculated)"}

    def rule_education_loan(self, monthly_emi: float) -> dict:
        """Rule: Education loan interest — no upper limit (Sec 80E)."""
        interest = monthly_emi * 12 * self.kb["EDU_INTEREST_PCT"]
        return {"label": "Education Loan Interest",
                "amount": self._fire("80E", interest),
                "note": "Interest portion of your education EMI (auto-calculated)"}

    def rule_savings_interest(self, interest: float, senior: bool) -> dict:
        """Rule: Savings / FD interest deduction (Sec 80TTA / 80TTB)."""
        if senior:
            capped = min(interest, self.kb["80TTB_LIMIT"])
            section = "80TTB (senior citizen)"
        else:
            capped = min(interest, self.kb["80TTA_LIMIT"])
            section = "80TTA"
        return {"label": f"Savings Interest ({section})",
                "amount": self._fire(section, capped)}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: THE AGENT
# ─────────────────────────────────────────────────────────────────────────────

class TaxSavingAgent:
    """
    Goal-Based AI Agent for Tax Saving Recommendations.

    Environment : Indian Tax System (FY 2024-25)
    Agent Type  : Goal-Based (goal = minimise tax liability)
    Percepts    : Plain-language answers from user (monthly salary, yes/no, etc.)
    Actions     : Compute deductions, compare regimes, suggest optimisations
    AI Logic    : Forward Chaining Inference Engine on Knowledge Base
    """

    def __init__(self):
        self.kb = TAX_KNOWLEDGE_BASE

    # ── PERCEIVE: translate plain-language answers into financial facts ────

    def perceive(self, plain_answers: dict) -> dict:
        """
        Convert what the user told us (in plain language) into
        structured financial percepts the inference engine can work with.
        All conversions are done HERE — the user never sees these.
        """
        monthly = plain_answers["monthly_salary"]
        basic   = monthly * (plain_answers["basic_pct"] / 100)
        gross   = monthly * 12

        # EPF: auto-calculated as 12% of annual basic
        epf = basic * 12 * self.kb["EPF_PCT"] if plain_answers["has_epf"] else 0

        # HRA component assumed at 20% of gross (standard industry CTC split)
        hra_received = gross * self.kb["HRA_OF_GROSS_PCT"]

        return {
            "gross":           gross,
            "basic_annual":    basic * 12,
            "hra_received":    hra_received,
            "monthly_rent":    plain_answers.get("monthly_rent", 0),
            "is_metro":        plain_answers.get("is_metro", False),
            "senior_self":     plain_answers.get("senior_self", False),
            "senior_parents":  plain_answers.get("senior_parents", False),
            # investments
            "epf":   epf,
            "ppf":   plain_answers.get("ppf_annual", 0),
            "elss":  plain_answers.get("elss_annual", 0),
            "lic":   plain_answers.get("lic_annual", 0),
            "nsc":   plain_answers.get("nsc_annual", 0),
            "fd5yr": plain_answers.get("fd5yr_annual", 0),
            "nps":   plain_answers.get("nps_annual", 0),
            # health
            "health_self":    plain_answers.get("health_self", 0),
            "health_parents": plain_answers.get("health_parents", 0),
            # loans
            "home_emi":  plain_answers.get("home_emi_monthly", 0),
            "edu_emi":   plain_answers.get("edu_emi_monthly", 0),
            # savings interest
            "savings_interest": plain_answers.get("savings_interest", 0),
        }

    # ── REASON: fire all rules via inference engine ───────────────────────

    def reason(self, percepts: dict) -> dict:
        engine = InferenceEngine(self.kb)

        std   = engine.rule_standard_deduction()
        hra   = engine.rule_hra(percepts["basic_annual"], percepts["hra_received"],
                                percepts["monthly_rent"], percepts["is_metro"])
        inv   = engine.rule_investments_80c(percepts["epf"], percepts["ppf"],
                                            percepts["elss"], percepts["lic"],
                                            percepts["nsc"], percepts["fd5yr"])
        nps   = engine.rule_nps_extra(percepts["nps"])
        health= engine.rule_health_insurance(percepts["health_self"],
                                             percepts["health_parents"],
                                             percepts["senior_self"],
                                             percepts["senior_parents"])
        home  = engine.rule_home_loan(percepts["home_emi"], inv["amount"])
        edu   = engine.rule_education_loan(percepts["edu_emi"])
        sav   = engine.rule_savings_interest(percepts["savings_interest"],
                                             percepts["senior_self"])

        deductions = [std, hra, inv, nps, health, home, edu, sav]

        # Old regime uses all deductions
        total_old = sum(d["amount"] for d in deductions) + home.get("principal_for_80c", 0)

        # New regime: only standard deduction allowed
        total_new = self.kb["STANDARD_DEDUCTION"]

        return {
            "deductions":  deductions,
            "total_old":   round(total_old),
            "total_new":   total_new,
            "fired_rules": engine.fired_rules,
        }

    # ── ACT: compute taxes, compare regimes, generate suggestions ─────────

    def act(self, percepts: dict, reasoning: dict) -> dict:
        gross   = percepts["gross"]
        engine  = InferenceEngine(self.kb)

        tax_old = engine.calculate_tax(gross, reasoning["total_old"], "old")
        tax_new = engine.calculate_tax(gross, reasoning["total_new"], "new")

        best_regime = "OLD" if tax_old["total_tax"] <= tax_new["total_tax"] else "NEW"
        you_save    = abs(tax_old["total_tax"] - tax_new["total_tax"])

        # Gap analysis — what more can the user do?
        used_80c = sum(
            percepts[k] for k in ["epf", "ppf", "elss", "lic", "nsc", "fd5yr"]
        )
        gap_80c = max(0, self.kb["80C_LIMIT"] - used_80c)
        gap_nps = max(0, self.kb["NPS_EXTRA_LIMIT"] - percepts["nps"])

        suggestions = []
        if gap_80c > 2000:
            extra_saving = round(gap_80c * 0.20)
            instruments  = []
            if percepts["elss"] == 0: instruments.append("ELSS mutual fund (3-yr lock-in, good returns)")
            if percepts["ppf"]  == 0: instruments.append("PPF (safe, post office, 15-yr)")
            if not instruments:       instruments.append("top up your existing investments")
            suggestions.append(
                f"Invest Rs.{gap_80c:,.0f} more in {' or '.join(instruments)} "
                f"-> saves you an extra Rs.{extra_saving:,.0f} in tax"
            )
        if gap_nps > 2000:
            suggestions.append(
                f"Put Rs.{gap_nps:,.0f} in NPS (National Pension Scheme) "
                f"-> gives a BONUS deduction on top of all your other investments"
            )
        if percepts["health_self"] < 5000:
            suggestions.append(
                "Get a health insurance policy (Rs.6,000-10,000/year) "
                "-> saves Rs.1,200-3,000 in tax AND protects your family medically"
            )
        if percepts["monthly_rent"] > 0 and hra_exempt_zero(percepts):
            suggestions.append(
                "You pay rent but your salary has no HRA — ask your HR "
                "to restructure your salary to include HRA. Saves thousands every year."
            )

        return {
            "tax_old":     tax_old,
            "tax_new":     tax_new,
            "best_regime": best_regime,
            "you_save":    you_save,
            "suggestions": suggestions,
        }


def hra_exempt_zero(percepts):
    """Helper: check if HRA exemption came out zero despite paying rent."""
    basic = percepts["basic_annual"]
    hra   = percepts["hra_received"]
    rent  = percepts["monthly_rent"] * 12
    return max(0, min(hra, rent - 0.10 * basic, 0.40 * basic)) == 0
