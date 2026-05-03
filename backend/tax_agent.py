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

    # ── FULL AGENT LOOP ───────────────────────────────────────────────────

    def run(self, plain_answers: dict) -> dict:
        """Perceive -> Reason -> Act -> Report"""
        percepts  = self.perceive(plain_answers)
        reasoning = self.reason(percepts)
        action    = self.act(percepts, reasoning)
        self._report(percepts, reasoning, action)
        return action

    # ── REPORT ────────────────────────────────────────────────────────────

    @staticmethod
    def _r(n): return f"Rs.{round(n):>12,.0f}"

    def _report(self, percepts, reasoning, action):
        gross    = percepts["gross"]
        tax_old  = action["tax_old"]
        tax_new  = action["tax_new"]
        best     = action["best_regime"]
        best_tax = tax_old["total_tax"] if best == "OLD" else tax_new["total_tax"]

        print(f"\n{'='*65}")
        print(f"  YOUR TAX PICTURE  |  Annual Income: {self._r(gross)}")
        print(f"{'='*65}")

        print(f"\n  What we deducted from your income (Old Regime)\n")
        for d in reasoning["deductions"]:
            if d["amount"] > 0:
                print(f"  + {d['label']:<38} {self._r(d['amount'])}")
                if "breakdown" in d:
                    for item, amt in d["breakdown"].items():
                        if amt > 0:
                            print(f"      -> {item:<35} {self._r(amt)}")
        print(f"  {'─'*55}")
        print(f"  {'Total removed from your taxable income':<38} {self._r(reasoning['total_old'])}")

        print(f"\n  {'':38} {'Old Regime':>12} {'New Regime':>12}")
        print(f"  {'─'*62}")
        rows = [
            ("Taxable Income after deductions", "taxable_income"),
            ("Tax on that income",              "base_tax"),
            ("Minus rebate from government",    "rebate"),
            ("Health & Education Cess (4%)",    "cess"),
            ("TOTAL TAX YOU PAY",               "total_tax"),
        ]
        for label, key in rows:
            o = tax_old[key]
            n = tax_new[key]
            marker = "=>" if key == "total_tax" else "  "
            print(f"  {marker} {label:<36} {self._r(o)} {self._r(n)}")

        print(f"\n{'='*65}")
        print(f"  USE THE {best} TAX REGIME")
        print(f"  You pay only {self._r(best_tax)}  (saves {self._r(action['you_save'])} vs the other regime)")
        print(f"{'='*65}")

        if action["suggestions"]:
            print(f"\n  What you can additionally do to save more:\n")
            for i, s in enumerate(action["suggestions"], 1):
                print(f"  {i}. {s}\n")
        else:
            print(f"\n  🎉 Excellent! You have already optimized your taxes in all possible ways.")
            print(f"  There are no additional deductions or improvements available based on your inputs.\n")

        print(f"\n  [Rules Fired: {', '.join(reasoning['fired_rules'])}]")
        print(f"{'─'*65}\n")


def hra_exempt_zero(percepts):
    """Helper: check if HRA exemption came out zero despite paying rent."""
    basic = percepts["basic_annual"]
    hra   = percepts["hra_received"]
    rent  = percepts["monthly_rent"] * 12
    return max(0, min(hra, rent - 0.10 * basic, 0.40 * basic)) == 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: PLAIN-LANGUAGE CLI  (no jargon shown to user)
# ─────────────────────────────────────────────────────────────────────────────

def ask_yn(question: str) -> bool:
    """Ask a yes/no question. Returns True for yes."""
    for _ in range(100):
        ans = input(f"  {question} (yes/no): ").strip().lower()
        if ans in ("yes", "y"):  return True
        if ans in ("no",  "n"): return False
        print("  Please type yes or no.")

def ask_amount(prompt: str, hint: str = "") -> float:
    """Ask for a rupee amount. Returns 0 if blank."""
    if hint:
        print(f"  ({hint})")
    for _ in range(100):
        raw = input(f"  {prompt}: Rs. ").strip()
        if raw == "":
            return 0.0
        try:
            val = float(raw.replace(",", ""))
            if val < 0:
                print("  Please enter a positive number.")
                continue
            return val
        except ValueError:
            print("  Please enter a number (e.g. 45000).")

def modify_investments(data: dict):
    """
    Lets user modify or add to existing investments.
    Returns updated data dictionary.
    """

    print("\n--- MODIFY YOUR INVESTMENTS ---")
    print("You can increase or update any of these:\n")
    print("1. PPF")
    print("2. ELSS")
    print("3. LIC")
    print("4. NPS")
    print("5. Health Insurance")
    print("6. Go back\n")

    choice = input("Choose option (1-6): ").strip()

    mapping = {
        "1": "ppf_annual",
        "2": "elss_annual",
        "3": "lic_annual",
        "4": "nps_annual",
        "5": "health_self"
    }

    if choice == "6":
        return data

    if choice not in mapping:
        print("Invalid choice.")
        return data

    key = mapping[choice]

    print(f"\nCurrent value: Rs.{data.get(key, 0):,.0f}")

    print("Do you want to:")
    print("1. Add more")
    print("2. Replace value")

    action = input("Choose (1/2): ").strip()

    try:
        amount = float(input("Enter amount: ").strip())
    except:
        print("Invalid amount.")
        return data

    if action == "1":
        data[key] = data.get(key, 0) + amount
    elif action == "2":
        data[key] = amount
    else:
        print("Invalid option.")

    print("\n✅ Investment updated.\n")
    return data

def plain_language_cli():
    """
    The user is asked ONLY in everyday language.
    No section numbers. No tax jargon. No annual calculations.
    The agent figures out everything behind the scenes.
    """
    print("\n" + "="*65)
    print("   TAX SAVING RECOMMENDATION AGENT")
    print("   Indian Income Tax FY 2024-25 / AY 2025-26")
    print("   Answer in plain language -- we do the tax math.")
    print("="*65)

    data = {}

    # ── INCOME ───────────────────────────────────────────────────────────
    print("\n--- YOUR INCOME ---\n")

    data["monthly_salary"] = ask_amount(
        "How much do you earn per month?",
        "The amount that lands in your bank account, or your gross monthly salary"
    )

    print("\n  What percentage is your 'Basic Pay' in your salary slip?")
    print("  (If you are not sure, just press Enter — we will use 40% which is standard)")
    for _ in range(100):
        raw = input("  Basic Pay % [40]: ").strip()
        if raw == "":
            data["basic_pct"] = 40
            break
        try:
            pct = float(raw)
            if 10 <= pct <= 80:
                data["basic_pct"] = pct
                break
            print("  Please enter a value between 10 and 80.")
        except ValueError:
            print("  Please enter a number like 40 or 50.")

    data["senior_self"] = ask_yn("\nAre you 60 years or older?")

    # ── HOME ──────────────────────────────────────────────────────────────
    print("\n--- YOUR HOME ---\n")

    data["monthly_rent"] = 0
    data["is_metro"]     = False
    if ask_yn("Do you pay rent every month?"):
        data["monthly_rent"] = ask_amount("How much rent do you pay per month?")
        print("\n  Is your city Mumbai, Delhi, Kolkata, or Chennai?")
        data["is_metro"] = ask_yn("  (These are the 4 metro cities for tax purposes)")

    if ask_yn("\nDo you pay a home loan EMI?"):
        data["home_emi_monthly"] = ask_amount(
            "How much is your home loan EMI per month?",
            "We will automatically work out the interest and principal portions"
        )
    else:
        data["home_emi_monthly"] = 0

    if ask_yn("\nDo you pay an education loan EMI? (for your own degree)"):
        data["edu_emi_monthly"] = ask_amount(
            "How much is your education loan EMI per month?",
            "We will automatically work out the interest portion"
        )
    else:
        data["edu_emi_monthly"] = 0

    # ── SAVINGS & INVESTMENTS ─────────────────────────────────────────────
    print("\n--- YOUR SAVINGS & INVESTMENTS ---\n")
    print("  Tell us which of these you have. We will calculate the amounts where we can.\n")

    # EPF
    data["has_epf"] = ask_yn(
        "Does your company deduct PF (Provident Fund) from your salary every month?"
    )
    print("  [Auto-calculated as 12% of your basic pay]" if data["has_epf"] else "")

    # PPF
    data["ppf_annual"] = 0
    if ask_yn("\nDo you put money in PPF (Post Office savings)?"):
        data["ppf_annual"] = ask_amount("How much per year in PPF?")

    # ELSS
    data["elss_annual"] = 0
    if ask_yn("\nDo you invest in an ELSS mutual fund (tax-saving mutual fund)?"):
        data["elss_annual"] = ask_amount("How much per year in ELSS?")

    # LIC
    data["lic_annual"] = 0
    if ask_yn("\nDo you pay premium for a life insurance policy (LIC or any other)?"):
        data["lic_annual"] = ask_amount("How much is the annual premium?")

    # NSC
    data["nsc_annual"] = 0
    if ask_yn("\nDo you buy NSC (National Savings Certificate) from the post office?"):
        data["nsc_annual"] = ask_amount("How much per year?")

    # 5-Year FD
    data["fd5yr_annual"] = 0
    if ask_yn("\nDo you have a 5-year tax-saving Fixed Deposit in a bank?"):
        data["fd5yr_annual"] = ask_amount("How much did you put in this year?")

    # NPS
    data["nps_annual"] = 0
    if ask_yn("\nDo you contribute to NPS (National Pension Scheme)?"):
        data["nps_annual"] = ask_amount(
            "How much per year in NPS?",
            "NPS gives an EXTRA deduction beyond all other investments"
        )

    # ── HEALTH INSURANCE ──────────────────────────────────────────────────
    print("\n--- HEALTH INSURANCE ---\n")

    data["health_self"] = ask_amount(
        "How much do you pay per year for health insurance? (yourself and family)",
        "The annual premium for your mediclaim policy. Enter 0 if you don't have one."
    )

    data["health_parents"] = ask_amount(
        "\nDo you also pay for your parents' health insurance? (per year, 0 if not)",
        "Enter 0 if you don't pay for parents' insurance"
    )

    data["senior_parents"] = False
    if data["health_parents"] > 0:
        data["senior_parents"] = ask_yn("Are your parents 60 years or older?")

    # ── SAVINGS INTEREST ──────────────────────────────────────────────────
    print("\n--- OTHER ---\n")
    data["savings_interest"] = ask_amount(
        "How much interest did you earn from savings accounts or FDs this year?",
        "Check your bank statement — usually a small amount. Enter 0 if unsure."
    )

    # ── RUN AGENT ─────────────────────────────────────────────────────────
    print("\n" + "─"*65)
    print("  Analysing your tax situation...")
    print("─"*65)

    agent = TaxSavingAgent()

    for _ in range(100):

        result = agent.run(data)

    # If no suggestions → already optimal
        if not result["suggestions"]:
            print("\n🎉 You have already optimized your taxes in all possible ways.")
            break

        print("\nDo you want to modify your investments and see if you can save more?")
        choice = input("Type yes or no: ").strip().lower()

        if choice not in ["yes", "y"]:
            print("\n✅ Final plan locked.")
            break

        # Modify investments
        data = modify_investments(data)

        print("\n🔄 Recalculating with updated values...\n")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TEST SCENARIOS  (3 required by rubric)
# All inputs given in plain-language format matching the CLI
# ─────────────────────────────────────────────────────────────────────────────

def run_test_scenarios():
    agent = TaxSavingAgent()

    print("\n" + "#"*65)
    print("  RUNNING 3 TEST SCENARIOS")
    print("  (Inputs are in plain-language format — monthly numbers, yes/no)")
    print("#"*65)

    # ── Scenario 1: Young salaried employee, partial investments ─────────
    print("\n\n=== SCENARIO 1: Young Software Employee, Rs.60,000/month ===")
    print("     Pays rent Rs.12,000/month in Bangalore, has EPF, LIC, education loan")
    agent.run({
        "monthly_salary":  60000,
        "basic_pct":       40,
        "senior_self":     False,
        "monthly_rent":    12000,
        "is_metro":        False,   # Bangalore = non-metro for tax
        "home_emi_monthly":0,
        "edu_emi_monthly": 8000,    # education loan
        "has_epf":         True,    # auto: 12% of basic
        "ppf_annual":      0,
        "elss_annual":     0,
        "lic_annual":      24000,   # Rs.2,000/month LIC
        "nsc_annual":      0,
        "fd5yr_annual":    0,
        "nps_annual":      0,
        "health_self":     6000,
        "health_parents":  0,
        "senior_parents":  False,
        "savings_interest":2000,
    })

    # ── Scenario 2: Mid-career employee, well-invested ───────────────────
    print("\n\n=== SCENARIO 2: Mid-Career Manager, Rs.1,20,000/month ===")
    print("     Pays rent Rs.25,000/month in Mumbai, home loan, good investments")
    agent.run({
        "monthly_salary":  120000,
        "basic_pct":       40,
        "senior_self":     False,
        "monthly_rent":    25000,
        "is_metro":        True,    # Mumbai = metro
        "home_emi_monthly":28000,
        "edu_emi_monthly": 0,
        "has_epf":         True,
        "ppf_annual":      50000,
        "elss_annual":     30000,
        "lic_annual":      0,
        "nsc_annual":      0,
        "fd5yr_annual":    0,
        "nps_annual":      50000,
        "health_self":     25000,
        "health_parents":  50000,
        "senior_parents":  True,    # parents above 60
        "savings_interest":12000,
    })

    # ── Scenario 3: Senior citizen on pension ────────────────────────────
    print("\n\n=== SCENARIO 3: Senior Citizen, Rs.80,000/month pension ===")
    print("     Retired, owns home, PPF and LIC investments, no rent")
    agent.run({
        "monthly_salary":  80000,
        "basic_pct":       40,
        "senior_self":     True,    # above 60, senior citizen slabs apply
        "monthly_rent":    0,
        "is_metro":        False,
        "home_emi_monthly":0,
        "edu_emi_monthly": 0,
        "has_epf":         False,
        "ppf_annual":      150000,
        "elss_annual":     0,
        "lic_annual":      50000,
        "nsc_annual":      0,
        "fd5yr_annual":    0,
        "nps_annual":      0,
        "health_self":     50000,
        "health_parents":  0,
        "senior_parents":  False,
        "savings_interest":80000,   # FD interest -> 80TTB (senior limit Rs.50,000)
    })

    print("\n" + "#"*65)
    print("  ALL SCENARIOS DONE")
    print("#"*65)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_test_scenarios()
    else:
        plain_language_cli()
