"""Flask web application for the CityCare FOL FAQ system.

The web layer deliberately delegates every hospital answer to the existing
query processor and pyDatalog inference engine.  It does not contain a second
knowledge base or a keyword-answer fallback.
"""
from collections import Counter, defaultdict
from functools import wraps
import os
import secrets
import time

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

import auth
import inference_engine as engine
import knowledge_base as kb
import reasoning_trace

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_USERNAME = os.environ.get("CITYCARE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("CITYCARE_ADMIN_PASSWORD", "admin123")
LOGIN_ATTEMPTS = {}
LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 5

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("CITYCARE_SECRET_KEY", secrets.token_urlsafe(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("CITYCARE_SECURE_COOKIES") == "1",
)
auth.init_db(ADMIN_USERNAME, ADMIN_PASSWORD)


def label(value):
    return reasoning_trace.pretty(value)


def ensure_engine():
    """Load facts for CLI/test imports and recover after a normal restart."""
    try:
        return engine.load_knowledge_base()
    except kb.KnowledgeBaseError:
        return 0


def facts():
    return kb.load_facts()


def value_map(records):
    out = defaultdict(list)
    for item in records:
        out[item["predicate"]].append(item["args"])
    return out


def hospital_data():
    """Build every directory/card from stored facts or rule-derived queries."""
    stored = facts()
    groups = value_map(stored)
    specialities = {args[0]: args[1] for args in groups["specializes"] if len(args) == 2}
    availability = {args[0]: args[1] for args in groups["doctor_availability"] if len(args) == 2}
    doctors = [{"id": d[0], "name": "Dr. " + label(d[0]),
                "specialty": label(specialities.get(d[0], "")) if specialities.get(d[0]) else None,
                "availability": availability.get(d[0])}
               for d in groups["doctor"] if d]
    by_department = defaultdict(list)
    for doctor in doctors:
        if doctor["specialty"]:
            by_department[doctor["specialty"]].append(doctor["name"])
    departments = [{"name": label(row[0]), "id": row[0],
                    "doctors": by_department.get(label(row[0]), [])}
                   for row in groups["department"] if row]
    services = [{"name": label(row[0]), "id": row[0], "kind": "Service"}
                for row in groups["service"] if row]
    facilities = [{"name": label(row[0]), "id": row[0], "kind": "Facility"}
                  for row in groups["facility"] if row]
    timing = {row["predicate"]: row["args"][1] for row in stored
              if len(row["args"]) == 2 and row["predicate"] in kb.TEXT_VALUE_PREDICATES}
    return {"facts": stored, "groups": groups, "doctors": doctors, "departments": departments,
            "services": services, "facilities": facilities, "timing": timing}


def dashboard_metrics():
    data = hospital_data()
    counter = Counter(f["predicate"] for f in data["facts"])
    return {"facts": len(data["facts"]), "doctors": len(data["doctors"]),
            "departments": len(data["departments"]), "services": len(data["services"]),
            "facilities": len(data["facilities"]), "rules": len(engine.RULE_INFO),
            "predicate_counts": dict(sorted(counter.items())),
            "specialties": dict(sorted(Counter(d["specialty"] or "Unrecorded" for d in data["doctors"]).items())),
            "directory": {"Services": len(data["services"]), "Facilities": len(data["facilities"]),
                          "Departments": len(data["departments"])}}


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]


@app.context_processor
def common_context():
    role = session.get("role")
    return {"csrf_token": csrf_token(), "is_admin": role == "admin", "current_role": role,
            "username": session.get("username"), "hospital": kb.HOSPITAL_NAME}


def require_roles(*allowed_roles):
    """Authorize every protected route/API from the role held in the session."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="You are not authorized to access this resource."), 403 if session.get("role") else 401
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def require_admin(view):
    """Compatibility name for the administrator-only knowledge-base operations."""
    return require_roles("admin")(view)


def require_csrf():
    token = (request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
             or (request.get_json(silent=True) or {}).get("csrf_token"))
    if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
        abort(400, "Invalid CSRF token.")


@app.before_request
def initialise():
    if request.endpoint not in {"static", None}:
        ensure_engine()


@app.errorhandler(400)
def bad_request(error):
    if request.path.startswith("/api/"):
        return jsonify(error=getattr(error, "description", "Invalid request.")), 400
    return render_template("error.html", title="Invalid request", message="Please check the submitted information."), 400


@app.route("/")
def landing():
    return render_template("landing.html", title="CityCare Hospital")


@app.route("/dashboard")
@require_roles("admin")
def dashboard():
    data = hospital_data()
    return render_template("dashboard.html", title="Dashboard", metrics=dashboard_metrics(), data=data, role=session.get("role"))


@app.route("/roles")
def roles():
    return redirect(url_for("login"))


@app.route("/faq")
def faq():
    suggestions = ["Which doctor works in orthopedics?", "What are the OPD timings?",
                   "What services does the hospital provide?", "Does the hospital have an MRI?",
                   "What is the availability of Dr. Kumar?"]
    return render_template("faq.html", title="FAQ Assistant", suggestions=suggestions)


@app.route("/doctors")
def doctors():
    return render_template("directory.html", title="Doctors", item_type="doctor", items=hospital_data()["doctors"])


@app.route("/departments")
def departments():
    return render_template("directory.html", title="Departments", item_type="department", items=hospital_data()["departments"])


@app.route("/services")
def services():
    data = hospital_data()
    return render_template("directory.html", title="Services & Facilities", item_type="resource",
                           items=data["services"] + data["facilities"])


@app.route("/knowledge-base")
@require_admin
def knowledge_base_page():
    return render_template("knowledge_base.html", title="Knowledge Base", facts=facts(),
                           predicates=sorted({f["predicate"] for f in facts()}))


@app.route("/reasoning")
def reasoning():
    return render_template("reasoning.html", title="FOL Reasoning", rules=engine.RULE_INFO, facts=facts()[:8])


@app.route("/analytics")
def analytics():
    return render_template("analytics.html", title="Analytics", metrics=dashboard_metrics())


def _safe_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") else None


def _login_throttled(identity):
    attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(identity, []) if stamp > time.time() - LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[identity] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


@app.route("/login", methods=["GET", "POST"])
@app.route("/admin", methods=["GET", "POST"])
def login():
    if session.get("role") and request.method == "GET":
        return redirect(url_for("dashboard"))
    intended_role = "admin"
    message = None
    if request.method == "POST":
        require_csrf()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        identity = request.remote_addr or "unknown"
        if _login_throttled(identity):
            message = "Too many sign-in attempts. Please try again later."
        else:
            account = auth.authenticate(username, password)
            if not account or (intended_role and account["role"] != intended_role):
                LOGIN_ATTEMPTS.setdefault(identity, []).append(time.time())
                message = "Unable to sign in with those details."
            else:
                LOGIN_ATTEMPTS.pop(identity, None)
                session.clear()  # rotate the session and CSRF token after authentication
                session.update(user_id=account["id"], username=account["username"], role=account["role"],
                               admin=account["role"] == "admin")  # legacy key retained for integrations
                csrf_token()
                return redirect(_safe_next(request.form.get("next")) or url_for("dashboard"))
    return render_template("login.html", title="Sign In", message=message, intended_role=intended_role,
                           next_url=_safe_next(request.values.get("next")))


@app.route("/admin/workspace")
@require_admin
def admin():
    return render_template("admin.html", title="Admin Workspace", users=auth.list_users())


@app.post("/logout")
@require_roles("admin")
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("landing"))


@app.post("/api/admin/users")
@require_admin
def api_create_user():
    require_csrf()
    body = request.get_json(silent=True) or {}
    try:
        auth.create_user(body.get("username"), body.get("password"), body.get("role"))
        return jsonify(message="Account created."), 201
    except ValueError as error:
        return jsonify(error=str(error)), 422


@app.route("/about")
def about():
    return render_template("about.html", title="About the Project")


@app.post("/api/faq")
def api_faq():
    body = request.get_json(silent=True) or {}
    question = body.get("question", "")
    if not isinstance(question, str) or len(question.strip()) > 1000:
        return jsonify(error="Question must be between 1 and 1000 characters."), 400
    result = reasoning_trace.answer_question(question.strip())
    return jsonify(result)


@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(dashboard_metrics())


@app.get("/api/directory")
def api_directory():
    return jsonify(hospital_data())


def refreshed_facts(updated):
    validated = kb.validate_facts(updated, engine.derived_predicates())
    kb.save_facts(validated, engine.derived_predicates())
    engine.load_knowledge_base()
    return validated


@app.get("/api/facts")
@require_admin
def api_facts():
    return jsonify(facts=facts(), count=len(facts()), predicates=sorted({f["predicate"] for f in facts()}))


@app.post("/api/facts")
@require_admin
def api_add_fact():
    require_csrf()
    body = request.get_json(silent=True) or {}
    try:
        updated = kb.add_fact(facts(), body.get("predicate"), body.get("args", []), engine.derived_predicates())
        refreshed_facts(updated)
        return jsonify(message="Fact added and inference engine reloaded.", facts=updated), 201
    except (kb.FactError, kb.KnowledgeBaseError) as error:
        return jsonify(error=str(error)), 422


@app.put("/api/facts/<int:index>")
@require_admin
def api_update_fact(index):
    require_csrf()
    body = request.get_json(silent=True) or {}
    try:
        updated = kb.update_fact(facts(), index, body.get("predicate"), body.get("args", []), engine.derived_predicates())
        refreshed_facts(updated)
        return jsonify(message="Fact updated and inference engine reloaded.", facts=updated)
    except (kb.FactError, kb.KnowledgeBaseError) as error:
        return jsonify(error=str(error)), 422


@app.delete("/api/facts/<int:index>")
@require_admin
def api_delete_fact(index):
    require_csrf()
    try:
        updated = kb.delete_fact(facts(), index)
        refreshed_facts(updated)
        return jsonify(message="Fact deleted and inference engine reloaded.", facts=updated)
    except (kb.FactError, kb.KnowledgeBaseError) as error:
        return jsonify(error=str(error)), 422


@app.post("/api/admin/query")
@require_admin
def api_admin_query():
    require_csrf()
    text = (request.get_json(silent=True) or {}).get("query", "")
    try:
        predicate, args = engine.parse_logical_query(text)
        return jsonify(query=engine.format_query(predicate, args), answers=engine.query(predicate, args))
    except engine.InferenceError as error:
        return jsonify(error=str(error)), 422


@app.post("/api/admin/validate")
@require_admin
def api_validate():
    require_csrf()
    try:
        checked = kb.validate_facts(facts(), engine.derived_predicates())
        return jsonify(message="Knowledge base is valid.", count=len(checked))
    except kb.KnowledgeBaseError as error:
        return jsonify(error=str(error)), 422


@app.post("/api/admin/reload")
@require_admin
def api_reload():
    require_csrf()
    try:
        count = engine.load_knowledge_base()
        return jsonify(message="Knowledge base reloaded.", count=count)
    except kb.KnowledgeBaseError as error:
        return jsonify(error=str(error)), 422


@app.post("/api/admin/backup")
@require_admin
def api_backup():
    require_csrf()
    try:
        path = kb.backup_kb()
        return jsonify(message="Backup created.", filename=os.path.basename(path))
    except kb.KnowledgeBaseError as error:
        return jsonify(error=str(error)), 422


if __name__ == "__main__":
    ensure_engine()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
