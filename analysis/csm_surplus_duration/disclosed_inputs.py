"""Hand-entered fiscal 2025 disclosures that the ALM repo's processed files do not carry.

C$ millions. Maturity and run-off bands are (start year, end year or None for the open band, amount).
Everything else in the build comes from MooseDragon/cdn-life-insurer-alm (data/processed, deck/, research/).
"""

# ALM repo short ID -> company_id in the earlier version's results (v1_results_2026-10-29.csv)
V1_ID = {"RBC": "rbc_life", "BMO": "bmo_life", "MFC": "manulife", "SLF": "sun_life", "CLF": "canada_life", "EMP": "empire_life",
         "IVA": "ivari", "EQL": "equitable_life", "COP": "cooperators_life", "IOF": "foresters_life", "WAW": "wawanesa_life",
         "IAG": "ia", "BEN": "beneva", "DFS": "desjardins"}

# Companies on the project's list that the ALM repo does not cover. Adding a peer is a decision the repo reserves for its owner.
_NOT_IN_REPO = "Not in the ALM repo's peer set, so not rebuilt on the new basis. The earlier estimate (2026-10-29) is not comparable with these results."
NOT_REBUILT = {
    "Assumption Life": _NOT_IN_REPO,
    "Canadian Premier Life": _NOT_IN_REPO,
    "Primerica Life": _NOT_IN_REPO,
    "Humania": _NOT_IN_REPO,
    "UV Insurance": _NOT_IN_REPO,
    "Canada Protection Plan": "Inside Foresters Life (no separate filing).",
}

# Foresters Life 2025 financial statements: "Composition of assets supporting liabilities and surplus" (Dec 31, 2025)
# and the interest rate risk table (change in the balance sheet value for a 1% parallel shift, before tax).
FORESTERS_SEGMENTS = {
    "Insurance": dict(short_term=0.429, bonds=417.587, stocks=10.104, preferred=32.684, other_invested=14.857),
    "Surplus": dict(cash=33.175, short_term=11.591, bonds=239.582, stocks=0.0, preferred=24.906, other_invested=31.351),
    "insurance_fi_per_1pct": [26.804, 23.345],
    "surplus_fi_per_1pct": [14.193, 12.452],
    "source": "Foresters Life 2025 FS: assets supporting liabilities and surplus by segment; interest rate risk table "
              "(1% shift: financial instruments backing insurance liabilities 26.8 / 23.3, surplus instruments 14.2 / 12.5)",
}

AMF = {
    "IAG": dict(
        csm_bands=[(0, 1, 746), (1, 5, 2214), (5, 10, 1805), (10, None, 2423)],
        csm_scope="iA consolidated, insurance contracts issued", csm_source="iA 2025 FS note 13 D), expected recognition of the CSM",
        bonds=[(0, 1, 1163), (1, 5, 3058), (5, 10, 3870), (10, None, 22989)],
        loans=[(0, 1, 371), (1, 5, 1294), (5, 10, 1151), (10, None, 41)],
        bonds_source="iA 2025 FS, interest rate risk note: bonds and loans by maturity (consolidated general fund)",
        sens=[
            dict(basis="iA consolidated", shock="-50 bps", measure="equity", value=-25, definition="Immediate parallel shift, net of tax", source="iA 2025 MD&A p.75-76"),
            dict(basis="iA consolidated", shock="-50 bps", measure="net_income", value=0, definition="Immediate parallel shift, net of tax", source="iA 2025 MD&A p.75-76"),
            dict(basis="iA consolidated", shock="-50 bps", measure="csm", value=-50, definition="Immediate parallel shift, before tax", source="iA 2025 MD&A p.75-76"),
        ],
        fvoci_source="iA 2025 FS: bonds are carried at FVTPL",
        fvoci={},
        oci_text="No FVOCI debt: rate moves go through net income (equity -25 for -50 bps, C$MM, consolidated)",
    ),
    "BEN": dict(
        csm_bands=[(0, 1, 111.3), (1, 5, 223.4), (5, 10, 194.4), (10, None, 349.8)],
        csm_scope="Beneva consolidated, insurance contracts issued", csm_source="Beneva 2025 AR note 18, timing of expected CSM recognition",
        bonds=[(0, 1, 271.5), (1, 5, 2820.9), (5, 10, 928.9), (10, None, 2403.3)],
        private_debt=[(0, 1, 13.4), (1, 5, 50.3), (5, 10, 131.3), (10, None, 181.7)],
        loans=[(0, 1, 245.7), (1, 5, 690.9), (5, 10, 42.2), (10, None, 1.2)],
        bonds_source="Beneva 2025 AR note 7, maturities of debt securities, private debt and loans (consolidated, incl. P&C)",
        oci_per_1pct=(75.9 + 69.0) / 2, fvoci_bonds=2536.8,
        oci_source="Beneva 2025 AR note 7: 1% shift moves OCI by +75.9 / -69.0; FVOCI bonds C$2,537MM (note 5)",
        sens=[
            dict(basis="Beneva consolidated (incl. P&C)", shock="-100 bps", measure="net_income", value=3.3, definition="Immediate parallel shift", source="Beneva 2025 AR note 7"),
            dict(basis="Beneva consolidated (incl. P&C)", shock="-100 bps", measure="oci", value=75.9, definition="Immediate parallel shift", source="Beneva 2025 AR note 7"),
            dict(basis="Beneva consolidated (incl. P&C)", shock="+100 bps", measure="oci", value=-69.0, definition="Immediate parallel shift", source="Beneva 2025 AR note 7"),
            dict(basis="Beneva consolidated (incl. P&C)", shock="-100 bps", measure="csm", value=-10.6, definition="Immediate parallel shift", source="Beneva 2025 AR note 7"),
        ],
        fvoci_source="Beneva 2025 AR note 5, carrying amount by classification (consolidated, incl. P&C)",
        fvoci=dict(fvoci_mm=3360, amortized_cost_mm=1526, fvoci_fixed_income_mm=2537, fvoci_ac_fixed_income_mm=3162),
        oci_text="-100 bps: +75.9; +100 bps: -69.0 (C$MM, Beneva consolidated)",
    ),
    "DFS": dict(
        csm_bands=[(0, 1, 193), (1, 2, 179), (2, 3, 166), (3, 4, 154), (4, 5, 143), (5, 10, 571), (10, None, 1193)],
        csm_scope="Desjardins life and health subsidiary, insurance contracts issued",
        csm_source="Desjardins Group 2025 combined FS, CSM recognition table",
        sens=[
            dict(basis="Desjardins life and health subsidiary", shock="-100 bps", measure="equity", value=42, definition="Insurance activities, net of tax", source="Desjardins Group 2025 combined FS note 16"),
            dict(basis="Desjardins life and health subsidiary", shock="-100 bps", measure="net_income", value=11, definition="Insurance activities, net of tax", source="Desjardins Group 2025 combined FS note 16"),
            dict(basis="Desjardins life and health subsidiary", shock="-100 bps", measure="csm", value=-22, definition="Insurance activities", source="Desjardins Group 2025 combined FS note 16"),
            dict(basis="Desjardins life and health subsidiary", shock="-100 bps", measure="equity", value=13, component="instruments not held for insurance activities",
                 definition="Financial instruments not held for insurance activities, net of tax", source="Desjardins Group 2025 combined FS note 16"),
            dict(basis="Desjardins life and health subsidiary", shock="+100 bps", measure="equity", value=-14, component="instruments not held for insurance activities",
                 definition="Financial instruments not held for insurance activities, net of tax", source="Desjardins Group 2025 combined FS note 16"),
        ],
        fvoci_source="No public balance sheet for the life subsidiary (ALM repo L42)",
        fvoci={},
        oci_text="Instruments not held for insurance activities: equity +13 for -100 bps, -14 for +100 bps (C$MM)",
    ),
}

# What each insurer says in public about limits on rate, OCI or surplus exposure. Statements are the ALM repo's
# alm_mandate rows (data/processed/filings_all_long.csv) unless a filing is named. No insurer publishes a numeric OCI or FVOCI limit.
LIMITS = {
    "RBC": dict(text="No quantitative limit published. Market risk is managed through asset/liability management 'to ensure our risk profile remains within the Bank's risk appetite'.",
                source="RBC 2025 Annual Report (insurance risk), ALM repo alm_mandate rows",
                note="Supporting assets are 'predominantly fixed income assets measured at FVTPL'; the FVOCI and amortized cost book is close to equity plus CSM."),
    "BMO": dict(text="Risk Appetite Statement is 'defined in both quantitative and qualitative terms'; the quantities are not given. Policy is to match policyholder rates with FVTPL assets.",
                source="BMO Life 2025 FS, ALM repo alm_mandate rows", note="Small FVOCI book; nearly all assets at FVTPL."),
    "MFC": dict(text="No numeric limit published. Aggregate market risk is managed against limits tied to earnings and capital volatility under the Risk Appetite Framework.",
                source="Manulife 2025 MD&A, ALM repo alm_mandate rows",
                note="FVOCI debt backs liabilities under the IFRS 17 OCI option, so the FVOCI book is not a surplus book."),
    "SLF": dict(text="No numeric limit published. Liabilities with a similar risk profile are grouped and managed 'within our risk appetite limits'.",
                source="Sun Life 2025 MD&A and FS note 6, ALM repo alm_mandate rows",
                note="FVOCI fixed income is 'held primarily backing surplus, investment contracts and CSM liabilities' (group)."),
    "CLF": dict(text="No numeric limit published. 'Asset and liability cash flows are matched within established limits.'",
                source="Great-West Lifeco 2025 MD&A, ALM repo alm_mandate rows", note=""),
    "EMP": dict(text="No numeric limit published. Capital market risk is accepted 'provided it is managed within specific risk tolerances'; the equity hedging policy sets risk limits that are not printed.",
                source="Empire Life 2025 Annual Report, ALM repo alm_mandate rows", note="All bonds at FVTPL: no OCI exposure to rates."),
    "IVA": dict(text="No numeric limit published. An asset-liability management working group reviews compliance with market risk policies and standards.",
                source="ivari 2025 FS, ALM repo alm_mandate rows", note="All invested assets at FVTPL: no OCI exposure to rates."),
    "EQL": dict(text="Investment guidelines 'specify minimum and/or maximum limits for each asset class, industry and any individual issuer'; the numbers are not printed.",
                source="Equitable 2025 Annual Report, ALM repo alm_mandate rows", note="No FVOCI or amortized cost assets."),
    "COP": dict(text="No company-level statement. The group describes a risk appetite with limits on assumed risks; no numbers.",
                source="The Co-operators Group 2025 Annual Report (group level), ALM repo alm_mandate rows", note=""),
    "IOF": dict(text="Common stocks limited to 10% of invested assets, preferred stocks to 15%, any one investee to 5% of the bond portfolio. No rate or OCI limit published.",
                source="Foresters Life 2025 FS, ALM repo alm_mandate rows", note="No FVOCI assets; the only peer that publishes the assets supporting surplus."),
    "WAW": dict(text="The Investment Policy Statement sets an allowed duration range for fixed income; the range is not printed. Largest corporate exposure 2.0% of general fund assets, within limits.",
                source="Wawanesa Life 2025 Annual Report, ALM repo alm_mandate rows", note="No FVOCI assets."),
    "BLU": dict(text="No public statement (no Canadian financial statements).", source="ALM repo alm_mandate rows", note=""),
    "IAG": dict(text="No numeric limit published. Total Portfolio Management keeps 'strict asset/liability replicating criteria'; the strategy balances after-tax return and capital protection.",
                source="iA 2025 MD&A p.81 and FS note 7, ALM repo alm_mandate rows", note="Bonds at FVTPL."),
    "BEN": dict(text="Interest rate risk is managed by cash-flow matching with maximum spread limits reported quarterly to the Investment Committee; the limits are not printed. Separate surplus segments exist but are not published.",
                source="Beneva 2025 Annual Report p.59, ALM repo alm_mandate rows", note="Consolidated, includes property and casualty."),
    "DFS": dict(text="Policies 'define exposure limits for each type of investment as well as limits by issuer'; numbers not published.",
                source="Desjardins Group 2025 combined FS note 16, ALM repo alm_mandate rows", note=""),
}
