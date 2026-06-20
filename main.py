from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import boto3
from botocore.client import Config
import psycopg2
import psycopg2.extras
import os
import uuid
import mimetypes
from datetime import datetime

app = FastAPI(title="PHG AKHENATON IA — Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CONFIG R2 ──
R2_ENDPOINT      = os.getenv("R2_ENDPOINT")        # https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY    = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY    = os.getenv("R2_SECRET_KEY")
R2_BUCKET        = os.getenv("R2_BUCKET", "phgedition")
R2_PUBLIC_URL    = os.getenv("R2_PUBLIC_URL")      # https://pub-xxxx.r2.dev

# ── CONFIG PostgreSQL ──
DATABASE_URL = os.getenv("DATABASE_URL")           # postgresql://user:pass@host/db

# ── R2 CLIENT ──
def get_r2():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

# ── DB CONNECTION ──
def get_db():
    return psycopg2.connect(DATABASE_URL)

# ── INIT TABLE ──
def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS oeuvres (
                id            SERIAL PRIMARY KEY,
                uid           UUID DEFAULT gen_random_uuid(),
                titre         TEXT NOT NULL,
                sous_titre    TEXT,
                auteur        TEXT NOT NULL,
                email_auteur  TEXT NOT NULL,
                categorie     TEXT,
                description   TEXT,
                tags          TEXT,
                biographie    TEXT,
                liens_auteur  TEXT,
                fichier_url   TEXT,
                cover_url     TEXT,
                prix_achat    NUMERIC(10,2),
                prix_location NUMERIC(10,2),
                prix_stream   NUMERIC(10,2),
                acces_gratuit BOOLEAN DEFAULT FALSE,
                lien_externe  TEXT,
                statut        TEXT DEFAULT 'en_attente',
                created_at    TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Table 'oeuvres' prête.")
    except Exception as e:
        print(f"⚠️ DB init error: {e}")

@app.on_event("startup")
def startup():
    init_db()

# ══════════════════════════════════════
# ROUTE : Santé
# ══════════════════════════════════════
@app.get("/")
def root():
    return {"status": "PHG AKHENATON IA — Backend opérationnel ✅"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "phg-akhenaton"}

# ══════════════════════════════════════
# ROUTE : Upload œuvre (auteur)
# ══════════════════════════════════════
@app.post("/upload/oeuvre")
async def upload_oeuvre(
    # Fichier
    fichier: UploadFile = File(...),
    couverture: UploadFile = File(None),
    # Infos œuvre
    titre: str = Form(...),
    sous_titre: str = Form(""),
    categorie: str = Form(""),
    description: str = Form(""),
    tags: str = Form(""),
    # Auteur
    auteur: str = Form(...),
    email_auteur: str = Form(...),
    biographie: str = Form(""),
    liens_auteur: str = Form(""),   # JSON string [{type, label, url}]
    # Accès & Prix
    prix_achat: float = Form(None),
    prix_location: float = Form(None),
    prix_stream: float = Form(None),
    acces_gratuit: bool = Form(False),
    lien_externe: str = Form(""),
):
    # ── Validation type fichier ──
    ALLOWED = {
        "application/pdf": ".pdf",
        "application/epub+zip": ".epub",
        "application/x-mobipocket-ebook": ".mobi",
        "application/octet-stream": "",
    }
    ext_map = {".pdf": "pdf", ".epub": "epub", ".mobi": "mobi"}
    fname = fichier.filename.lower()
    if not any(fname.endswith(e) for e in [".pdf", ".epub", ".mobi"]):
        raise HTTPException(400, "Format non supporté. Acceptés : PDF, EPUB, MOBI")

    # ── Limite 50 Mo ──
    content = await fichier.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop lourd (max 50 Mo)")

    r2 = get_r2()
    uid = str(uuid.uuid4())
    ext = fname.rsplit(".", 1)[-1]

    # ── Upload fichier vers R2 ──
    fichier_key = f"livres/{uid}.{ext}"
    r2.put_object(
        Bucket=R2_BUCKET,
        Key=fichier_key,
        Body=content,
        ContentType=fichier.content_type or "application/octet-stream",
    )
    fichier_url = f"{R2_PUBLIC_URL}/{fichier_key}"

    # ── Upload couverture (optionnel) ──
    cover_url = None
    if couverture and couverture.filename:
        cover_content = await couverture.read()
        cover_ext = couverture.filename.rsplit(".", 1)[-1].lower()
        cover_key = f"covers/{uid}.{cover_ext}"
        r2.put_object(
            Bucket=R2_BUCKET,
            Key=cover_key,
            Body=cover_content,
            ContentType=couverture.content_type or "image/jpeg",
        )
        cover_url = f"{R2_PUBLIC_URL}/{cover_key}"

    # ── Enregistrement PostgreSQL ──
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO oeuvres (
                uid, titre, sous_titre, auteur, email_auteur,
                categorie, description, tags, biographie, liens_auteur,
                fichier_url, cover_url,
                prix_achat, prix_location, prix_stream, acces_gratuit, lien_externe,
                statut
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,
                %s,%s,%s,%s,%s,
                'en_attente'
            ) RETURNING id, uid, created_at
        """, (
            uid, titre, sous_titre, auteur, email_auteur,
            categorie, description, tags, biographie, liens_auteur,
            fichier_url, cover_url,
            prix_achat, prix_location, prix_stream, acces_gratuit, lien_externe,
        ))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {str(e)}")

    return JSONResponse({
        "success": True,
        "message": "Œuvre soumise avec succès. Publication sous 24h après validation.",
        "id": row["id"],
        "uid": str(row["uid"]),
        "fichier_url": fichier_url,
        "cover_url": cover_url,
        "statut": "en_attente",
    })

# ══════════════════════════════════════
# ROUTE : Catalogue public
# ══════════════════════════════════════
@app.get("/catalogue")
def get_catalogue(categorie: str = None, page: int = 1, limit: int = 20):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        offset = (page - 1) * limit
        if categorie:
            cur.execute("""
                SELECT id, uid, titre, sous_titre, auteur, categorie, description,
                       tags, cover_url, prix_achat, prix_location, prix_stream,
                       acces_gratuit, lien_externe, liens_auteur, created_at
                FROM oeuvres WHERE statut = 'publie' AND categorie ILIKE %s
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (f"%{categorie}%", limit, offset))
        else:
            cur.execute("""
                SELECT id, uid, titre, sous_titre, auteur, categorie, description,
                       tags, cover_url, prix_achat, prix_location, prix_stream,
                       acces_gratuit, lien_externe, liens_auteur, created_at
                FROM oeuvres WHERE statut = 'publie'
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """, (limit, offset))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "oeuvres": [dict(r) for r in rows], "page": page}
    except Exception as e:
        raise HTTPException(500, str(e))

# ══════════════════════════════════════
# ROUTE : Fiche œuvre
# ══════════════════════════════════════
@app.get("/oeuvre/{uid}")
def get_oeuvre(uid: str):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, uid, titre, sous_titre, auteur, categorie, description,
                   tags, biographie, liens_auteur, cover_url, fichier_url,
                   prix_achat, prix_location, prix_stream, acces_gratuit, lien_externe,
                   statut, created_at
            FROM oeuvres WHERE uid = %s AND statut = 'publie'
        """, (uid,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(404, "Œuvre introuvable")
        return {"success": True, "oeuvre": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ══════════════════════════════════════
# ROUTE : Avis
# ══════════════════════════════════════
@app.post("/oeuvre/{oeuvre_id}/avis")
async def poster_avis(
    oeuvre_id: int,
    nom: str = Form(...),
    texte: str = Form(...),
    note: int = Form(...),
    email: str = Form(""),
):
    if not 1 <= note <= 5:
        raise HTTPException(400, "Note invalide (1-5)")
    try:
        conn = get_db()
        cur = conn.cursor()
        # Créer table avis si besoin
        cur.execute("""
            CREATE TABLE IF NOT EXISTS avis (
                id         SERIAL PRIMARY KEY,
                oeuvre_id  INTEGER REFERENCES oeuvres(id),
                nom        TEXT NOT NULL,
                email      TEXT,
                texte      TEXT NOT NULL,
                note       INTEGER NOT NULL,
                verifie    BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            INSERT INTO avis (oeuvre_id, nom, email, texte, note)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (oeuvre_id, nom, email, texte, note))
        avis_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Avis soumis. Visible après modération.", "id": avis_id}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/oeuvre/{oeuvre_id}/avis")
def get_avis(oeuvre_id: int):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT nom, texte, note, verifie, created_at
            FROM avis WHERE oeuvre_id = %s
            ORDER BY created_at DESC
        """, (oeuvre_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        avg = round(sum(r["note"] for r in rows)/len(rows), 1) if rows else 0
        return {"success": True, "avis": [dict(r) for r in rows], "moyenne": avg, "total": len(rows)}
    except Exception as e:
        raise HTTPException(500, str(e))

# ══════════════════════════════════════
# ROUTE : Admin — valider une œuvre
# ══════════════════════════════════════
@app.patch("/admin/oeuvre/{uid}/publier")
def publier_oeuvre(uid: str, admin_key: str = Form(...)):
    if admin_key != os.getenv("ADMIN_KEY", "phg-admin-2026"):
        raise HTTPException(403, "Clé admin invalide")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE oeuvres SET statut='publie' WHERE uid=%s RETURNING id", (uid,))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(404, "Œuvre introuvable")
        return {"success": True, "message": "Œuvre publiée ✅"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

