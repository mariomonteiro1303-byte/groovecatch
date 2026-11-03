"""Anúncios próprios/afiliados: cadastro SQLite, sem scripts de terceiros."""
import os, sqlite3, hmac, secrets, time
from pathlib import Path
from urllib.parse import urlsplit
from flask import Blueprint, current_app, request, render_template, redirect, url_for, session, abort, jsonify

bp = Blueprint("advertising", __name__)
SLOTS = ("topo", "conteudo", "rodape")
KINDS = ("afiliado", "patrocinador", "rede")

def connection():
    path = Path(current_app.config["ADS_DB_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, image_url TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, slot TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, impressions INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL)")
    con.commit()
    return con

def valid_https(url):
    try:
        p = urlsplit(url)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password and not any(c.isspace() for c in url)
    except ValueError:
        return False

def admin_enabled():
    return bool(os.environ.get("GROOVECATCH_ADS_ADMIN_PASSWORD"))

def is_admin():
    return admin_enabled() and session.get("ads_admin") is True

def csrf_token():
    if "ads_csrf" not in session:
        session["ads_csrf"] = secrets.token_urlsafe(32)
    return session["ads_csrf"]

def require_csrf():
    if not hmac.compare_digest(request.form.get("csrf", ""), session.get("ads_csrf", "")):
        abort(403)

def ad_for_slot(slot):
    if slot not in SLOTS:
        return None
    with connection() as con:
        rows = con.execute("SELECT id,title,description,image_url,kind,slot FROM ads WHERE active=1 AND slot=? ORDER BY id", (slot,)).fetchall()
        if not rows:
            return None
        # Rodízio por tempo; uma única peça por espaço por renderização.
        ad = dict(rows[(int(time.time()) // 60) % len(rows)])
        con.execute("UPDATE ads SET impressions=impressions+1 WHERE id=?", (ad["id"],))
        return ad

@bp.get('/ads/out/<int:ad_id>')
def outbound(ad_id):
    with connection() as con:
        row = con.execute("SELECT url,active FROM ads WHERE id=?", (ad_id,)).fetchone()
        if not row or not row['active'] or not valid_https(row['url']):
            abort(404)
        con.execute("UPDATE ads SET clicks=clicks+1 WHERE id=?", (ad_id,))
        return redirect(row['url'], code=302)

@bp.route('/admin/ads/login', methods=['GET','POST'])
def login():
    if not admin_enabled():
        abort(404)
    error = ''
    if request.method == 'POST':
        require_csrf()
        if hmac.compare_digest(request.form.get('password',''), os.environ['GROOVECATCH_ADS_ADMIN_PASSWORD']):
            session.clear()
            session['ads_admin'] = True
            return redirect(url_for('advertising.admin'))
        error = 'Senha inválida.'
    return render_template('ads_admin.html', login=True, csrf=csrf_token(), error=error)

@bp.route('/admin/ads/logout', methods=['POST'])
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for('advertising.login'))

@bp.get('/admin/ads')
def admin():
    if not admin_enabled():
        abort(404)
    if not is_admin():
        return redirect(url_for('advertising.login'))
    with connection() as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM ads ORDER BY id DESC').fetchall()]
    return render_template('ads_admin.html', login=False, ads=rows, csrf=csrf_token(), slots=SLOTS, kinds=KINDS, error='')

@bp.post('/admin/ads/save')
def save():
    if not is_admin():
        abort(403)
    require_csrf()
    try:
        ad_id = int(request.form.get('id') or 0)
    except ValueError:
        abort(400)
    title = request.form.get('title','').strip()[:90]
    description = request.form.get('description','').strip()[:160]
    url = request.form.get('url','').strip()[:2048]
    image_url = request.form.get('image_url','').strip()[:2048]
    kind = request.form.get('kind','')
    slot = request.form.get('slot','')
    active = int(request.form.get('active') == 'on')
    if not title or not valid_https(url) or (image_url and not valid_https(image_url)) or kind not in KINDS or slot not in SLOTS:
        return 'Dados inválidos. Título, URLs HTTPS e categorias são obrigatórios.', 400
    with connection() as con:
        if ad_id:
            cur = con.execute('UPDATE ads SET title=?,description=?,url=?,image_url=?,kind=?,slot=?,active=? WHERE id=?', (title,description,url,image_url,kind,slot,active,ad_id))
            if not cur.rowcount:
                abort(404)
        else:
            con.execute('INSERT INTO ads(title,description,url,image_url,kind,slot,active,created) VALUES(?,?,?,?,?,?,?,?)', (title,description,url,image_url,kind,slot,active,int(time.time())))
    return redirect(url_for('advertising.admin'))

@bp.post('/admin/ads/delete/<int:ad_id>')
def delete(ad_id):
    if not is_admin():
        abort(403)
    require_csrf()
    with connection() as con:
        con.execute('DELETE FROM ads WHERE id=?', (ad_id,))
    return redirect(url_for('advertising.admin'))
