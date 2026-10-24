"""Step 1, `prepare`: cases_candidates.csv -> mapping.csv. NO Qloo calls.

PRE-REGISTRATION RULE: mapping.csv is the pre-registered mapping table. It is generated from the
frozen labels, reviewed, and COMMITTED BEFORE ANY QLOO SCORE IS COMPUTED (i.e. before `resolve`
and `score` run in live mode). After that commit it may change only to fix a documented
transcription error, in a separate commit and before any further scoring run; never because a
Qloo score disagrees with it. `prepare` therefore refuses to overwrite an existing mapping.csv
whose content differs from what it would generate (pass --force to regenerate deliberately).

Everything here is deterministic:
- query strings: a generic cleaning rule (strip parentheticals, keep the first "/", ";" or ","
  segment, drop trailing descriptor words such as "word marks" / "trade dress", title-case
  all-caps names) plus an explicit override table (`QUERY_OVERRIDES`) for rows where the mark
  text is not a searchable brand name (descriptions of the accused use, product-line marks,
  same-name parties). Each override carries its reason into the `query_note` column.
- same_category: a keyword lexicon over the two goods phrases; the bucket of the EARLIEST
  matching keyword (after removing parentheticals) is the phrase's category.
- labels: relatedness and channels/purchasers labels are combined; disagreement -> "mixed",
  which is excluded.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path
from typing import Any

from tearose.eval.backtest.common import CASES_CSV, MAPPING_CSV, read_csv
from tearose.qloo.fixtures import slugify

DECIDED = ("favors_plaintiff", "neutral", "favors_defendant")
LABEL_CODE = {"favors_defendant": 0, "neutral": 1, "favors_plaintiff": 2}

MAPPING_COLUMNS = [
    "case_id",
    "dispute_id",
    "case_name",
    "year",
    "confidence",
    "senior_query",
    "junior_query",
    "query_note",
    "senior_goods_phrase",
    "junior_goods_phrase",
    "senior_category",
    "junior_category",
    "same_category",
    "factor_relatedness",
    "factor_channels",
    "include_relatedness",
    "label_relatedness",
    "relatedness_exclusion",
    "include_fame",
    "label_fame",
]

# --------------------------------------------------------------------------------------
# Category lexicon (same_category heuristic)
# --------------------------------------------------------------------------------------

# Singular, lowercase tokens. "sports/fitness" is an addition to the planned list: home exercise
# machines and golf equipment (Bowflex, Toucan Gold) fit no other bucket.
CATEGORY_LEXICON: dict[str, tuple[str, ...]] = {
    "apparel/footwear": (
        "apparel", "clothing", "jean", "shirt", "tshirt", "lingerie", "footwear", "shoe",
        "sneaker", "boot", "handbag", "bag", "tote", "purse", "luggage", "accessory", "leather",
        "activewear", "outsole", "garment", "hat", "sock",
    ),
    "food": (
        "food", "cereal", "snack", "cheese", "ham", "hamburger", "burger", "restaurant", "taco",
        "pizza", "candy", "chocolate", "grocery", "meat", "chip", "treat",
    ),
    "beverage/alcohol": (
        "beverage", "drink", "whiskey", "whisky", "bourbon", "vodka", "tequila", "rum", "gin",
        "wine", "champagne", "beer", "coffee", "coffeehouse", "tea", "juice", "water", "soda",
        "spirit", "liquor",
    ),
    "pet": ("pet", "dog", "cat", "puppy", "kitten"),
    "cosmetics": ("cosmetic", "fragrance", "perfume", "makeup", "skincare", "beauty", "lipstick"),
    "jewelry/watches": ("jewelry", "jewellery", "ring", "diamond", "watch", "wristwatch"),
    "tech/electronics": (
        "software", "electronic", "audio", "radio", "speaker", "amplifier", "computer", "phone",
        "nft", "app", "headphone",
    ),
    "media/entertainment": (
        "music", "song", "recording", "book", "film", "movie", "magazine", "entertainment",
        "educational", "education", "university",
    ),
    "retail/services": (
        "retail", "marketplace", "resale", "store", "shop", "advertising", "keyword", "search",
        "ecommerce",
    ),
    "financial": ("bank", "banking", "insurance", "credit", "financial", "payment"),
    "auto": ("car", "automobile", "automotive", "vehicle", "truck", "tire", "motorcycle"),
    "toys/games": ("toy", "doll", "puzzle", "boardgame"),
    "household": ("furniture", "kitchen", "cookware", "appliance", "mug", "houseware", "bedding"),
    "sports/fitness": ("exercise", "fitness", "golf", "putter", "gym"),
}  # fmt: skip

_KEYWORD_TO_BUCKET = {kw: b for b, kws in CATEGORY_LEXICON.items() for kw in kws}
_PAREN_RE = re.compile(r"\([^()]*\)")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def strip_parentheticals(text: str) -> str:
    prev = None
    while prev != text:
        prev, text = text, _PAREN_RE.sub(" ", text)
    return " ".join(text.split())


def category_of(goods_phrase: str) -> str:
    """Bucket of the earliest lexicon keyword in the phrase (parentheticals removed).

    "Tennessee whiskey; licensed merchandise incl. dog collars" -> "beverage/alcohol" (whiskey
    comes before dog). Returns "unknown" when no keyword matches.
    """
    for tok in _WORD_RE.findall(strip_parentheticals(goods_phrase).lower()):
        bucket = _KEYWORD_TO_BUCKET.get(_singular(tok)) or _KEYWORD_TO_BUCKET.get(tok)
        if bucket:
            return bucket
    return "unknown"


def same_category(senior_goods: str, junior_goods: str) -> tuple[str, str, str]:
    """(senior bucket, junior bucket, "yes"|"no"). Unknown never counts as a match."""
    a, b = category_of(senior_goods), category_of(junior_goods)
    return a, b, "yes" if a == b and a != "unknown" else "no"


# --------------------------------------------------------------------------------------
# Query strings
# --------------------------------------------------------------------------------------

_DESCRIPTOR_TAIL = {
    "word", "words", "mark", "marks", "trade", "dress", "logo", "logos", "design", "designs",
    "registered", "and", "bottle", "monogram", "pattern", "stitching", "seal", "image",
    "images", "stylized",
}  # fmt: skip
_QUOTES = "\"'“”‘’"


def _smart_title(text: str) -> str:
    """Title-case an all-caps name, keeping apostrophes intact: JACK DANIEL'S -> Jack Daniel's."""
    letters = [c for c in text if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters):
        return text
    return " ".join(
        "-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")) for w in text.split()
    )


def clean_mark(mark: str) -> str:
    """Generic rule: mark text -> brand search string (see module docstring)."""
    text = strip_parentheticals(mark)
    text = re.split(r"/|;|,", text)[0]
    words = text.strip().strip(_QUOTES).split()
    while words and words[-1].lower().strip(_QUOTES) in _DESCRIPTOR_TAIL:
        words.pop()
    return _smart_title(" ".join(words).strip(_QUOTES + " "))


# Explicit, reviewed overrides: case_id -> {side: (query, reason)}. Applied instead of the
# generic rule. They exist because the mark column describes the accused USE rather than naming
# the junior BRAND, names a product line or design instead of the brand, or both parties share a
# name (Coach). Fixed before any score is computed (see module docstring).
QUERY_OVERRIDES: dict[str, dict[str, tuple[str, str]]] = {
    "taco_bell_ip_holder_llc_v_spicy_seasonings_llc_taco_johns_taco_tuesday_2023": {
        "senior": ("Taco John's", "registrant brand, not the phrase"),
        "junior": ("Taco Bell", "petitioner; mark column is 'n/a'"),
    },
    "in_n_out_burgers_v_smashburger_ip_holder_llc_2019": {
        "senior": ("In-N-Out", "brand, not the menu-item mark"),
        "junior": ("Smashburger", "brand, not the menu-item mark"),
    },
    "adidas_america_inc_v_thom_browne_inc_2026": {
        "senior": ("adidas", "brand, not the stripe mark"),
        "junior": ("Thom Browne", "brand, not the stripe designs"),
    },
    "tiffany_and_co_v_costco_wholesale_corp_2020": {
        "senior": ("Tiffany & Co.", "full brand name"),
        "junior": ("Costco", "accused user; mark column describes signage"),
    },
    "starbucks_corp_v_wolfes_borough_coffee_inc_2013": {
        "junior": ("Black Bear Micro Roastery", "accused user's brand"),
    },
    "starbucks_corp_v_wolfes_borough_coffee_inc_2009": {
        "junior": ("Black Bear Micro Roastery", "accused user's brand"),
    },
    "coach_services_inc_v_triumph_learning_llc_2012": {
        "junior": ("Triumph Learning", "same-name junior; searching COACH would hit the senior"),
    },
    "vans_inc_v_mschf_product_studio_inc_2023": {
        "senior": ("Vans", "brand, not the shoe model"),
        "junior": ("MSCHF", "accused user's brand"),
    },
    "rolex_watch_usa_inc_v_beckertime_l_l_c_2024": {
        "junior": ("BeckerTime", "accused user; mark column describes the use"),
    },
    "hermes_international_v_rothschild_2023": {
        "senior": ("Hermès", "house brand rather than the BIRKIN product line"),
        "junior": ("MetaBirkins", "accused NFT project name"),
    },
    "the_pennsylvania_state_university_v_vintage_brand_llc_2024": {
        "senior": ("Penn State", "brand name without descriptors"),
        "junior": ("Vintage Brand", "accused user; mark column describes the use"),
    },
    "nike_inc_v_stockx_llc_2025": {
        "junior": ("StockX", "accused user; mark column describes the use"),
    },
    "chanel_inc_v_wgaca_llc_what_goes_around_comes_around_2024": {
        "junior": ("What Goes Around Comes Around", "accused user; mark column describes use"),
    },
    "tiffany_nj_inc_v_ebay_inc_2010": {
        "senior": ("Tiffany & Co.", "full brand name"),
        "junior": ("eBay", "accused user; mark column describes the use"),
    },
    "gucci_america_inc_v_guess_inc_2012": {
        "senior": ("Gucci", "brand, not the pattern marks"),
        "junior": ("Guess", "brand, not the pattern marks"),
    },
    "levi_strauss_and_co_v_abercrombie_and_fitch_trading_co_2011": {
        "senior": ("Levi's", "brand, not the stitching design"),
        "junior": ("Abercrombie & Fitch", "accused user's brand (Ruehl was its sub-line)"),
    },
    "kraft_foods_group_brands_llc_v_cracker_barrel_old_country_store_inc_2013": {
        "senior": ("Cracker Barrel Cheese", "Kraft's cheese brand; plain name hits the junior"),
        "junior": ("Cracker Barrel Old Country Store", "the restaurant/retail chain"),
    },
    "fiji_water_co_v_fiji_mineral_water_usa_llc_2010": {
        "senior": ("Fiji Water", "brand name"),
    },
    "mattel_inc_v_mca_records_inc_2002": {
        "junior": ("MCA Records", "accused user; the junior use is a song title"),
    },
    "dr_seuss_enterprises_l_p_v_comicmix_llc_2020": {
        "senior": ("Dr. Seuss", "brand; the mark is a book title"),
        "junior": ("ComicMix", "accused user's brand"),
    },
    "playboy_enterprises_inc_v_netscape_communications_corp_2004": {
        "junior": ("Netscape", "accused user; the junior use is keyword advertising"),
    },
    "kellogg_co_v_toucan_golf_inc_2003": {
        "senior": ("Froot Loops", "consumer brand carrying the Toucan Sam mark"),
    },
    "nautilus_group_inc_v_icon_health_and_fitness_inc_2004": {
        "junior": ("CrossBow", "brand spelling; generic 'crossbow' is a weapon"),
    },
    "louis_vuitton_malletier_v_dooney_and_bourke_inc_2006": {
        "senior": ("Louis Vuitton", "brand, not the monogram"),
        "junior": ("Dooney & Bourke", "accused user's brand"),
    },
    "louis_vuitton_malletier_s_a_v_my_other_bag_inc_2016": {
        "senior": ("Louis Vuitton", "brand, not the monogram"),
        "junior": ("My Other Bag", "accused user's brand"),
    },
    "christian_louboutin_s_a_v_yves_saint_laurent_america_holding_inc_2012": {
        "senior": ("Christian Louboutin", "brand, not the red-sole mark"),
        "junior": ("Yves Saint Laurent", "accused user's brand"),
    },
    "adidas_america_inc_v_payless_shoesource_inc_2008": {
        "senior": ("adidas", "brand, not the stripe mark"),
        "junior": ("Payless ShoeSource", "accused user's brand"),
    },
    "adidas_america_inc_v_skechers_usa_inc_2018": {
        "senior": ("adidas", "brand, not the trade dress"),
        "junior": ("Skechers", "accused user's brand"),
    },
    "abercrombie_and_fitch_stores_inc_v_american_eagle_outfitters_inc_2002": {
        "senior": ("Abercrombie & Fitch", "brand, not the trade dress"),
        "junior": ("American Eagle Outfitters", "accused user's brand"),
    },
    "board_of_supervisors_for_lsu_v_smack_apparel_co_2008": {
        "senior": ("LSU", "lead plaintiff's brand (four universities sued)"),
        "junior": ("Smack Apparel", "accused user's brand"),
    },
    "makers_mark_distillery_inc_v_diageo_north_america_inc_2012": {
        "senior": ("Maker's Mark", "brand, not the wax-seal mark"),
        "junior": ("Jose Cuervo", "brand of the accused Reserva de la Familia line"),
    },
    "pom_wonderful_llc_v_hubbard_2014": {
        "junior": ("Pur Beverages", "accused user; searching 'pom' would hit the senior"),
    },
    "jl_beverage_co_v_jim_beam_brands_co_2016": {
        "senior": ("Johnny Love Vodka", "brand without the lips design"),
        "junior": ("Pucker Vodka", "accused brand without the lips design"),
    },
    "fortune_dynamic_inc_v_victorias_secret_stores_brand_management_inc_2010": {
        "junior": ("Victoria's Secret Pink", "accused user's line (PINK)"),
    },
    "jack_wolfskin_ausrustung_fur_draussen_gmbh_v_new_millennium_sports_s_l_u_2015": {
        "senior": ("Kelme", "brand, not the paw-print design"),
        "junior": ("Jack Wolfskin", "brand, not the paw-print design"),
    },
    "kate_spade_llc_v_saturdays_surf_llc_2013": {
        "senior": ("Saturdays NYC", "trading name of SATURDAYS SURF NYC"),
    },
    "multi_time_machine_inc_v_amazon_com_inc_2015": {
        "junior": ("Amazon", "accused user; the junior use is search results"),
    },
    "bose_corp_v_qsc_audio_products_inc_2002": {
        "senior": ("Bose", "house brand of the WAVE marks"),
        "junior": ("QSC", "house brand of POWERWAVE"),
    },
    "louis_vuitton_malletier_v_burlington_coat_factory_warehouse_corp_2005": {
        "senior": ("Louis Vuitton", "brand, not the monogram"),
        "junior": ("Burlington", "accused retailer"),
    },
    "rosetta_stone_ltd_v_google_inc_2012": {
        "junior": ("Google", "accused user; the junior use is keyword advertising"),
    },
}


def ascii_slug(text: str) -> str:
    """slugify after folding accents (Hermès -> hermes)."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return slugify(folded)


def case_id_for(row: dict[str, str]) -> str:
    return f"{ascii_slug(row['case_name'])}_{row['year'].strip()}"


# --------------------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------------------


def combine_labels(relatedness: str, channels: str) -> tuple[str, str]:
    """(label, exclusion_reason); the reason is "" when the row is usable.

    Both factor labels decided and equal -> that label; decided and different -> "mixed"
    (excluded); only one decided -> that one; neither -> excluded as "unread" if either is
    unread, else "not_discussed".
    """
    rel, ch = relatedness.strip(), channels.strip()
    r = rel if rel in DECIDED else ""
    c = ch if ch in DECIDED else ""
    if r and c:
        return (r, "") if r == c else ("mixed", "mixed")
    if r or c:
        return r or c, ""
    if "unread" in (rel, ch):
        return "", "unread"
    return "", "not_discussed"


def build_mapping(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: dict[str, int] = {}
    unused = set(QUERY_OVERRIDES)
    for case in cases:
        cid = case_id_for(case)
        seen[cid] = seen.get(cid, 0) + 1
        if seen[cid] > 1:
            cid = f"{cid}_{seen[cid]}"
        senior_q, junior_q = clean_mark(case["senior_mark"]), clean_mark(case["junior_mark"])
        notes: list[str] = []
        over = QUERY_OVERRIDES.get(cid, {})
        unused.discard(cid)
        if "senior" in over:
            senior_q = over["senior"][0]
            notes.append(f"senior override: {over['senior'][1]}")
        if "junior" in over:
            junior_q = over["junior"][0]
            notes.append(f"junior override: {over['junior'][1]}")
        s_goods, j_goods = case["senior_goods"].strip(), case["junior_goods"].strip()
        s_cat, j_cat, same = same_category(s_goods, j_goods)
        label, excl = combine_labels(
            case["factor_relatedness_of_goods"], case["factor_channels_purchasers"]
        )
        fame = case["fame_found"].strip()
        rows.append(
            {
                "case_id": cid,
                "dispute_id": ascii_slug(f"{senior_q} vs {junior_q}"),
                "case_name": case["case_name"].strip(),
                "year": case["year"].strip(),
                "confidence": case["confidence"].strip(),
                "senior_query": senior_q,
                "junior_query": junior_q,
                "query_note": "; ".join(notes) or "generic rule",
                "senior_goods_phrase": s_goods,
                "junior_goods_phrase": j_goods,
                "senior_category": s_cat,
                "junior_category": j_cat,
                "same_category": same,
                "factor_relatedness": case["factor_relatedness_of_goods"].strip(),
                "factor_channels": case["factor_channels_purchasers"].strip(),
                "include_relatedness": "yes" if label and not excl else "no",
                "label_relatedness": label,
                "relatedness_exclusion": excl,
                "include_fame": "yes" if fame in ("yes", "no") else "no",
                "label_fame": fame if fame in ("yes", "no") else "",
            }
        )
    if unused and len(cases) == len({case_id_for(c) for c in cases}) and len(cases) > 40:
        # Only checked on the full case file: an override that matches no case is a silent
        # mapping bug (e.g. a renamed case) and must be loud instead.
        raise ValueError(f"QUERY_OVERRIDES entries match no case: {sorted(unused)}")
    return rows


def render_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    rel = [r for r in rows if r["include_relatedness"] == "yes"]
    fame = [r for r in rows if r["include_fame"] == "yes"]
    return {
        "cases": len(rows),
        "relatedness_included": len(rel),
        "relatedness_labels": _count([r["label_relatedness"] for r in rel]),
        "relatedness_excluded": _count(
            [r["relatedness_exclusion"] for r in rows if r["include_relatedness"] != "yes"]
        ),
        "relatedness_disputes": len({r["dispute_id"] for r in rel}),
        "channels_only_included": sum(r["factor_channels"] in DECIDED for r in rows),
        "relatedness_only_included": sum(r["factor_relatedness"] in DECIDED for r in rows),
        "fame_included": len(fame),
        "fame_labels": _count([r["label_fame"] for r in fame]),
        "same_category_yes_in_relatedness_set": sum(r["same_category"] == "yes" for r in rel),
        "unknown_category_phrases": sum(
            (r["senior_category"] == "unknown") + (r["junior_category"] == "unknown") for r in rows
        ),
        "query_overrides": sum(r["query_note"] != "generic rule" for r in rows),
    }


def run(
    cases_csv: Path = CASES_CSV, mapping_csv: Path = MAPPING_CSV, force: bool = False
) -> dict[str, Any]:
    """Build mapping.csv. Idempotent: identical output is not rewritten; differing output is
    refused unless `force` (the committed file is the pre-registration)."""
    rows = build_mapping(read_csv(cases_csv))
    text = render_csv(rows, MAPPING_COLUMNS)
    status = "written"
    if mapping_csv.exists():
        if mapping_csv.read_text(encoding="utf-8") == text:
            status = "unchanged"
        elif not force:
            raise SystemExit(
                f"{mapping_csv} exists and differs from the generated mapping. It is the "
                "pre-registered table: change it only to fix a documented error, in its own "
                "commit. Re-run with --force to overwrite deliberately."
            )
        else:
            status = "overwritten (--force)"
    if status != "unchanged":
        mapping_csv.parent.mkdir(parents=True, exist_ok=True)
        with mapping_csv.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
    return {"status": status, "path": str(mapping_csv), **summarize(rows)}
