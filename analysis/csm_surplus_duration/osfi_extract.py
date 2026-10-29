"""Pull the OSFI data points used for the CSM and surplus duration estimates (fiscal 2025 Q4, primary entity per company)."""
import csv, gzip, collections, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OSFI = ROOT / "data" / "osfi"
OUT = pathlib.Path(__file__).with_name("osfi_inputs.csv")
YEAR, QUARTER = "2025", "Q4"

PRIMARY = {
    "bmo_life": "BMO Life Assurance Company",
    "canada_life": "The Canada Life Assurance Company",
    "canadian_premier": "Canadian Premier Life Insurance Company",
    "cooperators_life": "Co-operators Life Insurance Company",
    "empire_life": "The Empire Life Insurance Company",
    "equitable_life": "The Equitable Life Insurance Company of Canada",
    "foresters_life": "Foresters Life Insurance Company",
    "ivari": "ivari",
    "manulife": "The Manufacturers Life Insurance Company",
    "primerica_life": "Primerica Life Insurance Company of Canada",
    "rbc_life": "RBC Life Insurance Company",
    "sun_life": "Sun Life Assurance Company of Canada",
    "wawanesa_life": "The Wawanesa Life Insurance Company",
}

# field -> (return, address); amounts in C$000s
FIELDS = {
    # LF2 investment schedule: col 11 FVTPL, 16 FVOCI, 36 amortized cost, 40 balance sheet value
    **{f"{cls}_{basis}": ("LF2", f"P21012{row}{col}")
       for cls, row in [("short_term", "010"), ("bonds", "479"), ("mortgages", "500"), ("preferred", "599"),
                        ("common", "659"), ("other_loans", "810"), ("other_invested", "820"), ("total_inv", "889")]
       for basis, col in [("fvtpl", "11"), ("fvoci", "16"), ("amortized", "36"), ("bsv", "40")]},
    "bonds_govt_fed_ig": ("LF2", "P2101204540"), "bonds_prov_ig": ("LF2", "P2101205540"),
    "bonds_muni_ig": ("LF2", "P2101214040"), "bonds_corp_pub_ig": ("LF2", "P2101221040"),
    "bonds_corp_priv_ig": ("LF2", "P2101241040"),
    "aoci_fvoci_recycling": ("LF2", "P7004270021"), "aoci_fvoci_no_recycling": ("LF2", "P7004285321"),
    "oci_fvoci_bonds_chg": ("LF2", "P7004214021"), "oci_fvoci_loans_chg": ("LF2", "P7004211021"),
    "oci_fvoci_reclass": ("LF2", "P7004221021"), "oci_fvoci_equities_chg": ("LF2", "P7004246521"),
    "oci_ifie": ("LF2", "P7004246321"),
    "cash": ("LF1", "P2000201001"), "intangibles": ("LF1", "P2000213001"), "goodwill": ("LF1", "P2000214001"),
    "shareholders_equity": ("LF1", "P2000459901"), "total_equity": ("LF1", "P2000469901"),
    "csm_liab_lca": ("LCA", "D2040010025"), "csm_asset_lca": ("LCA", "D2040010015"),
    "csm_remaining_issued": ("LF3", "P3508529999"), "csm_remaining_reins": ("LF3", "P3508539999"),
    "csm_recognised_canada": ("LF3", "P4501502099"),
    "liab_ind_ins": ("LF3", "P2201002501"), "liab_ind_ann": ("LF3", "P2201005501"),
    "liab_grp_ins": ("LF3", "P2201012501"), "liab_grp_ann": ("LF3", "P2201015501"),
    "liab_par": ("LF3", "P2201051001"), "liab_total_canada": ("LF3", "P2201081901"),
    "liab_grand_total": ("LF3", "P2202031901"),
    "available_capital": ("LCQ", "D1010010030"), "licat_total_ratio": ("LCQ", "D1010010020"),
}


def main():
    wanted = collections.defaultdict(set)
    for ret, addr in FIELDS.values():
        wanted[ret].add(addr)
    vals = {}
    for ret, addrs in wanted.items():
        with gzip.open(OSFI / f"{ret}_core.csv.gz", "rt") as fh:
            for r in csv.DictReader(fh):
                if r["fiscal_year"] == YEAR and r["quarter"] == QUARTER and r["address"] in addrs \
                        and PRIMARY.get(r["company_id"]) == r["entity"]:
                    vals[(r["company_id"], ret, r["address"])] = r["value"]
    # out-of-Canada CSM recognised (P45025, column 99 totals) summed when present
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["company_id", "entity"] + list(FIELDS))
        for cid, ent in sorted(PRIMARY.items()):
            w.writerow([cid, ent] + [vals.get((cid, ret, addr), "") for ret, addr in FIELDS.values()])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
