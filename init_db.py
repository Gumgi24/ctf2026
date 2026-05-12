"""
Initialise la base de données SQLite : crée les tables et insère
les équipes + challenges avec leurs réponses.

Usage :
    python init_db.py           # initialise si la DB est vide
    python init_db.py --force   # réinitialise complètement
"""

import os
import sys
import sqlite3

from dotenv import load_dotenv

load_dotenv()

DATABASE = os.environ.get("DATABASE_PATH", "ctf.db")

# ── Schéma ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS challenges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    description   TEXT,
    points        INTEGER NOT NULL DEFAULT 0,
    parent_id     INTEGER REFERENCES challenges(id),
    image         TEXT,
    expected_form TEXT,
    order_num     REAL NOT NULL DEFAULT 0,
    compare_mode  TEXT NOT NULL DEFAULT 'exact',
    is_parent     INTEGER NOT NULL DEFAULT 0,
    category      TEXT NOT NULL DEFAULT 'main'
);

CREATE TABLE IF NOT EXISTS challenge_answers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    answer       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id      INTEGER NOT NULL REFERENCES teams(id),
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_id, challenge_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id      INTEGER NOT NULL REFERENCES teams(id),
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    wrong_count  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(team_id, challenge_id)
);

CREATE TABLE IF NOT EXISTS flag_overrides (
    team_id      INTEGER NOT NULL REFERENCES teams(id),
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    is_locked    INTEGER NOT NULL DEFAULT 0,
    is_solved    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (team_id, challenge_id)
);
"""

# ── Données ───────────────────────────────────────────────────────────────────

TEAMS = [f"Equipe {i}" for i in range(1, 15)]

# compare_mode values:
#   exact           — correspondance exacte après strip
#   icase           — insensible à la casse après strip
#   icase_nospace   — insensible à la casse, espaces internes supprimés
#   icase_apostrophe — insensible à la casse, apostrophes normalisées
#
# parent_id peut être un slug (str) — résolu en second passage.

CHALLENGES = [
    # ── Challenge extra préliminaire ──────────────────────────────────────────
    {
        "slug": "extra-stranded-deep",
        "title": "Stranded Deep",
        "description": "Sur quelle île cette photo a-t-elle été prise ?",
        "points": 3,
        "parent_id": None,
        "image": "island.png",
        "expected_form": "Nom de l'île, sans accent obligatoire",
        "order_num": 0,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "extra",
        "answers": ["Kharg", "Khark"],
    },
    # ── Flag 1 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-1-imo",
        "title": "Flag 1 — Identifiant du navire",
        "description": (
            "Retrouvez l'identifiant permanent du navire visible sur la photo "
            "dans les bases maritimes."
        ),
        "points": 1,
        "parent_id": None,
        "image": "ship.png",
        "expected_form": "7 chiffres",
        "order_num": 1,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["9255933"],
    },
    # ── Flag 2 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-2-annonce",
        "title": "Flag 2 — L'annonce commerciale",
        "description": (
            "Plus tard dans sa vie, ce navire apparaît dans une annonce de vente "
            "ou d'affrètement longue durée. "
            "À quelle date cette annonce a-t-elle été publiée ?"
        ),
        "points": 2,
        "parent_id": None,
        "image": None,
        "expected_form": "AAAAMMJJ",
        "order_num": 2,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["20240902"],
    },
    # ── Flag 3 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-3-uen",
        "title": "Flag 3 — La société du courtier",
        "description": (
            "La signature de l'annonce mène à une société singapourienne liée au courtier. "
            "Quel est son Universal Entity Number ?"
        ),
        "points": 3,
        "parent_id": None,
        "image": None,
        "expected_form": "UEN exact, en majuscules",
        "order_num": 3,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "main",
        "answers": ["T19LL1366C"],
    },
    # ── Flag 4 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-4-certificat",
        "title": "Flag 4 — Le certificat fantôme",
        "description": (
            "Après cette annonce, le navire réapparaît dans un article consacré à une "
            "immatriculation douteuse. Retrouvez le certificat montré dans l'article. "
            "Quel numéro de certificat figure en haut à droite ?"
        ),
        "points": 2,
        "parent_id": None,
        "image": None,
        "expected_form": "PR suivi de 5 chiffres, sans espace",
        "order_num": 4,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "main",
        "answers": ["PR30092"],
    },
    # ── Flag 5 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-5-faute",
        "title": "Flag 5 — La faute d'orthographe",
        "description": (
            "Sur ce même certificat, une phrase administrative contient une faute "
            "d'orthographe visible. Quel est le mot fautif ?"
        ),
        "points": 1,
        "parent_id": None,
        "image": None,
        "expected_form": "Mot unique, en majuscules",
        "order_num": 5,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "main",
        "answers": ["ACEPTED"],
    },
    # ── Flag 6 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-6-abandon-1",
        "title": "Flag 6 — Abandon des gens de mer, premier dossier",
        "description": (
            "Un premier dossier d'abandon des gens de mer mentionne les conditions de vie "
            "à bord. Relevez précisément l'expression entre parenthèses décrivant une infestation."
        ),
        "points": 2,
        "parent_id": None,
        "image": None,
        "expected_form": "***/********** ***********",
        "order_num": 6,
        "compare_mode": "icase_apostrophe",
        "is_parent": 0,
        "category": "main",
        "answers": ["bug/cockroaches' infestation", "bug/cockroaches infestation"],
    },
    # ── Flag 7 ────────────────────────────────────────────────────────────────
    {
        "slug": "flag-7-abandon-2",
        "title": "Flag 7 — Abandon des gens de mer, second dossier",
        "description": (
            "Un autre dossier d'abandon des gens de mer concerne le même navire. "
            "À quelle date le statut de paiement indique-t-il que les salaires impayés "
            "ont finalement été réglés ?"
        ),
        "points": 2,
        "parent_id": None,
        "image": None,
        "expected_form": "AAAAMMJJ",
        "order_num": 7,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["20251008"],
    },
    # ── Flag 8 (parent) ───────────────────────────────────────────────────────
    {
        "slug": "flag-8-piraterie",
        "title": "Flag 8 — Rapport de piraterie",
        "description": (
            "Le navire apparaît dans un rapport mensuel de l'OMI sur la piraterie, "
            "sous un autre nom. Retrouvez l'entrée correspondant au même IMO, "
            "puis remplissez les champs séparément."
        ),
        "points": 0,
        "parent_id": None,
        "image": None,
        "expected_form": None,
        "order_num": 8,
        "compare_mode": "exact",
        "is_parent": 1,
        "category": "main",
        "answers": [],
    },
    # ── Flag 8A ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-8a-heure",
        "title": "Flag 8A — Heure",
        "description": "Quelle heure est indiquée pour l'événement ?",
        "points": 1,
        "parent_id": "flag-8-piraterie",
        "image": None,
        "expected_form": "HHMMUTC",
        "order_num": 8.1,
        "compare_mode": "icase_nospace",
        "is_parent": 0,
        "category": "main",
        "answers": ["0535UTC"],
    },
    # ── Flag 8B ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-8b-personnes",
        "title": "Flag 8B — Personnes non autorisées",
        "description": "Combien de personnes non autorisées sont mentionnées ?",
        "points": 1,
        "parent_id": "flag-8-piraterie",
        "image": None,
        "expected_form": "Nombre entier",
        "order_num": 8.2,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["6"],
    },
    # ── Flag 8C ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-8c-armes",
        "title": "Flag 8C — Personnes armées",
        "description": "Combien d'entre elles sont décrites comme armées ?",
        "points": 1,
        "parent_id": "flag-8-piraterie",
        "image": None,
        "expected_form": "Nombre entier",
        "order_num": 8.3,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["1"],
    },
    # ── Flag 8D ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-8d-position",
        "title": "Flag 8D — Position",
        "description": (
            "Quelle position géographique est donnée pour l'incident ? "
            "Donnez la longitude puis la latitude."
        ),
        "points": 2,
        "parent_id": "flag-8-piraterie",
        "image": None,
        "expected_form": (
            "LONGITUDE_LATITUDE, sans symbole de degré, sans espace, "
            "sans point, sans apostrophe"
        ),
        "order_num": 8.4,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "main",
        "answers": ["1040017E_011418N"],
    },
    # ── Flag 9 (parent) ───────────────────────────────────────────────────────
    {
        "slug": "flag-9-saisie",
        "title": "Flag 9 — Saisie récente",
        "description": (
            "La semaine dernière, le même navire a été saisi. "
            "Retrouvez l'incident, puis remplissez les deux champs séparément."
        ),
        "points": 0,
        "parent_id": None,
        "image": None,
        "expected_form": None,
        "order_num": 9,
        "compare_mode": "exact",
        "is_parent": 1,
        "category": "main",
        "answers": [],
    },
    # ── Flag 9A ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-9a-date",
        "title": "Flag 9A — Date",
        "description": "À quelle date la saisie a-t-elle eu lieu ?",
        "points": 1,
        "parent_id": "flag-9-saisie",
        "image": None,
        "expected_form": "AAAAMMJJ",
        "order_num": 9.1,
        "compare_mode": "exact",
        "is_parent": 0,
        "category": "main",
        "answers": ["20260508"],
    },
    # ── Flag 9B ───────────────────────────────────────────────────────────────
    {
        "slug": "flag-9b-pays",
        "title": "Flag 9B — Pays",
        "description": "Quel pays a saisi le navire ?",
        "points": 1,
        "parent_id": "flag-9-saisie",
        "image": None,
        "expected_form": "Nom du pays en majuscules, sans accent",
        "order_num": 9.2,
        "compare_mode": "icase",
        "is_parent": 0,
        "category": "main",
        "answers": ["IRAN"],
    },
]


# ── Initialisation ────────────────────────────────────────────────────────────

def init_db(force=False):
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    # Vérifie si la DB contient déjà des données
    already = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    if already > 0 and not force:
        print("La base est déjà initialisée. Utilisez --force pour réinitialiser.")
        conn.close()
        return

    if force:
        conn.executescript(
            """
            DELETE FROM flag_overrides;
            DELETE FROM attempts;
            DELETE FROM submissions;
            DELETE FROM challenge_answers;
            DELETE FROM challenges;
            DELETE FROM teams;
            """
        )
        print("Base réinitialisée.")

    # Équipes
    for name in TEAMS:
        conn.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", (name,))

    # Premier passage : challenges sans parent_id string
    slug_to_id: dict[str, int] = {}
    for ch in CHALLENGES:
        if ch["parent_id"] is None:
            cur = conn.execute(
                """
                INSERT INTO challenges
                    (slug, title, description, points, parent_id, image,
                     expected_form, order_num, compare_mode, is_parent, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ch["slug"], ch["title"], ch["description"], ch["points"],
                    None, ch["image"], ch["expected_form"],
                    ch["order_num"], ch["compare_mode"], ch["is_parent"], ch["category"],
                ),
            )
            slug_to_id[ch["slug"]] = cur.lastrowid

    # Second passage : challenges avec parent_id = slug
    for ch in CHALLENGES:
        if isinstance(ch["parent_id"], str):
            parent_db_id = slug_to_id[ch["parent_id"]]
            cur = conn.execute(
                """
                INSERT INTO challenges
                    (slug, title, description, points, parent_id, image,
                     expected_form, order_num, compare_mode, is_parent, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ch["slug"], ch["title"], ch["description"], ch["points"],
                    parent_db_id, ch["image"], ch["expected_form"],
                    ch["order_num"], ch["compare_mode"], ch["is_parent"], ch["category"],
                ),
            )
            slug_to_id[ch["slug"]] = cur.lastrowid

    # Réponses (stockées côté serveur uniquement, jamais exposées en frontend)
    for ch in CHALLENGES:
        ch_id = slug_to_id[ch["slug"]]
        for answer in ch["answers"]:
            conn.execute(
                "INSERT INTO challenge_answers (challenge_id, answer) VALUES (?, ?)",
                (ch_id, answer),
            )

    conn.commit()
    conn.close()

    total_pts = sum(ch["points"] for ch in CHALLENGES)
    print(f"Base initialisée : {len(TEAMS)} équipes, {len(CHALLENGES)} challenges, {total_pts} pts max.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    init_db(force=force)
