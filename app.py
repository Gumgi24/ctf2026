import os
import re
import hmac
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, session, redirect,
    url_for, g, flash, abort, make_response,
)
from dotenv import load_dotenv
import sqlite3

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.permanent_session_lifetime = timedelta(days=7)

DATABASE = os.environ.get("DATABASE_PATH", "ctf.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
MAX_WRONG_ATTEMPTS = 3


# ── Database ───────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── Admin Basic Auth ───────────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            resp = make_response("Unauthorized", 401)
            resp.headers["WWW-Authenticate"] = 'Basic realm="CTF Admin"'
            return resp
        try:
            user_ok = hmac.compare_digest(
                auth.username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8")
            )
            pass_ok = hmac.compare_digest(
                auth.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")
            )
        except Exception:
            user_ok = pass_ok = False

        if not (user_ok and pass_ok):
            resp = make_response("Unauthorized", 401)
            resp.headers["WWW-Authenticate"] = 'Basic realm="CTF Admin"'
            return resp

        return f(*args, **kwargs)
    return decorated


# ── Answer normalization ───────────────────────────────────────────────────────

def normalize(text, mode):
    """Normalize an answer according to the compare_mode of a challenge."""
    text = text.strip()
    if mode == "exact":
        return text
    text = text.lower()
    if mode == "icase":
        return text
    if mode == "icase_nospace":
        return re.sub(r"\s+", "", text)
    if mode == "icase_apostrophe":
        # Normalize curly apostrophes to straight apostrophe
        return text.replace("’", "'").replace("‘", "'")
    return text


def check_answer(submitted: str, answers: list, mode: str) -> bool:
    """Return True if submitted matches any accepted answer for this mode."""
    norm_sub = normalize(submitted, mode)
    for accepted in answers:
        if norm_sub == normalize(accepted, mode):
            return True
    # For apostrophe mode, also accept the string without any apostrophe
    if mode == "icase_apostrophe":
        sub_no_apos = norm_sub.replace("'", "")
        for accepted in answers:
            if sub_no_apos == normalize(accepted, mode).replace("'", ""):
                return True
    return False


# ── Query helpers ──────────────────────────────────────────────────────────────

def get_team(team_id):
    return get_db().execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()


def get_all_teams():
    return get_db().execute("SELECT * FROM teams ORDER BY id").fetchall()


def get_top_level_challenges():
    return get_db().execute(
        "SELECT * FROM challenges WHERE parent_id IS NULL ORDER BY order_num"
    ).fetchall()


def get_children(parent_id):
    return get_db().execute(
        "SELECT * FROM challenges WHERE parent_id = ? ORDER BY order_num",
        (parent_id,),
    ).fetchall()


def get_answers(challenge_id):
    rows = get_db().execute(
        "SELECT answer FROM challenge_answers WHERE challenge_id = ?", (challenge_id,)
    ).fetchall()
    return [r["answer"] for r in rows]


def get_team_status(team_id, challenge_id):
    """Return solved/locked/remaining info for a team+challenge pair."""
    db = get_db()

    override = db.execute(
        "SELECT is_solved, is_locked FROM flag_overrides WHERE team_id=? AND challenge_id=?",
        (team_id, challenge_id),
    ).fetchone()

    if override and override["is_solved"]:
        return {"solved": True, "locked": False, "wrong_count": 0, "remaining": 0}

    sub = db.execute(
        "SELECT id FROM submissions WHERE team_id=? AND challenge_id=?",
        (team_id, challenge_id),
    ).fetchone()
    if sub:
        return {"solved": True, "locked": False, "wrong_count": 0, "remaining": 0}

    attempt = db.execute(
        "SELECT wrong_count FROM attempts WHERE team_id=? AND challenge_id=?",
        (team_id, challenge_id),
    ).fetchone()
    wrong = attempt["wrong_count"] if attempt else 0

    admin_locked = bool(override and override["is_locked"])
    is_locked = admin_locked or (wrong >= MAX_WRONG_ATTEMPTS)

    return {
        "solved": False,
        "locked": is_locked,
        "wrong_count": wrong,
        "remaining": max(0, MAX_WRONG_ATTEMPTS - wrong) if not is_locked else 0,
    }


def get_team_score(team_id):
    """Return (total_points, solved_count, last_solve_timestamp)."""
    db = get_db()

    rows = db.execute(
        """
        SELECT COALESCE(SUM(c.points), 0) AS pts,
               COUNT(*) AS cnt,
               MAX(s.submitted_at) AS last_at
        FROM submissions s
        JOIN challenges c ON c.id = s.challenge_id
        WHERE s.team_id = ?
        """,
        (team_id,),
    ).fetchone()
    pts = rows["pts"] or 0
    cnt = rows["cnt"] or 0
    last_at = rows["last_at"]

    # Add points from admin force-solves not already in submissions
    ov = db.execute(
        """
        SELECT COALESCE(SUM(c.points), 0) AS pts, COUNT(*) AS cnt
        FROM flag_overrides fo
        JOIN challenges c ON c.id = fo.challenge_id
        WHERE fo.team_id = ? AND fo.is_solved = 1
          AND fo.challenge_id NOT IN (
              SELECT challenge_id FROM submissions WHERE team_id = ?
          )
        """,
        (team_id, team_id),
    ).fetchone()
    pts += ov["pts"] or 0
    cnt += ov["cnt"] or 0

    return pts, cnt, last_at


def get_scoreboard():
    teams = get_all_teams()
    result = []
    for team in teams:
        pts, cnt, last_at = get_team_score(team["id"])
        result.append(
            {
                "id": team["id"],
                "name": team["name"],
                "score": pts,
                "solved": cnt,
                "last_solve": last_at,
            }
        )
    result.sort(key=lambda x: (-x["score"], x["last_solve"] or "9999-99-99"))
    for i, r in enumerate(result):
        r["rank"] = i + 1
    return result


def enrich_challenge(ch, team_id, admin=False):
    """Attach status and children to a challenge dict."""
    ch = dict(ch)
    if ch["is_parent"]:
        ch["status"] = None
        children = get_children(ch["id"])
        ch["children"] = [enrich_challenge(dict(c), team_id, admin) for c in children]
    else:
        ch["status"] = get_team_status(team_id, ch["id"])
        ch["children"] = []
        if admin:
            attempt = get_db().execute(
                "SELECT wrong_count FROM attempts WHERE team_id=? AND challenge_id=?",
                (team_id, ch["id"]),
            ).fetchone()
            ch["wrong_count"] = attempt["wrong_count"] if attempt else 0
    return ch


# ── Jinja2 filter ──────────────────────────────────────────────────────────────

@app.template_filter("fmt_ts")
def fmt_ts(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).split(".")[0])
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


# ── Public routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/teams")
def team_select():
    teams = get_all_teams()
    current_team_id = session.get("team_id")
    return render_template("team_select.html", teams=teams, current_team_id=current_team_id)


@app.route("/teams/<int:team_id>/join", methods=["POST"])
def join_team(team_id):
    team = get_team(team_id)
    if not team:
        abort(404)
    session["team_id"] = team_id
    session.permanent = True
    flash(f'Vous avez rejoint {team["name"]}.', "success")
    return redirect(url_for("challenges"))


@app.route("/challenges")
def challenges():
    team_id = session.get("team_id")
    if not team_id:
        flash("Veuillez d'abord sélectionner votre équipe.", "warning")
        return redirect(url_for("team_select"))

    team = get_team(team_id)
    if not team:
        session.pop("team_id", None)
        flash("Équipe introuvable. Veuillez en sélectionner une autre.", "danger")
        return redirect(url_for("team_select"))

    top = get_top_level_challenges()
    challenge_tree = [enrich_challenge(ch, team_id) for ch in top]
    score, solved_count, _ = get_team_score(team_id)

    return render_template(
        "challenges.html",
        team=team,
        challenges=challenge_tree,
        score=score,
        solved_count=solved_count,
    )


@app.route("/challenges/<int:challenge_id>/submit", methods=["POST"])
def submit_flag(challenge_id):
    team_id = session.get("team_id")
    if not team_id:
        flash("Veuillez d'abord sélectionner votre équipe.", "warning")
        return redirect(url_for("team_select"))

    db = get_db()
    ch = db.execute("SELECT * FROM challenges WHERE id = ?", (challenge_id,)).fetchone()
    if not ch or ch["is_parent"]:
        abort(404)

    status = get_team_status(team_id, challenge_id)

    if status["solved"]:
        flash(f'"{ch["title"]}" est déjà résolu.', "info")
        return redirect(url_for("challenges"))

    if status["locked"]:
        flash(f'"{ch["title"]}" est verrouillé après trop de mauvaises réponses.', "danger")
        return redirect(url_for("challenges"))

    submitted = request.form.get("answer", "").strip()
    if not submitted:
        flash("Veuillez entrer une réponse.", "warning")
        return redirect(url_for("challenges"))

    answers = get_answers(challenge_id)
    correct = check_answer(submitted, answers, ch["compare_mode"])

    if correct:
        try:
            db.execute(
                "INSERT INTO submissions (team_id, challenge_id) VALUES (?, ?)",
                (team_id, challenge_id),
            )
            db.commit()
            flash(f'✓ Correct ! {ch["points"]} point(s) pour "{ch["title"]}".', "success")
        except sqlite3.IntegrityError:
            flash(f'"{ch["title"]}" est déjà résolu.', "info")
    else:
        db.execute(
            """
            INSERT INTO attempts (team_id, challenge_id, wrong_count) VALUES (?, ?, 1)
            ON CONFLICT(team_id, challenge_id) DO UPDATE SET wrong_count = wrong_count + 1
            """,
            (team_id, challenge_id),
        )
        db.commit()
        new_status = get_team_status(team_id, challenge_id)
        if new_status["locked"]:
            flash(f'Réponse incorrecte. "{ch["title"]}" est maintenant verrouillé.', "danger")
        else:
            r = new_status["remaining"]
            flash(
                f'Réponse incorrecte. Il vous reste {r} essai(s) pour "{ch["title"]}".',
                "warning",
            )

    return redirect(url_for("challenges"))


@app.route("/scoreboard")
def scoreboard():
    board = get_scoreboard()
    return render_template("scoreboard.html", board=board)


# ── Admin routes ───────────────────────────────────────────────────────────────

@app.route("/admin")
@require_admin
def admin_dashboard():
    teams = get_all_teams()
    scores = []
    for team in teams:
        pts, cnt, last_at = get_team_score(team["id"])
        scores.append(
            {
                "id": team["id"],
                "name": team["name"],
                "score": pts,
                "solved": cnt,
                "last_solve": last_at,
            }
        )
    return render_template("admin_dashboard.html", scores=scores)


@app.route("/admin/team/<int:team_id>")
@require_admin
def admin_team(team_id):
    team = get_team(team_id)
    if not team:
        abort(404)

    top = get_top_level_challenges()
    challenge_tree = [enrich_challenge(ch, team_id, admin=True) for ch in top]
    score, solved_count, _ = get_team_score(team_id)

    return render_template(
        "admin_team.html",
        team=team,
        challenges=challenge_tree,
        score=score,
        solved_count=solved_count,
    )


@app.route("/admin/team/<int:team_id>/reset", methods=["POST"])
@require_admin
def admin_reset_team(team_id):
    team = get_team(team_id)
    if not team:
        abort(404)
    db = get_db()
    db.execute("DELETE FROM submissions WHERE team_id = ?", (team_id,))
    db.execute("DELETE FROM attempts WHERE team_id = ?", (team_id,))
    db.execute("DELETE FROM flag_overrides WHERE team_id = ?", (team_id,))
    db.commit()
    flash(f'Équipe "{team["name"]}" réinitialisée.', "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reset-all", methods=["POST"])
@require_admin
def admin_reset_all():
    db = get_db()
    db.execute("DELETE FROM submissions")
    db.execute("DELETE FROM attempts")
    db.execute("DELETE FROM flag_overrides")
    db.commit()
    flash("Compétition entièrement réinitialisée.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/team/<int:team_id>/rename", methods=["POST"])
@require_admin
def admin_rename_team(team_id):
    team = get_team(team_id)
    if not team:
        abort(404)
    new_name = request.form.get("name", "").strip()
    if not new_name:
        flash("Nom invalide.", "danger")
        return redirect(url_for("admin_team", team_id=team_id))
    get_db().execute("UPDATE teams SET name = ? WHERE id = ?", (new_name, team_id))
    get_db().commit()
    flash(f'Équipe renommée en "{new_name}".', "success")
    return redirect(url_for("admin_team", team_id=team_id))


@app.route("/admin/challenge/<int:team_id>/<int:challenge_id>/solve", methods=["POST"])
@require_admin
def admin_force_solve(team_id, challenge_id):
    db = get_db()
    db.execute(
        """
        INSERT INTO flag_overrides (team_id, challenge_id, is_solved, is_locked)
        VALUES (?, ?, 1, 0)
        ON CONFLICT(team_id, challenge_id) DO UPDATE SET is_solved=1, is_locked=0
        """,
        (team_id, challenge_id),
    )
    db.commit()
    flash("Flag marqué comme résolu.", "success")
    return redirect(url_for("admin_team", team_id=team_id))


@app.route("/admin/challenge/<int:team_id>/<int:challenge_id>/lock", methods=["POST"])
@require_admin
def admin_lock_flag(team_id, challenge_id):
    db = get_db()
    db.execute(
        """
        INSERT INTO flag_overrides (team_id, challenge_id, is_solved, is_locked)
        VALUES (?, ?, 0, 1)
        ON CONFLICT(team_id, challenge_id) DO UPDATE SET is_locked=1
        """,
        (team_id, challenge_id),
    )
    db.commit()
    flash("Flag verrouillé.", "warning")
    return redirect(url_for("admin_team", team_id=team_id))


@app.route("/admin/challenge/<int:team_id>/<int:challenge_id>/unlock", methods=["POST"])
@require_admin
def admin_unlock_flag(team_id, challenge_id):
    db = get_db()
    db.execute(
        """
        INSERT INTO flag_overrides (team_id, challenge_id, is_solved, is_locked)
        VALUES (?, ?, 0, 0)
        ON CONFLICT(team_id, challenge_id) DO UPDATE SET is_locked=0
        """,
        (team_id, challenge_id),
    )
    # Reset wrong attempt counter so the team can try again
    db.execute(
        "DELETE FROM attempts WHERE team_id=? AND challenge_id=?",
        (team_id, challenge_id),
    )
    db.commit()
    flash("Flag déverrouillé et compteur d'essais réinitialisé.", "success")
    return redirect(url_for("admin_team", team_id=team_id))


# ── Error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", 8000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
