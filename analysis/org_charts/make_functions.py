"""Writes data/functions.json: for each insurer, six fixed seats in the ALM chain (investments, ALM, chief actuary,
appointed actuary, finance, risk), what the insurer's own filing says about ALM governance, and an action title.

Lens: MooseDragon/cdn-life-insurer-alm (the project's primary framework). People come from the org files in data/ and
data/inv/, refreshed 2026-11-27 from insurer pages, plus the annual reports and statements held in the ALM repo
(data/raw/<insurer>/...), which name each Appointed Actuary and describe the ALM committees.

Certainty follows README.md: H = insurer's own site / filing / release; M = LinkedIn profile, trade press, or a filing that
later evidence may have overtaken; L = snippet or aggregator; "-" = seat exists or is required but nobody is named publicly.
`inferred` marks a reporting line or remit read from a title. `src` keys: "org:x" / "inv:x" point at the src lines of
data/<id>.txt and data/inv/<id>.txt; other keys are in SOURCES below.

Run: python3 make_functions.py
"""
import json, os

SOURCES = {
    "rbc_ar": ["RBC 2025 Annual Report (year ended 2025-10-31): market risk and insurance risk sections", "https://www.rbc.com/investor-relations/_assets-custom/pdf/ar_2025_e.pdf"],
    "rbc_ricc": ["RBC Insurance Company of Canada 2025 financial statements (copy in the ALM repo, data/raw/rbc): Appointed Actuary's Report signed by Brian Guo, 2025-12-16. This is a separate RBC Insurance entity, not RBC Life", ""],
    "rbc_post": ["RBC job postings 2025-26 that refer to an RBC Insurance CFO team and Chief Actuary (incumbents not named)", "https://www.tealhq.com/job/director-insurance-finance-transformation_7ea1a9d6f5dbc6181166c626318a391f7b7bb"],
    "bmo_fs": ["BMO Life Insurance Company consolidated financial statements, year ended 2025-10-31 (signed 2025-12-04)", "https://www.bmo.com/advisor/PDFs/bmo-life-insurance-company-consolidated-financial-statements-e.pdf"],
    "mfc_mda": ["Manulife 2025 MD&A: risk governance and market & liquidity risk management strategy", "https://www.manulife.com/content/dam/manulife-com/ca/financial-documents/investors/MFC_MDA_2025_Y1_EN.pdf"],
    "mfc_ar": ["Manulife 2025 Annual Report: Appointed Actuary's Report dated 2026-02-11", "https://www.manulife.com/content/dam/manulife-com/ca/financial-documents/investors/MFC_SR_2025_Y1_EN.pdf"],
    "slf_ar": ["Sun Life 2025 Annual Report: risk governance committees; Appointed Actuary's Report signed by Brennan Kennedy, 2026-02-11", "https://www.sunlife.com/content/dam/sunlife/regional/global-marketing/documents/com/annual-report-2025-e.pdf"],
    "slf_ca": ["Sun Life release: Brennan Kennedy appointed SVP & Chief Actuary from 2025-10-04; previously SVP, Global Asset Liability Management", "https://www.sunlife.com/en/newsroom/news-releases/announcement/sun-life-appoints-brennan-kennedy-as-new-chief-actuary/123975/"],
    "clf_ar": ["The Canada Life Assurance Company 2025 Annual Report: Senior Officers list; Appointed Actuary's Report signed by Linda Kerrigan", "https://www.canadalife.com/content/dam/canadalife/documents/corporate/annual-reports/canada-life-2025-annual-report.pdf"],
    "gwo_ar": ["Great-West Lifeco 2025 Annual Report: risk governance (ERMC chaired by the CRO; CRO reports to the CEO and the Board Risk Committee), Investment Committee mandate, ALM strategy", "https://www.greatwestlifeco.com/content/dam/lifeco/documents/investor-relations/reports/2026/annual/lifeco-2025-annual-report.pdf"],
    "clf_jobs": ["Canada Life careers site: ALM analytics, ALM systems and financial risk postings in Winnipeg and London, Ontario (no incumbents named)", "https://jobs.canadalife.com/job/Winnipeg-Manager%2C-ALM-Analytics-&-Platform-Development-MB/1382396733"],
    "ia_ar": ["iA Financial Group 2025 Annual Report: management's responsibility statement, risk management, Total Portfolio Management strategy", "https://ia.ca/-/media/files/ia/investisseurs/rapportsfinanciers/annuel/2026/en/foa-annualreport2025.pdf"],
    "dfs_ar": ["Desjardins Group 2025 Annual Report: Asset/Liability Committee, Note 16 (insurance risk management)", "https://www.desjardins.com/ressources/pdf/d50-rapport-annuel-mcd-2025-t4-e.pdf"],
    "ben_ar": ["Beneva Group 2025 Annual Report (copy in the ALM repo, data/raw/beneva): investment policy and matching, printed pp.106-113", "https://www.beneva.ca/en/media/20911/download"],
    "emp_ar": ["Empire Life 2025 Annual Report: risk governance (Asset Management Committee, Chief Risk Officer), Appointed Actuary's Report signed by Will Featherstonhaugh", "https://www.empire.ca/sites/default/files/2026-04/AnnualReport2025-EN-web.pdf"],
    "emp_2021": ["Empire Life release (2021-12): Edward Gibson named SVP, Capital Management & Chief Actuary", "https://www.newswire.ca/news-releases/empire-life-announces-leadership-appointments-807374483.html"],
    "iva_ar": ["ivari Annual Report 2025: Appointed Actuary's Report signed by Devika Prashad, 2026-02-24; market risk management (ALM working group); risk management function", "https://ivari.ca/files/CS124.pdf"],
    "eql_ar": ["Equitable Annual Report 2025: risk governance, Appointed Actuary's Report signed by Phillip K. Watson, 2026-02-20", "https://equitable.ca/getmedia/8d614bdc-875a-4b2d-8fe7-ac560fbe80b4/annual-report-2025.pdf"],
    "eql_post": ["Equitable job posting, Chief Risk Officer (Waterloo; undated, now closed): role reports to the EVP, Chief Financial Officer", "https://tietalent.com/en/jobs/p-241521736/waterloo-chief-risk-officer"],
    "cop_iar": ["Co-operators Group 2025 Integrated Annual Report: group risk appetite statement (no Co-operators Life statements are public)", "https://www.cooperators.ca/-/media/cooperators/assets/iar/documents/2025-integrated-annual-report.pdf"],
    "cop_2019": ["Insurance Business (2019): Alec Blundell, then VP Individual Insurance & Chief Actuary of Co-operators Life, named EVP & COO", "https://insurancebusinessmag.com/ca/news/breaking-news/the-cooperators-to-name-executive-vicepresident-and-coo-of-life-insurance-business-161929.aspx"],
    "iof_fs": ["Foresters Life Insurance Company 2025 financial statements: Appointed Actuary's Report signed by Trudy Engel; investment policy limits; ALM testing", "https://www.foresters.com/-/media/foresters/documents/pdfs/en-ca/2025-flic-financial-statements-final-ua.pdf"],
    "waw_fs": ["Wawanesa Life 2025 audited financial statements: Appointed Actuary's Report signed by Graham Kent; Note 18 risk management", "https://wawanesa.com/resources/docs/canada/annual-reports/2025-Audited-Wawanesa-Life-Insurance-Company-financial-statements.pdf"],
    "alm_repo": ["MooseDragon/cdn-life-insurer-alm: data/processed/filings_all_long.csv (metric group alm_mandate: verbatim ALM statements with page references) and docs/DATA.md entity register", "https://github.com/MooseDragon/cdn-life-insurer-alm"],
}

ND = "Not publicly named"

def seat(fn, name, title, where, cert, src, inferred=False):
    return {"fn": fn, "name": name, "title": title, "where": where, "cert": cert, "src": src, "inferred": inferred}

def gov(kind, text, src):
    return {"kind": kind, "text": text, "src": src}

F = {}

F["rbc_life"] = {
    "title": "RBC Life: only the CIO is named publicly; five of six seats cannot be seen",
    "lead": "Outside-in, RBC Life shows the least about who holds ALM, actuarial, finance and risk, against a General Account that is 16% repo-financed.",
    "alm_home": "Investments", "inv_seat": "Not published", "combo": None,
    "seats": [
        seat("Investments", "Abid Dobani", "SVP & Chief Investment Officer, RBC Insurance", "RBC Insurance leadership; no executive team is published", "H", ["org:c"]),
        seat("ALM", ND, "Head of ALM, Office of the CIO", "Seat sits in the CIO office; no incumbent visible since July 2025 (LinkedIn)", "-", ["inv:c"], True),
        seat("Chief Actuary", ND, "Chief Actuary, RBC Insurance", "Job postings refer to a CFO team and a Chief Actuary", "-", ["rbc_post"]),
        seat("Appointed Actuary", ND, "Appointed Actuary, RBC Life Insurance Company", "RBC Life's own statements are not public; Brian Guo signs for RBC Insurance Company of Canada, a separate entity", "-", ["rbc_ricc"]),
        seat("Finance", ND, "Chief Financial Officer, RBC Insurance", "Not on any RBC page", "-", ["rbc_post"]),
        seat("Risk", ND, "Chief Risk Officer, RBC Insurance", "Risk appetite is set at bank level", "-", ["rbc_ar"]),
    ],
    "gov": [
        gov("Policy", "\"Our exposure to market risk is managed through our asset/liability management activities, developed to ensure our risk profile remains within the Bank's risk appetite.\"", ["rbc_ar"]),
        gov("Assets", "\"The investments which support actuarial liabilities are predominantly fixed income assets measured at FVTPL.\"", ["rbc_ar"]),
        gov("Committees", "The bank's Asset Liability Committee and Group Risk Management cover the bank's own rate and liquidity risk; no insurer-level ALM or investment committee is described.", ["rbc_ar"]),
    ],
}

F["bmo_life"] = {
    "title": "BMO Life: the CIO, Chief Actuary and CFO all sit on the CEO's leadership team",
    "lead": "The Chief Actuary is also the Appointed Actuary, ALM measurement sits in the CIO office, and the CFO seat was advertised during 2026.",
    "alm_home": "Investments", "inv_seat": "Executive team", "combo": "Chief Actuary is also Appointed Actuary",
    "seats": [
        seat("Investments", "Michael Logan", "Chief Investment Officer, BMO Insurance (since January 2025)", "Senior leadership team under the CEO", "H", ["org:a"]),
        seat("ALM", "Yiwen Zhu", "Director, ALM Measurement & Analysis (since July 2023)", "CIO office (LinkedIn title; line inferred)", "M", ["inv:li4"], True),
        seat("Chief Actuary", "Tim Cavallin", "Chief Actuary", "Senior leadership team under the CEO", "H", ["org:a"]),
        seat("Appointed Actuary", "Timothy Cavallin", "Signed the fiscal 2025 Appointed Actuary's opinion", "Same person as the Chief Actuary", "H", ["bmo_fs"]),
        seat("Finance", "Linda Thorpe", "VP & Chief Financial Officer", "Signed the fiscal 2025 statements; BMO advertised the role in 2026", "M", ["bmo_fs", "org:c"]),
        seat("Risk", ND, "Chief Risk Officer, Insurance", "Seat named in the 2026 CFO posting; partners with the CFO on risk appetite", "-", ["org:c"]),
    ],
    "gov": [
        gov("Board", "\"The Board has established an Investment Policy and Asset Liability Management Policy\"; responsibility for interest rate risk management \"falls to our Investment Committee\".", ["bmo_fs"]),
        gov("Policy", "\"Our policy is to match the interest rates offered to policyholders with equivalent interest yielding assets, designated as FVTPL investments.\"", ["bmo_fs"]),
        gov("Programs", "Risk programs named: asset-liability matching, hedging with derivatives, and quota share reinsurance.", ["bmo_fs"]),
    ],
}

F["manulife"] = {
    "title": "Manulife: CIO, CFO, CRO and Chief Actuary each report to the CEO",
    "lead": "ALM has a global head inside the CIO organisation and its own risk committee; the Chief Actuary seat changed on 12 October 2026.",
    "alm_home": "Investments", "inv_seat": "Executive team", "combo": None,
    "seats": [
        seat("Investments", "Trevor Kreel", "Chief Investment Officer (since August 2024): all general account investments", "Executive Leadership Team; reports to the CEO", "H", ["org:a", "org:n"]),
        seat("ALM", "Ian Roke", "Global Head of Asset Liability Management (Boston; since July 2022)", "CIO organisation (LinkedIn profile; line inferred)", "M", ["inv:li1"], True),
        seat("Chief Actuary", "Sinéad O'Connor", "Chief Actuary (from 12 October 2026; was Global Head of Inforce Management)", "Executive Leadership Team; reports to the CEO", "H", ["org:o"]),
        seat("Appointed Actuary", "Derek Houle", "Appointed Actuary until the Chief Actuary completes Canadian accreditation", "The 2025 opinion was signed by Stephanie Fadous", "H", ["org:o", "mfc_ar"]),
        seat("Finance", "Colin Simpson", "Chief Financial Officer", "Executive Leadership Team; reports to the CEO", "H", ["org:a"]),
        seat("Risk", "Halina von dem Hagen", "Chief Risk Officer", "Executive Leadership Team; reports to the CEO", "H", ["org:a"]),
    ],
    "gov": [
        gov("Management", "\"Market & liquidity risk management strategy is governed by the Global Asset Liability Committee\", one of the risk oversight committees under the Executive Risk Committee.", ["mfc_mda"]),
        gov("Second line", "\"The Chief Actuary and the Actuarial function are considered to have accountability for both the First Line and Second Line duties.\"", ["mfc_mda"]),
        gov("Policy", "General fund philosophy: \"invest in an asset mix that optimizes our risk adjusted returns and matches the characteristics of our underlying liabilities\".", ["alm_repo"]),
    ],
}

F["sun_life"] = {
    "title": "Sun Life: the Chief Actuary came from Global ALM; the CIO sits below the top team",
    "lead": "The CIO works inside the Sun Life Asset Management pillar, the CRO has been interim since 1 January 2026, and a Corporate ALM Committee owns the framework.",
    "alm_home": "Investments", "inv_seat": "Below executive team", "combo": "Chief Actuary is also Appointed Actuary",
    "seats": [
        seat("Investments", "Randy Brown", "Chief Investment Officer (since January 2016): Office of the CIO", "Sun Life Asset Management pillar under Tom Murphy, not the CEO's executive team", "H", ["org:j"], True),
        seat("ALM", "Brent Simmons", "SVP, Global ALM, general account (since October 2025)", "Office of the CIO (LinkedIn profile; line inferred)", "M", ["inv:li2"], True),
        seat("Chief Actuary", "Brennan Kennedy", "SVP & Chief Actuary (since 4 October 2025)", "Previously SVP, Global ALM; reporting line not stated", "H", ["slf_ca"]),
        seat("Appointed Actuary", "Brennan Kennedy", "Signed the 2025 Appointed Actuary's Report", "Same person as the Chief Actuary", "H", ["slf_ar"]),
        seat("Finance", "Tim Deacon", "EVP & Chief Financial Officer", "Executive team; reports to the CEO", "H", ["org:a", "org:b"]),
        seat("Risk", "Jacques Goulet", "EVP & Chief Risk Officer (interim since 1 January 2026)", "Executive team; permanent appointment pending", "H", ["org:b", "org:d"]),
    ],
    "gov": [
        gov("Management", "\"The Corporate Asset Liability Management Committee is responsible for providing oversight and input on the Asset Liability Management framework, policies, guidelines, limits\" and hedging strategy changes.", ["slf_ar"]),
        gov("Management", "An Investment & Credit Risk Committee reviews \"critical matters related to the on-going management of the Company's General Fund\".", ["slf_ar"]),
        gov("Policy", "\"Liabilities having a similar risk profile are grouped together and a customized investment and hedging strategy is developed\" within risk appetite limits.", ["alm_repo"]),
    ],
}

F["canada_life"] = {
    "title": "Canada Life: investments, actuarial, finance and risk are led at Lifeco level",
    "lead": "The Canadian executive page names a CFO and CRO for Canada but no investment or actuarial lead; the Appointed Actuary is a Lifeco senior officer.",
    "alm_home": "Not disclosed", "inv_seat": "Group / affiliate", "combo": None,
    "seats": [
        seat("Investments", "John Melvin", "EVP & Chief Investment Officer, Canada Life and Great-West Lifeco", "Senior officer of the company; Robert Barnes is SVP & CIO, Canada Life (LinkedIn)", "H", ["clf_ar", "inv:li1"]),
        seat("ALM", ND, "Head of ALM", "ALM analytics, ALM systems and financial risk teams are advertised; no head is named", "-", ["clf_jobs"]),
        seat("Chief Actuary", ND, "Chief Actuary", "No Chief Actuary title appears in the senior officers list", "-", ["clf_ar"]),
        seat("Appointed Actuary", "Linda Kerrigan", "SVP & Appointed Actuary", "Senior officer of The Canada Life Assurance Company", "H", ["clf_ar"]),
        seat("Finance", "Jon Nielsen", "EVP & Chief Financial Officer, Canada Life and Lifeco", "Mei Dong is CFO for Canada on the Canadian executive page", "H", ["clf_ar", "org:a"]),
        seat("Risk", "Dervla Tomlin", "EVP & Chief Risk Officer, Canada Life and Lifeco", "Reports to the CEO and the Board Risk Committee; Nancy Hudson is CRO for Canada", "H", ["clf_ar", "gwo_ar", "org:a"]),
    ],
    "gov": [
        gov("Management", "An Executive Risk Management Committee chaired by the CRO is advised by three enterprise-wide sub-committees.", ["gwo_ar"]),
        gov("Board", "The Investment Committee oversees global investment strategy and approves the Investment Policy; the Risk Committee meets with it as appropriate.", ["gwo_ar"]),
        gov("Policy", "\"Asset and liability cash flows are matched within established limits\"; the ALM strategy \"uses public equities and other non-fixed income assets\" to support liabilities.", ["alm_repo"]),
    ],
}

F["ia"] = {
    "title": "iA: one executive is both CFO and Chief Actuary; ALM has an SVP in investments",
    "lead": "The CIO, the CRO and the combined CFO and Chief Actuary each sit on the Executive Committee; the Appointed Actuary is not named in the annual report.",
    "alm_home": "Investments", "inv_seat": "Executive team", "combo": "CFO is also Chief Actuary",
    "seats": [
        seat("Investments", "Alain Bergeron", "EVP & Chief Investment Officer (since September 2019); CEO & CIO, iA Global Asset Management", "Executive Committee", "H", ["org:a"]),
        seat("ALM", "Alexandre Bannon", "SVP, Head of Asset Liability Management, iA Global Asset Management", "CIO organisation (team page; line inferred)", "H", ["inv:c"], True),
        seat("Chief Actuary", "Éric Jobin", "EVP, CFO & Chief Actuary (since August 2023)", "Executive Committee", "H", ["org:a"]),
        seat("Appointed Actuary", ND, "Appointed Actuary, Industrial Alliance Insurance and Financial Services", "Appointed by the subsidiary's Board under the Insurers Act (Quebec); not named", "-", ["ia_ar"]),
        seat("Finance", "Éric Jobin", "EVP, CFO & Chief Actuary", "Executive Committee", "H", ["org:a"]),
        seat("Risk", "Marie-Annick Bonneau", "EVP & Chief Risk Officer", "Executive Committee; the Chief Compliance Officer reports to her", "H", ["org:a", "org:g", "ia_ar"]),
    ],
    "gov": [
        gov("Policy", "Total Portfolio Management strategy \"designed to optimize long-term returns on the assets while maintaining strict asset/liability replicating criteria\".", ["alm_repo"]),
        gov("Board", "Compliance with the investment policy is \"reported to the Board of Directors' Investment Committee at least quarterly\".", ["ia_ar"]),
        gov("Second line", "The Chief Risk Officer \"oversees the risk management function, which spans the entire organization\".", ["ia_ar"]),
    ],
}

F["desjardins"] = {
    "title": "Desjardins: one VP holds finance and corporate actuarial; the group manager runs assets",
    "lead": "DFS lists its own Appointed Actuary, CRO and VP Investments on one management team; rate and liquidity risk go to a group-level Asset/Liability Committee.",
    "alm_home": "Not disclosed", "inv_seat": "Executive team", "combo": "Finance lead also heads corporate actuarial",
    "seats": [
        seat("Investments", "Nicolas Richard", "VP, Investments, DFS (also SMD & Business Head, Desjardins Global Asset Management)", "DFS management team", "H", ["org:b", "org:c"]),
        seat("ALM", ND, "Head of ALM", "No DFS seat named; the group Asset/Liability Committee approves matching strategy", "-", ["dfs_ar"]),
        seat("Chief Actuary", "Alexandre Guertin", "VP, Wealth Management and L&H Insurance Finance & Corporate Actuarial", "DFS management team", "H", ["org:b"]),
        seat("Appointed Actuary", "Nathalie Bouchard", "VP, Corporate Actuarial Services & Appointed Actuary", "DFS management team", "H", ["org:b"]),
        seat("Finance", "Alexandre Guertin", "VP, Wealth Management and L&H Insurance Finance & Corporate Actuarial", "DFS management team", "H", ["org:b"]),
        seat("Risk", "Mario St-Hilaire", "Chief Risk Officer, Life Insurance", "DFS management team", "H", ["org:b"]),
    ],
    "gov": [
        gov("Management", "\"The Asset/Liability Committee supports the Desjardins Group Finance and Risk Management Committee in providing interest rate and liquidity risk\" oversight (group level).", ["dfs_ar"]),
        gov("Policy", "\"A hedging program was implemented by the life and health insurance subsidiary to minimize the impact of interest rate fluctuations on guarantees under segregated fund contracts.\"", ["alm_repo"]),
        gov("Board", "DFS has its own Board Investment Committee (named in a director's biography).", ["dfs_ar"]),
    ],
}

F["beneva"] = {
    "title": "Beneva: no investment, actuarial or risk officer sits on the executive team",
    "lead": "The CIO and the risk head appear only on LinkedIn and in the annual report, placed under Finance by inference; the Board's Investment Committee monitors matching.",
    "alm_home": "Not disclosed", "inv_seat": "Below executive team", "combo": None,
    "seats": [
        seat("Investments", "Hugo Drouin", "VP & Chief Investment Officer (since July 2020)", "Not on beneva.ca; placed under the EVP Finance by inference", "M", ["inv:li1"], True),
        seat("ALM", ND, "Head of ALM", "Matching is done by line of business; no seat named", "-", ["ben_ar"]),
        seat("Chief Actuary", ND, "Chief Actuary", "Not on the management team page", "-", ["org:a"]),
        seat("Appointed Actuary", ND, "Appointed Actuary", "The annual report refers to \"the actuary appointed by the Board\" without a name", "-", ["ben_ar"]),
        seat("Finance", "Mélissa Gilbert", "EVP & Leader, Finance", "Management team; reports to the CEO", "H", ["org:a"]),
        seat("Risk", "Michel Fournier", "VP, Risk Management", "Placed under the EVP Finance by inference", "M", ["org:b"], True),
    ],
    "gov": [
        gov("Policy", "Assets are matched to liabilities by line of business with separate surplus segments; compliance is reviewed monthly.", ["alm_repo"]),
        gov("Board", "Interest rate risk is managed by cash-flow matching with maximum spread limits, reported quarterly to the Board's Investment Committee.", ["alm_repo"]),
        gov("Board", "A sub-committee of the Investment Committee covers investments in private companies.", ["ben_ar"]),
    ],
}

F["empire_life"] = {
    "title": "Empire Life: a management committee, not a named officer, owns ALM",
    "lead": "The CFO changed in November 2026; the leadership page lists no Chief Risk Officer or Chief Actuary, though the annual report describes both roles.",
    "alm_home": "Committee", "inv_seat": "Executive team", "combo": None,
    "seats": [
        seat("Investments", "Paul Holba", "SVP & Chief Investment Officer (CIO since July 2022); President, Empire Life Investments", "Leadership team; reports to the CEO", "H", ["org:a", "org:b"]),
        seat("ALM", ND, "Head of ALM", "The Asset Management Committee monitors ALM practices; no seat named", "-", ["emp_ar"]),
        seat("Chief Actuary", ND, "Chief Actuary", "Edward Gibson was named SVP, Capital Management & Chief Actuary in 2021; not on the current page", "-", ["emp_2021", "org:a"]),
        seat("Appointed Actuary", "Will Featherstonhaugh", "Signed the 2025 Appointed Actuary's Report", "Not on the leadership page", "H", ["emp_ar"]),
        seat("Finance", "Scott Ewert", "SVP & Chief Financial Officer (also VP & CFO, E-L Financial)", "Leadership team; succeeded Rebecca Rycroft in November 2026", "H", ["org:a", "org:c"]),
        seat("Risk", ND, "Chief Risk Officer", "Sits on the Asset Management Committee; shares Board reporting on capital with the CFO", "-", ["emp_ar"]),
    ],
    "gov": [
        gov("Management", "\"The Company has an Asset Management Committee\" overseeing \"market, credit and liquidity risk including asset/liability management as well as capital management\".", ["emp_ar"]),
        gov("Board", "The Investment Committee \"also monitors the Company's asset/liability management activities\"; a Risk and Capital Committee oversees risk and capital.", ["emp_ar"]),
        gov("Policy", "An Equity Risk Hedging Policy supports general fund equity hedging and is reported at least quarterly to the Risk and Capital Committee.", ["alm_repo"]),
    ],
}

F["ivari"] = {
    "title": "ivari: an ALM working group runs market risk; finance and risk are group roles",
    "lead": "ivari publishes no leadership team. Its Appointed Actuary signs locally, while the CFO, CRO and Chief Actuary carry Sagicor group titles.",
    "alm_home": "Investments", "inv_seat": "Below executive team", "combo": None,
    "seats": [
        seat("Investments", "Andrew Bloom", "SVP, Investments (since August 2026)", "LinkedIn profile; no ivari team page", "M", ["inv:li1"]),
        seat("ALM", "Puneet Malik", "AVP, Investments & ALM (since 2020)", "Investment team (LinkedIn; line inferred)", "M", ["inv:li2"], True),
        seat("Chief Actuary", "Nari Persad", "Group Chief Actuary, Sagicor", "Group role with an ivari remit (inferred)", "H", ["org:a"], True),
        seat("Appointed Actuary", "Devika Prashad", "Appointed Actuary: signed the 2025 report", "ivari", "H", ["iva_ar"]),
        seat("Finance", "Kathryn Jenkins", "Chief Financial Officer, ivari (Group CFO, Sagicor)", "Signed the 2025 statements with the CEO", "H", ["org:a", "org:b"]),
        seat("Risk", "Lynda Gauthier", "Group Chief Risk Officer & Chief Sustainability Officer, Sagicor", "Group role; ivari's report describes a CRO directing Risk Management", "H", ["org:a", "org:d", "iva_ar"], True),
    ],
    "gov": [
        gov("Management", "\"The Asset-Liability Management working group oversees key market risk strategies and tactics, reviews compliance with applicable policies and standards and reviews investment and hedging performance.\"", ["alm_repo"]),
        gov("Second line", "The Risk Management function, \"under the direction of the Chief Risk Officer\", works with a Risk and Capital Committee that can adjust or limit risk positions.", ["iva_ar"]),
        gov("Assets", "All invested assets are FVTPL; ETFs support equity-linked universal life account values.", ["alm_repo"]),
    ],
}

F["equitable_life"] = {
    "title": "Equitable: the Chief Actuary is the Appointed Actuary; the CRO reports to the CFO",
    "lead": "CIO, CFO and Chief Actuary are senior management; the CRO is not named, and an Asset Management Committee oversees market and credit risk.",
    "alm_home": "Committee", "inv_seat": "Executive team", "combo": "Chief Actuary is also Appointed Actuary",
    "seats": [
        seat("Investments", "Eugene Lundrigan", "EVP, Chief Investment Officer & Head of Asset Management (since September 2025)", "Senior management; reports to the CEO", "H", ["org:a", "org:b"]),
        seat("ALM", ND, "Head of ALM", "The Asset Management division manages exposures; no seat named", "-", ["eql_ar"]),
        seat("Chief Actuary", "Phillip K. Watson", "SVP, Chief Actuary", "Senior management", "H", ["org:a"]),
        seat("Appointed Actuary", "Phillip K. Watson", "Signed the 2025 Appointed Actuary's Report", "Same person as the Chief Actuary", "H", ["eql_ar"]),
        seat("Finance", "Melanie Kliska", "EVP, Chief Financial Officer", "Senior management; reports to the CEO", "H", ["org:a"]),
        seat("Risk", ND, "Chief Risk Officer", "Seat reports to the EVP, CFO (job posting); not in the senior management list", "-", ["eql_post"]),
    ],
    "gov": [
        gov("Management", "Senior management oversees risk \"through the Senior Risk and Capital Committee and Asset Management Committee\".", ["eql_ar"]),
        gov("Second line", "Risk oversight teams are \"led by the Chief Risk Officer, Chief Compliance Officer, Chief Actuary, and Head of Technology - Risk and Governance\".", ["eql_ar"]),
        gov("Board", "The Investment Committee \"recommends investment and lending policies and objectives for Board approval\".", ["eql_ar"]),
    ],
}

F["cooperators_life"] = {
    "title": "Co-operators Life: the asset manager's CEO sits on the group executive team",
    "lead": "Co-operators Life has no statements or leadership page of its own. Finance is a group role; no risk or actuarial officer is named.",
    "alm_home": "Not disclosed", "inv_seat": "Group / affiliate", "combo": None,
    "seats": [
        seat("Investments", "Ian A. McKinnon", "Chief Investment Officer, Addenda Capital (the group's asset manager)", "Addenda's CEO Roger Beauchemin sits on the group executive team", "H", ["inv:b", "org:a"]),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["cop_iar"]),
        seat("Chief Actuary", ND, "Chief Actuary, Co-operators Life", "Alec Blundell held the title until 2019 and is now EVP & COO of Co-operators Life", "-", ["cop_2019"]),
        seat("Appointed Actuary", ND, "Appointed Actuary, Co-operators Life", "No Co-operators Life statements are public", "-", ["cop_iar"]),
        seat("Finance", "Karen Higgins", "EVP, Finance & Chief Financial Officer, The Co-operators Group", "Group executive team", "H", ["org:a"]),
        seat("Risk", ND, "Chief Risk Officer", "No CRO appears on the group executive team page", "-", ["org:a"]),
    ],
    "gov": [
        gov("Group", "\"Our risk appetite defines the types and amount of risk we are willing and able to responsibly accept\" (group statement; nothing specific to Co-operators Life).", ["alm_repo"]),
        gov("Limits", "The ALM repo builds this insurer from OSFI returns only, because no Co-operators Life financial statements are published.", ["alm_repo"]),
        gov("Assets", "Addenda Capital manages the general account; its Executive Committee is on the investment-team slide.", ["org:b"]),
    ],
}

F["foresters_life"] = {
    "title": "Foresters Life: the Global CFO owns investments and ALM",
    "lead": "The CIO appears only on LinkedIn and likely reports to the CFO. The in-force non-par block is fully coinsured to the parent, so most ALM sits at group level.",
    "alm_home": "Finance", "inv_seat": "Below executive team", "combo": "CFO also owns investments and ALM",
    "seats": [
        seat("Investments", "Clark Wagner", "Chief Investment Officer, Foresters Financial (since April 2023)", "Likely under the Global CFO (LinkedIn; line inferred)", "M", ["inv:li1"], True),
        seat("ALM", "Alvin Sharma", "Global Chief Financial Officer: owns the investment and ALM functions", "Executive team; reports to the CEO", "H", ["org:b"]),
        seat("Chief Actuary", ND, "Chief Actuary", "Not on the senior leadership page", "-", ["org:a"]),
        seat("Appointed Actuary", "Trudy Engel", "Signed the 2025 Appointed Actuary's Report for Foresters Life", "Not on the senior leadership page", "H", ["iof_fs"]),
        seat("Finance", "Alvin Sharma", "Global Chief Financial Officer (since September 2018)", "Executive team; signed the 2025 statements", "H", ["org:a", "iof_fs"]),
        seat("Risk", "Caroline Rendall", "Chief Risk Officer (since July 2023)", "Executive team", "H", ["org:a"]),
    ],
    "gov": [
        gov("Policy", "\"Testing is performed under several interest rate scenarios (including increasing and decreasing rates) to make appropriate provision for reinvestment or disinvestment risk.\"", ["alm_repo"]),
        gov("Board", "A Board-approved Investment Policy limits fixed income to investment grade, common stocks to 10% and preferred stocks to 15% of invested assets; a Risk and Investment Committee sits at Board level.", ["alm_repo", "org:a"]),
        gov("Structure", "The in-force non-par block is 100% quota-share coinsured to the parent (2021), per the ALM repo's entity register.", ["alm_repo"]),
    ],
}

F["canada_protection_plan"] = dict(F["foresters_life"], **{
    "title": "Canada Protection Plan: names no functions of its own; Foresters supplies them",
    "lead": "CPP's policies are underwritten by Foresters Life, so the seats and figures below are Foresters'. cpp.ca names no executives.",
})

F["wawanesa_life"] = {
    "title": "Wawanesa Life: finance, risk and investments come from the P&C parent",
    "lead": "The life company keeps its own actuarial seats; the Board's Investment Committee sets guidelines and receives quarterly duration and matching reports.",
    "alm_home": "Not disclosed", "inv_seat": "Below executive team", "combo": None,
    "seats": [
        seat("Investments", "Wes Peters", "VP, Investments, Wawanesa group (external managers)", "Placed under the group CFO by inference; aggregator profiles only", "L", ["org:d"], True),
        seat("ALM", ND, "Head of ALM", "Assets and liabilities are grouped into funds by liability profile; no seat named", "-", ["waw_fs"]),
        seat("Chief Actuary", ND, "VP, Chief Actuary & Risk Management, Wawanesa Life", "Seat named in the 2025 statements; person not named", "-", ["waw_fs"]),
        seat("Appointed Actuary", "Julia Vul", "VP, Corporate Actuarial & Appointed Actuary (June 2026)", "Graham Kent signed the 2025 opinion", "M", ["org:c", "waw_fs"]),
        seat("Finance", "Gord Dowhan", "SVP, Chief Financial Officer, Wawanesa Mutual", "Group Executive Leadership Team", "H", ["org:a", "org:b"]),
        seat("Risk", "Maja Dos Santos", "SVP, Chief Risk Officer, Wawanesa Mutual (June 2026)", "Group Executive Leadership Team", "M", ["org:c"]),
    ],
    "gov": [
        gov("Policy", "\"Insurance product lines with similar liability profiles and the assets supporting those liabilities are grouped into separate funds.\"", ["alm_repo"]),
        gov("Board", "Fixed income duration ranges sit in the Investment Policy Statement; compliance is reported quarterly to the Board Investment Committee.", ["alm_repo"]),
        gov("Second line", "\"The Offices of the Chief Risk Officer and the Chief Compliance Officer and the Vice President, Chief Actuary & Risk Management\" support the Risk Committee and the Life Risk Committee.", ["waw_fs"]),
    ],
}

F["assumption_life"] = {
    "title": "Assumption Life: one VP is CFO and Chief Actuary and oversees risk",
    "lead": "The same VP's remit covers finance, enterprise risk and corporate actuarial; a wholly owned manager, Louisbourg Investments, runs the assets.",
    "alm_home": "Not disclosed", "inv_seat": "Group / affiliate", "combo": "CFO is also Chief Actuary",
    "seats": [
        seat("Investments", "Luc Gaudet", "President & CEO, Louisbourg Investments (wholly owned asset manager)", "Subsidiary; line to Assumption Life's CFO inferred", "M", ["org:b", "org:c"], True),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["org:a"]),
        seat("Chief Actuary", "Michel Allain", "VP, Chief Financial Officer & Chief Actuary", "Management team; reports to the CEO", "H", ["org:a"]),
        seat("Appointed Actuary", "Lyne Francoeur", "Appointed Actuary", "Leadership team", "H", ["org:a"]),
        seat("Finance", "Michel Allain", "VP, Chief Financial Officer & Chief Actuary", "Management team; reports to the CEO", "H", ["org:a"]),
        seat("Risk", "Isabelle Bourgeois", "Chief Risk Officer & Chief of Internal Audit", "Leadership team (line inferred)", "H", ["org:a"], True),
    ],
    "gov": [
        gov("Remit", "The CFO & Chief Actuary is \"responsible for the company's financial strategies and operations, the enterprise risk management and corporate actuarial activities\".", ["org:a"]),
        gov("Limits", "Assumption Life is outside the ALM repo: it files no OSFI returns, so no balance-sheet view or ALM statement has been collected.", ["alm_repo"]),
    ],
}

F["canadian_premier"] = {
    "title": "Canadian Premier Life: no investment or actuarial lead is named in Canada",
    "lead": "The five-person team puts actuarial under the CFO and risk under the Chief Legal Officer; the portfolio is presumed to be run by the US parent.",
    "alm_home": "Not disclosed", "inv_seat": "Not named", "combo": "CFO also covers actuarial",
    "seats": [
        seat("Investments", ND, "Head of Investments", "Likely at Securian Financial in the US (presumed)", "-", ["org:a"]),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["org:a"]),
        seat("Chief Actuary", ND, "Chief Actuary", "Actuarial sits in the CFO's remit", "-", ["org:b"]),
        seat("Appointed Actuary", ND, "Appointed Actuary", "No statements are public", "-", ["org:a"]),
        seat("Finance", "Marc Peliel", "Chief Financial Officer (finance, actuarial, procurement)", "Leadership team; reports to the CEO", "H", ["org:a", "org:b"]),
        seat("Risk", "Mark Geldernick", "Chief Legal Officer (legal, compliance, risk management)", "Leadership team; reports to the CEO", "H", ["org:a", "org:c"]),
    ],
    "gov": [
        gov("Limits", "The ALM repo keeps this insurer in its OSFI universe but outside the peer views (creditor and group insurer), so no ALM statement has been collected.", ["alm_repo"]),
    ],
}

F["primerica_life"] = {
    "title": "Primerica Life Canada: investments, finance and risk are US group functions",
    "lead": "The Canadian company names a CEO and a President; the group CFO oversees investments run by a third-party adviser.",
    "alm_home": "Not disclosed", "inv_seat": "Group / affiliate", "combo": "Group CFO also oversees investments",
    "seats": [
        seat("Investments", "Tracy Tan", "EVP & CFO, Primerica, Inc. (oversees investments; third-party adviser)", "US group function", "H", ["org:a"], True),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["org:a"]),
        seat("Chief Actuary", ND, "Chief Actuary, Primerica Life Canada", "Not disclosed", "-", ["org:a"]),
        seat("Appointed Actuary", ND, "Appointed Actuary, Primerica Life Canada", "No statements are public", "-", ["org:a"]),
        seat("Finance", "Tracy Tan", "EVP & CFO, Primerica, Inc. (since December 2023)", "US group function", "H", ["org:a"], True),
        seat("Risk", "Stacey K. Geer", "EVP, Chief Governance & Risk Officer, Primerica, Inc.", "US group function", "H", ["org:a"], True),
    ],
    "gov": [
        gov("Limits", "The ALM repo keeps this insurer in its OSFI universe but outside the peer views, so no ALM statement has been collected.", ["alm_repo"]),
    ],
}

F["humania"] = {
    "title": "Humania: actuarial and finance are named; the investment VP is off the web page",
    "lead": "External managers run the general account. The VP, Actuary also covers risk; the Appointed Actuary is not named.",
    "alm_home": "Not disclosed", "inv_seat": "Below executive team", "combo": None,
    "seats": [
        seat("Investments", "Luc Bergeron", "VP, Investment & Special Projects", "In the 2025 Annual Report's executive team; not on the current web page", "M", ["org:b"]),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["org:a"]),
        seat("Chief Actuary", "Alina Dudau", "VP, Actuary", "Executive team; reports to the CEO", "H", ["org:a"]),
        seat("Appointed Actuary", ND, "Appointed Actuary", "Not named", "-", ["org:a"]),
        seat("Finance", "Dimitri Georgoulas", "SVP, Finance (and Treasurer)", "Executive team; reports to the CEO", "H", ["org:a", "org:c"]),
        seat("Risk", ND, "Chief Risk Officer", "No risk seat on the executive team page", "-", ["org:a"]),
    ],
    "gov": [
        gov("Limits", "Humania is AMF-regulated and outside the ALM repo, so no balance-sheet view or ALM statement has been collected.", ["alm_repo"]),
    ],
}

F["uv_insurance"] = {
    "title": "UV Insurance: the Appointed Actuary also runs finance; no investment lead is named",
    "lead": "Actuarial, finance and risk all sit under one senior VP; the management team page lists no investment role.",
    "alm_home": "Not disclosed", "inv_seat": "Not named", "combo": "Appointed Actuary also leads finance",
    "seats": [
        seat("Investments", ND, "Head of Investments", "No investment role on the management team page", "-", ["org:a"]),
        seat("ALM", ND, "Head of ALM", "Not disclosed", "-", ["org:a"]),
        seat("Chief Actuary", "Hugo Boutin-Ouellet", "VP, Corporate Actuarial", "Reports to the SVP, Actuarial & Finance", "H", ["org:a", "org:d"]),
        seat("Appointed Actuary", "Pierre Parenteau", "SVP, Actuarial & Finance; Appointed Actuary", "Management team; reports to the CEO", "H", ["org:a"]),
        seat("Finance", "Pierre Parenteau", "SVP, Actuarial & Finance; Appointed Actuary", "Management team; reports to the CEO", "H", ["org:a"]),
        seat("Risk", "Eric Timmons", "Chief, Risk Management", "Placed under the SVP, Actuarial & Finance by inference", "H", ["org:a"], True),
    ],
    "gov": [
        gov("Limits", "UV is AMF-regulated and outside the ALM repo, so no balance-sheet view or ALM statement has been collected.", ["alm_repo"]),
    ],
}

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for k, v in F.items():
        assert [s["fn"] for s in v["seats"]] == ["Investments", "ALM", "Chief Actuary", "Appointed Actuary", "Finance", "Risk"], k
        assert len(v["title"]) <= 88, (k, len(v["title"]))
        for s in v["seats"]:
            assert (s["name"] == ND) == (s["cert"] == "-"), (k, s["fn"])
            for key in s["src"]:
                assert key.startswith(("org:", "inv:")) or key in SOURCES, (k, key)
        for g in v["gov"]:
            for key in g["src"]:
                assert key.startswith(("org:", "inv:")) or key in SOURCES, (k, key)
    json.dump({"sources": SOURCES, "insurers": F}, open(os.path.join(here, "data", "functions.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote data/functions.json:", len(F), "insurers")
