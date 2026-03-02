import requests
import pandas as pd
import sqlite3
import json
import time
from tqdm import tqdm

OPENALEX_AUTHOR_URL = "https://api.openalex.org/authors"
HEADERS = {
    "User-Agent": "UniversityEnrichmentScript (mailto:your_email@example.com)"
}

RATE_LIMIT_DELAY = 0.25  # Safe limit (~4 req/sec)
BATCH_SIZE = 100
CACHE_DB = "openalex_cache.db"


# ------------------------------------------------
# CACHE SETUP (SQLite)
# ------------------------------------------------
def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS author_cache (
            name TEXT PRIMARY KEY,
            response TEXT
        )
    """)
    conn.commit()
    return conn


def get_cached_author(conn, name):
    c = conn.cursor()
    c.execute("SELECT response FROM author_cache WHERE name = ?", (name,))
    row = c.fetchone()
    if row:
        return json.loads(row[0])
    return None


def save_author_to_cache(conn, name, response_json):
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO author_cache (name, response) VALUES (?, ?)",
        (name, json.dumps(response_json))
    )
    conn.commit()


# ------------------------------------------------
# OPENALEX SEARCH
# ------------------------------------------------
def search_author(name, conn):
    cached = get_cached_author(conn, name)
    if cached is not None:
        return cached if cached else None

    params = {
        "search": name,
        "per-page": 1
    }

    r = requests.get(OPENALEX_AUTHOR_URL, params=params, headers=HEADERS)

    if r.status_code != 200:
        save_author_to_cache(conn, name, {})
        time.sleep(RATE_LIMIT_DELAY)
        return None

    data = r.json()

    if data["meta"]["count"] == 0:
        save_author_to_cache(conn, name, {})
        time.sleep(RATE_LIMIT_DELAY)
        return None

    best_match = data["results"][0]

    save_author_to_cache(conn, name, best_match)
    time.sleep(RATE_LIMIT_DELAY)

    return best_match


# ------------------------------------------------
# EXTRACT AFFILIATIONS
# ------------------------------------------------
def extract_affiliations(author_record):
    affiliations = []

    if not author_record:
        return affiliations

    institutions = author_record.get("last_known_institutions") or []

    for inst in institutions:
        affiliations.append({
            "University_ID": inst.get("id"),
            "Role": "Researcher / Faculty",
            "Start Date": None,
            "End Date": None,
            "Source": "OpenAlex",
            "Notes": f"author_id={author_record.get('id')}"
        })

    return affiliations


# ------------------------------------------------
# MAIN PIPELINE
# ------------------------------------------------
def enrich_people(input_file, output_file):

    conn = init_cache()

    people = pd.read_csv(input_file)

    # Deduplicate names to reduce API calls
    unique_names = people["Name"].dropna().unique()

    print(f"Unique names to query: {len(unique_names)}")

    name_to_author = {}

    # -------- BATCH PROCESSING --------
    for i in tqdm(range(0, len(unique_names), BATCH_SIZE)):
        batch = unique_names[i:i+BATCH_SIZE]

        for name in batch:
            author = search_author(name, conn)
            name_to_author[name] = author

        print(f"Processed batch {i//BATCH_SIZE + 1}")

    # -------- BUILD OUTPUT TABLE --------
    results = []

    for _, row in people.iterrows():
        person_id = row["ID"]
        name = row["Name"]

        author = name_to_author.get(name)
        affiliations = extract_affiliations(author)

        for aff in affiliations:
            results.append({
                "Person_ID": person_id,
                "University_ID": aff["University_ID"],
                "Role": aff["Role"],
                "Start Date": aff["Start Date"],
                "End Date": aff["End Date"],
                "Source": aff["Source"],
                "Notes": aff["Notes"]
            })

    df_out = pd.DataFrame(results)
    df_out.to_csv(output_file, index=False)

    print("Done. Output saved to:", output_file)


# ------------------------------------------------
# RUN
# ------------------------------------------------
if __name__ == "__main__":
    enrich_people(
        input_file="people.csv",
        output_file="person_university_affiliations.csv"
    )
