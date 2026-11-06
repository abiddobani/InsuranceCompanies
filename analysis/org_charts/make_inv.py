"""Writes data/inv/<id>.txt (investment-team charts: CIO -> direct reports -> their teams).
People found on LinkedIn carry their profile slug; P = confirmed on the profile on 2026-11-06 (certainty M),
S = search snippet / search card only (certainty L). Other people cite source keys copied from data/<id>.txt.
Reporting lines below the CIO are inferred from titles (~) unless a source states them."""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
LI = "https://www.linkedin.com/in/"

def main_srcs(i):
    s = {}
    for line in open(os.path.join(HERE, "data", i + ".txt"), encoding="utf8"):
        m = re.match(r"src:\s*(\w+)\s*\|", line)
        if m: s[m.group(1)] = line.strip()
    return s

# person tuple: (level, name, title, ref, inferred) ; ref = "P:slug" | "S:slug" | "H:a,b" | "M:a" | "L:a" | "-"
SPEC = {
"rbc_life": dict(name="RBC Life Insurance (RBC Insurance)", anchor="SVP & Chief Investment Officer, RBC Insurance", people=[
  ("L1","Abid Dobani","SVP & Chief Investment Officer","H:c",0),
  ("L2","Andre C. Lewis","Senior Director & Head, Total Fund Management (Office of the CIO), since Aug 2025","P:andreclewis",1),
  ("L3","Mayooran Mahadevan","Director, PM, Global Credit & Rates (USD 25B long-only mandate), since Jan 2026","P:mmahadevan",1),
  ("L3","Song Shi","Director, Investment, since Nov 2025","P:song-shi-20556499",1),
  ("L3","Mehvish Shahid","Lead Portfolio Manager, since Sep 2025","S:mehvish-shahid-913035239",1),
  ("L3","Jeff Collins","Senior Portfolio Manager","S:jeff-collins-2270a23",1),
  ("L2","Imran Chaudhry","Senior Director & Head, Trading, since Feb 2026","P:imchaudhry",1),
  ("L3","David Chai","Director, Investments (derivatives, collateral, liquidity), since Mar 2026","P:david-chai-cfa",1),
  ("L2","Robert Izsak","Head, Mortgages & Commercial Real Estate, since Sep 2022","P:robert-izsak-86574b19",1),
  ("L2","Not publicly named","Head of ALM (vacant on LinkedIn since Hanling Zhou left, Jul 2025)","-",0),
  ("L2","Jesse Waugh","Senior Manager, Investment Risk Oversight (front office), since Nov 2025","S:jesse-waugh",1),
], notes=["Direct reports and teams are inferred from LinkedIn titles; Abid can correct the lines. Andrew Smith (Director, Private Placements) retired Jan 2023 and no successor is visible on LinkedIn."]),
"bmo_life": dict(name="BMO Life Assurance (BMO Insurance)", anchor="Chief Investment Officer, BMO Insurance", people=[
  ("L1","Michael Logan","Chief Investment Officer, since Jan 2025 (RBC Insurance until Jan 2025)","H:a",0),
  ("L2","Hanling Zhou","MD, Head of Portfolio Management, Global Investment Office, since Aug 2025","P:hanlingzhou",1),
  ("L3","Lauren Wheeler (Saunders)","Senior Portfolio Manager, since Jun 2025","P:lauren-wheeler-saunders-19372655",1),
  ("L3","Karen Medeiros","Senior Manager, Investments, since May 2024","P:karen-medeiros-62b85b249",1),
  ("L2","Yiwen Zhu","Director, ALM Measurement & Analysis, since Jul 2023","P:yiwen-zhu-34276834",1),
  ("L2","Anna Boldyreva","Senior Manager, Risk Management","S:annabold",1),
], notes=["Logan's LinkedIn profile confirms the CIO role from Jan 2025. Aleem Qureshi (MD, Head of Institutional Insurance) left for Sun Life in Jul 2026."]),
"manulife": dict(name="Manulife", anchor="Chief Investment Officer, Manulife (all US, Canadian and Asian general account)", people=[
  ("L1","Trevor Kreel","Chief Investment Officer, since Aug 2024","H:a,n",0),
  ("L2","Ian Roke","Global Head of Asset Liability Management (Boston), since Jul 2022","P:ian-roke-430a4836",1),
  ("L3","Tam Nhan","Director, Models & Analytics, Global ALM, since Jan 2023","P:tam-nhan-602b3875",1),
  ("L3","Ammar Dalal","Director, Investment Strategy, Global ALM","S:dalalammar",1),
  ("L3","Leonid Kelner","AVP & Actuary, ALM (Montreal)","S:leonid-kelner-fsa-fcia-04a84015",1),
  ("L2","Blake Witherington","Chief Credit Officer, since Sep 2023","P:blake-witherington-cfa-a313129",1),
  ("L3","Patrick Richardson","MD, Head of Canadian Credit, since Mar 2019","P:patrick-richardson-58118654",1),
  ("L3","Ian MacNeil","Global Head of Workouts & Recovery","S:ian-macneil-634a7425",1),
  ("L2","Matthew Waisnor","MD, Global Portfolio Manager, general account real estate, since Sep 2025","P:matthew-waisnor-36bba7b",1),
  ("L2","Nigel Gonsalves","AVP, Head of Global Equity & ALDA Risk Oversight (general account)","S:nigelpgonsalves",1),
  ("L2","Colin Purdie","Global CIO, Public Markets, Manulife IM (reports to Paul Lorentz; runs public GA assets)","H:i",1),
  ("L3","Isha Aggarwal","VP & Senior MD, Public Sector, Global Corporate Finance (public fixed income and private placements)","P:isha-aggarwal-a1b5355",1),
  ("L3","Scott Cherry","Senior Director, Sovereigns & Supranationals","S:cherryscott",1),
  ("L2","Anne Valentine Andrews","Global Head of Private Markets, Manulife IM (reports to Paul Lorentz)","H:j",1),
  ("L3","Jay Pratt","Global CCO & SMD, Private Markets and general account investments","S:jay-pratt-a8479312",1),
  ("L3","Bruce Anderson","MD, Power & Infrastructure Debt","S:bruce-anderson-0351872b",1),
  ("L3","Tony M.","AVP & MD, Real Estate Finance (commercial mortgages, Toronto)","S:tony-m-ba4b671a4",1),
  ("L3","Meghan Henselwood","MD, Transactions, Canadian CRE (general account and third party)","S:mhenselwood",1),
  ("L3","Silvana Mansard","MD, Head of Portfolio Strategy & Leasing, Real Estate","S:silvanamansard",1),
  ("L3","Jennifer R. Schillaci","MD & Head of Real Estate Equity Investments","S:jennifer-r-schillaci-cfa-31311524",1),
  ("L2","Not publicly named","Head of Canada general account / Global Head of Portfolio Management (Kreel's former role)","-",0),
], notes=["Purdie and Andrews report to Paul Lorentz (Global WAM) and manage general-account assets as a service; they are dashed here as functional lines to the CIO. No Canada general-account head or successor to Kreel's former Global Head of Portfolio Management role was found."]),
"sun_life": dict(name="Sun Life Financial", anchor="Chief Investment Officer, Sun Life (Office of the CIO; SLC Management executive committee)", people=[
  ("L1","Randy Brown","Chief Investment Officer, since Jan 2016","H:j",0),
  ("L2","Bryan Rowe","SMD, Global Portfolio Management (team supporting the general account), since Mar 2022","P:bryanrowe",1),
  ("L2","Brent Simmons","SVP, Global ALM (general account), since Oct 2025","P:brent-simmons-17472013",1),
  ("L3","Logan Kowalchuk","VP, Canada ALM, since Nov 2025","P:logan-kowalchuk",1),
  ("L2","Elaad Keren","SMD, Co-Head Private Fixed Income, SLC Management (Toronto), since Jan 2024","P:elaad-keren-6642a71ba",1),
  ("L3","Luke Meng","Senior Director, Private Fixed Income","S:lukemeng",1),
  ("L3","Daniel Bernholtz","Senior Director, Private Fixed Income","S:danielbernholtz",1),
  ("L2","Andrew Kleeman","SMD, Co-Head Private Fixed Income, SLC Management (Wellesley), since Jan 2024","P:andrew-kleeman-49622622",1),
  ("L2","Marc Hurley","Co-Lead, Canadian Public Fixed Income, since Mar 2025 (SMD, Canadian & UK Public FI since Jul 2018)","P:marc-hurley-a579b21",1),
  ("L3","Todd Williamson","Senior Director, UK & Canadian Public Fixed Income","S:todd-williamson-2658409",1),
  ("L3","Martin Ng","Senior Director, Public Fixed Income","S:ngmartin",1),
  ("L3","Edward Ling","Director, Public Fixed Income","S:edward-ling-cfa-89691840",1),
  ("L3","Hayley Dawson","Director, Public Fixed Income","S:hayleyrdawson",1),
  ("L3","Christophe Frappier-Hudon","Director, Public Fixed Income (Montreal)","S:christophe-frappier-hudon-fsa-cfa-156935105",1),
  ("L3","Rabia Yusufzai","Director, Public Fixed Income, Credit Research","S:rabiayusufzai",1),
  ("L2","Randall (Randy) Malcolm","Co-Lead, Canadian Public Fixed Income, since Mar 2025","P:randall-randy-malcolm-cfa-74924812",1),
  ("L2","Not publicly named","Head of Canadian Commercial Mortgages (BGO / Sun Life Mortgage Investments)","-",0),
  ("L3","Phil Dougherty","MD & Portfolio Manager, Commercial Mortgages, since Jan 2024","P:phil-dougherty-cfa-9b413516",1),
  ("L2","Foad Azima","MD, Private Credit, Sun Life Capital Management","S:foadazima",1),
  ("L2","Bart Holl","MD, Head of Insurance Strategy, SLC Management","S:bart-holl-4a295122",1),
  ("L2","Marco Galvan","MD, Investment Research","S:galvanm",1),
  ("L2","Philip Gillan","Senior Managing Director","S:philip-gillan-2131109",1),
  ("L2","Aleem Qureshi","SVP, Head of Insurance Solutions, Sun Life AM (from ~Jul 2026)","S:aleem-qureshi-024a8812b",1),
], notes=["BGO is the brand used by the Sun Life Mortgage Investments teams; the overall head of Canadian commercial mortgages was not found. David J. Fletcher (MD, Private Fixed Income) left in Oct 2023 and is excluded."]),
"canada_life": dict(name="Canada Life", anchor="SVP & Chief Investment Officer, Canada Life (within Great-West Lifeco's investment organisation under John Melvin, EVP & CIO)", people=[
  ("L1","Robert Barnes","SVP & Chief Investment Officer, since Apr 2025","P:robert-barnes-cfa-076180147",0),
  ("L2","Ron Hanson","SVP, Bond Investments, since May 2023","P:ron-hanson-0359a424",1),
  ("L3","Brendan Hargrave","MD, Portfolio Management & Trading, Bond Investments, since Oct 2018","P:brendan-hargrave-cfa-735b4545",1),
  ("L3","Katie Woodward","Senior Director, Bond Investments, since Jan 2026","P:katie-woodward-cfa-3461b746",1),
  ("L2","Gaurav Mittal","SVP, Head of Global Private Debt (over C$30B), since Jan 2022","P:gaurav-mittal-13a50b",1),
  ("L3","Sébastien Munsch","Senior Managing Director, private placements / private credit, since Jul 2025","P:sébastien-munsch-084b1540",1),
  ("L3","Marina Gert","MD, Global Private Debt, since Jan 2020","S:marina-gert-cfa-8532636",1),
  ("L3","Jason Ward","MD, Private Debt Investments, since Jan 2021","S:jason-ward-00308316",1),
  ("L3","Jackie Jun He","MD, Private Debt Investments, since 2014","S:jackiehecfa",1),
  ("L3","Yvette Dennis","MD, Global Private Debt","S:yvette-dennis-23514229",1),
  ("L3","Mariano Ficocelli","MD, Global Private Debt","S:mariano-ficocelli-95295722",1),
  ("L3","Michael Caranci","VP, Head of Infrastructure & Project Finance","S:michael-caranci-10837112",1),
  ("L2","Not publicly named","Head of Mortgage Investments","-",0),
  ("L3","Willson Shih","SMD, Mortgage Investments Origination, since Aug 2025","P:willson-shih-b7447850",1),
  ("L3","Suvir Haripersad","SMD, Mortgage Investments Portfolio Management & Fund Manager, since Jan 2023","S:suvirh",1),
  ("L3","Jim Anderson","SMD, Mortgage Operations","S:jim-anderson-cfa-541ab312",1),
  ("L3","Michael Cohen","MD, Mortgage Origination, since Oct 2019","S:michael-cohen-004490132",1),
  ("L2","Vince Coupland","AVP, Investment Operations","S:vince-coupland-cpa-cga",1),
], notes=["Canada Life's general account is run inside Great-West Lifeco's investment organisation; John Melvin (Lifeco EVP & CIO) sits above Barnes."]),
"ia": dict(name="iA Financial Group", anchor="EVP & Chief Investment Officer, iA (also CEO & CIO, iA Global Asset Management, which runs the general fund)", people=[
  ("L1","Alain Bergeron","EVP & CIO, since Sep 2019","H:a",0),
  ("L2","Tej Rai","MD, Head of General Funds & Asset Allocation, since May 2026","H:c",1),
  ("L2","Alexandre Bannon","SVP, Head of Asset Liability Management","H:c",1),
  ("L2","Dominic Siciliano","SVP, Head of Fixed Income, since Oct 2021","H:c",1),
  ("L2","Stéfanie Leduc","SVP, Head of Corporate Bonds & Private Debt, since Apr 2024","H:c",1),
  ("L3","Giampiero (JP) D'Agnillo","VP, Principal PM, Corporate Credit, since Jun 2018","S:giampiero-jp-d-agnillo-cfa-233b7a30",1),
  ("L2","Claude Sirois","MD, Real Assets & Private Equity","H:c",1),
  ("L2","Jean-René Adam","MD, Head of Investment Funds, Public Equities","H:c",1),
  ("L2","Jean-Pierre Cornillaut","MD, Chief Operating Officer, Investments","H:c",1),
  ("L2","Francis Jacob-Roy","VP, Head of Investment Risk","H:c",1),
  ("L2","Jonathan Mercier","SVP, Head of Strategy & Transformation","H:d",0),
  ("L2","Pavel Kuperman","VP & Head, Investment Strategy & Client Solutions","S:pavel-kuperman-cfa",1),
], notes=["Team from the iA Global Asset Management team page; LinkedIn confirmed Rai, Siciliano and Leduc and added role start dates. Only Mercier's bio states the reporting line."]),
"beneva": dict(name="Beneva (SSQ + La Capitale)", anchor="VP & Chief Investment Officer, Beneva (not named on beneva.ca)", people=[
  ("L1","Hugo Drouin","VP & Chief Investment Officer, since Jul 2020","P:hugo-drouin",0),
  ("L2","Carl Cleary","VP, Investissements, since Jan 2024 (previously VP Corporate Development)","P:carl-cleary-23270940",1),
  ("L2","Eric Blackburn","Director, Investment Strategies & Risk, since Jul 2020","P:eric-blackburn-mba-456078118",1),
  ("L2","Emmanuelle Roberge","Director, Private Investments & External Management, since May 2023","P:emmanuelle-roberge-mba-cfa-972bbb45",1),
  ("L3","François Beaubien-Plante","Director, Investment, Private Debt & Equity, since May 2023","S:francois-beaubien-plante",1),
  ("L3","Mathieu Roy","Portfolio Manager, Infrastructure","S:mathieu-roy-cfa-0b5837a9",1),
], notes=["Carl Cleary's role may be strategic or corporate investments rather than the general account."]),
"desjardins": dict(name="Desjardins Insurance", anchor="VP, Investments, DFS, and SMD & Business Head, Desjardins Global Asset Management (DGAM runs the general fund; no insurer-side CIO found)", people=[
  ("L1","Nicolas Richard","VP, Investments (also SMD & Business Head, DGAM)","H:b,c",0),
  ("L2","Christian Duceppe","MD & CIO, Public Markets, DGAM","H:c",1),
  ("L3","Tommy Nguyen","VP, Head of Global Equities, DGAM","S:tommy-nguyen-7745342",1),
  ("L2","Frédéric Angers","MD & Global CIO, Private Markets, DGAM","H:c",1),
  ("L3","Guillaume Morency","VP, Head of Infrastructure Investments, DGAM","S:guillaumemorency",1),
  ("L2","Guy Lamontagne","MD & Chief of Investment Strategy, DGAM","H:c",1),
  ("L2","Frederick Tremblay","VP, Investment Solutions, DFS","H:b",1),
], notes=["George Mavroudis is President & CEO of DGAM and Guardian Capital (LinkedIn search snippet only)."]),
"empire_life": dict(name="Empire Life", anchor="SVP & CIO, Empire Life; President & CIO, Empire Life Investments", people=[
  ("L1","Paul Holba","SVP & CIO (CIO since Jul 2022; President of Empire Life Investments since May 2025)","H:a,b",0),
  ("L2","Geoff Johnston","Leads Fixed Income & Private Placements team","H:b",1),
  ("L3","Ian Fung","Senior Portfolio Manager, Fixed Income, since Jul 2023","P:fungian",1),
  ("L3","Michael Schroeter","Private Placements (general fund private debt)","H:b",1),
  ("L2","Albert Ngo","Senior PM & Head of Alternative Assets","H:b",1),
  ("L3","Adrian Dolgan","Senior Investment Strategist (real estate, PE, infrastructure)","S:adrian-dolgan",1),
  ("L2","Ashley Misquitta","Senior PM & Investment Strategist (US & global equities)","H:b",1),
  ("L3","Neeraj Khosla","PM, Global Equities","S:khoslaneeraj",1),
  ("L2","Jennifer Law","Senior PM, Canadian Equities","H:b",1),
  ("L2","Doug Cooper","Senior Portfolio Manager, since Jan 2019","P:doug-cooper-cfa-b17b8350",1),
  ("L2","Lynn Guo","Director","P:lynn-guo-525a44372",1),
  ("L2","Nitasha Ragnauth","CFO, Empire Life Investments, since Sep 2023","S:nitasha-ragnauth-cpa-ca-266957149",1),
], notes=["Roles from the Empire Life Investments team page and LinkedIn; neither gives reporting lines."]),
"equitable_life": dict(name="Equitable Life of Canada", anchor="EVP & Chief Investment Officer, Equitable (Head of Asset Management)", people=[
  ("L1","Eugene Lundrigan","EVP, CIO & Head of Asset Management, since Sep 2025","H:a,b",0),
  ("L2","Mark Warywoda","VP, Public Portfolio Management, since Jan 2023","P:mark-warywoda-68951811b",1),
  ("L3","Johanna Shaw","Director, Portfolio Management","P:johanna-shaw-548119294",1),
  ("L2","Karl Brecht","Head of Alternative Investments, since Mar 2020","P:karlbrecht",1),
  ("L2","Darrin Webley","AVP, Private Investments, since Jan 2023","P:darrin-webley-34938474",1),
  ("L3","Liam Phelan","Director, Private Investments, since Jan 2026","P:liam-phelan-929650127",1),
], notes=["Lundrigan succeeded Tara Proper (EVP & CIO, Sep 2021 to Dec 2025). Paul English (SVP Investments) retired Dec 2021."]),
"ivari": dict(name="ivari", anchor="SVP, Investments, ivari (Sagicor group)", people=[
  ("L1","Andrew Bloom","SVP, Investments, since Aug 2026","P:andrew-d-bloom",0),
  ("L2","Puneet Malik","AVP, Investments & ALM, since 2020","P:malikpuneet",1),
], notes=["ivari publishes no team; both names are from LinkedIn."]),
"cooperators_life": dict(name="Co-operators Life Insurance Company", anchor="CIO, Addenda Capital (Co-operators' asset manager, which runs the general account)", people=[
  ("L1","Ian A. McKinnon","Chief Investment Officer, Addenda Capital","H:b",0),
  ("L2","Adam Kot","EVP, Commercial Mortgages, Addenda Capital","H:b",1),
  ("L2","Diane Young","VP, Portfolio Management & Strategy, Addenda Capital, since Sep 2026","S:diane-young-cfa-66a55415",1),
], notes=["Roger Beauchemin (President & CEO, Addenda) sits above the CIO."]),
"foresters_life": dict(name="Foresters Life Insurance Company", anchor="Chief Investment Officer, Foresters Financial (also covers Canada Protection Plan)", people=[
  ("L1","Clark Wagner","Chief Investment Officer, since Apr 2023 (also CIO Feb 2016 to Jun 2022)","P:clark-wagner-30201a92",0),
], notes=["foresters.com lists no CIO; Wagner's LinkedIn profile confirms the title. He likely reports to Alvin Sharma (Global CFO, Investments & ALM). No team below him is visible."]),
"canada_protection_plan": dict(name="Canada Protection Plan", anchor="Foresters Financial's Chief Investment Officer (CPP policies are underwritten by Foresters Life)", people=[
  ("L1","Clark Wagner","Chief Investment Officer, Foresters Financial, since Apr 2023","P:clark-wagner-30201a92",0),
], notes=["Same investment team as Foresters Life."]),
"wawanesa_life": dict(name="Wawanesa Life", anchor="VP, Investments, Wawanesa group (oversees external managers for the P&C and Life companies)", people=[
  ("L1","Wes Peters","VP, Investments","L:d",0),
  ("L2","Maja Hildebrand","Senior Investment Analyst, Wawanesa Insurance","S:maja-hildebrand-cfa-b45ab554",1),
], notes=["No CIO or investment head visible on LinkedIn; Wes Peters comes from aggregator profiles only."]),
"uv_insurance": dict(name="UV Insurance", anchor="Investment lead not published (UV's management team lists no investment role)", people=[
  ("L1","Not publicly named","Head of Investments","-",0),
], notes=["No investment staff visible on UV's site or LinkedIn (only sales and finance hits)."]),
"assumption_life": dict(name="Assumption Life", anchor="VP, CFO & Chief Actuary, Assumption Life (remit includes investment strategy)", people=[
  ("L1","Michel Allain","VP, CFO & Chief Actuary (finance, ERM, actuarial, investment strategy)","H:a",0),
  ("L2","Luc Gaudet","President & CEO, Louisbourg Investments (wholly owned asset manager)","M:b,c",1),
], notes=["No investment staff visible on LinkedIn beyond Louisbourg's CEO."]),
"canadian_premier": dict(name="Canadian Premier Life (Securian Canada)", anchor="No Canadian investment head; portfolio presumed run by the US parent's asset manager", people=[
  ("L1","Not publicly named","Head of Investments (likely at Securian Financial, US)","-",0),
], notes=["No investment team visible on Securian Canada's site or LinkedIn."]),
"primerica_life": dict(name="Primerica Life (Canada)", anchor="Group CFO of Primerica, Inc. oversees investments (run by a third-party adviser)", people=[
  ("L1","Tracy Tan","EVP & CFO, Primerica, Inc. (group function; oversees investments)","H:a",0),
], notes=["No Canadian investment team found on LinkedIn."]),
"humania": dict(name="Humania Insurance", anchor="VP, Investment & Special Projects, Humania (external managers under a Board investment committee)", people=[
  ("L1","Luc Bergeron","VP, Investment & Special Projects","M:b",0),
], notes=["No investment staff below the VP visible on LinkedIn."]),
}

CERT = {"P": "M", "S": "L"}
for i, d in SPEC.items():
    ms = main_srcs(i)
    used, li, out_people = set(), [], []
    for lvl, name, title, ref, inf in d["people"]:
        if ref == "-": cert, keys = "-", ""
        else:
            kind, val = ref.split(":", 1)
            if kind in ("P", "S"):
                k = f"li{len(li)+1}"
                li.append(f"src: {k} | LinkedIn profile, read 2026-11-06 ({'confirmed on profile' if kind=='P' else 'search snippet only, not confirmed'}) | {LI}{val}")
                cert, keys = CERT[kind], k
            else:
                cert, keys = kind, val
                used.update(val.split(","))
        out_people.append(f"{lvl} | {name} | {title} | {cert} | {keys}" + (" | ~" if inf else ""))
    lines = [f"id: {i}", f"name: {d['name']}", f"anchor: {d['anchor']}"]
    lines += [ms[k] for k in sorted(used)] + li + out_people + [f"note: {n}" for n in d["notes"]]
    open(os.path.join(HERE, "data", "inv", i + ".txt"), "w", encoding="utf8").write("\n".join(lines) + "\n")
print("wrote", len(SPEC))
