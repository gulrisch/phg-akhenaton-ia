from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import boto3
from botocore.client import Config
import psycopg2
import psycopg2.extras
import os
import uuid
import stripe

app = FastAPI(title="PHG AKHENATON IA — Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CONFIG ──
R2_ENDPOINT   = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET     = os.getenv("R2_BUCKET", "phgedition")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-1eeb31517baa4733a5ce9d63ac6a98aa.r2.dev")
DATABASE_URL  = os.getenv("DATABASE_URL")
ADMIN_KEY     = os.getenv("ADMIN_KEY", "phg-admin-2026")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ── BOOKS ──
BOOKS = [
    {"id": "zarek-archiviste",        "titre": "Les 48 Lois de Zarek",       "achat": 594,  "location": 149,  "stream": 89},
    {"id": "figuier-de-canaan",       "titre": "Le Figuier de Canaan",        "achat": 509,  "location": 127,  "stream": 76},
    {"id": "eldorado-ombres",         "titre": "Eldorado des Ombres",         "achat": 849,  "location": 212,  "stream": 127},
    {"id": "de-rien-a-la-liberte",    "titre": "De Rien a la Liberte",        "achat": 764,  "location": 191,  "stream": 115},
    {"id": "loi-semence",             "titre": "La Loi de la Semence",        "achat": 424,  "location": 106,  "stream": 64},
    {"id": "violence-humaine",        "titre": "La Violence Humaine",         "achat": 849,  "location": 212,  "stream": 127},
    {"id": "grand-secret",            "titre": "Le Grand Secret",             "achat": 509,  "location": 127,  "stream": 76},
    {"id": "manifestation-explosion", "titre": "Manifestation Financiere",    "achat": 1699, "location": 425,  "stream": 255},
    {"id": "afrique-civilisation",    "titre": "Afrique Civilisation",        "achat": 849,  "location": 212,  "stream": 127},
    {"id": "dernier-pauvre-famille",  "titre": "Le Dernier Pauvre",           "achat": 1274, "location": 319,  "stream": 191},
]

# ── R2 ──
def get_r2():
    return boto3.client("s3", endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY, aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"), region_name="auto")

# ── DB ──
def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    tables = [
        """CREATE TABLE IF NOT EXISTS oeuvres (
            id SERIAL PRIMARY KEY, uid UUID DEFAULT gen_random_uuid(),
            titre TEXT NOT NULL, sous_titre TEXT, auteur TEXT NOT NULL,
            email_auteur TEXT NOT NULL, categorie TEXT, description TEXT,
            tags TEXT, biographie TEXT, liens_auteur TEXT,
            fichier_url TEXT, cover_url TEXT,
            prix_achat NUMERIC(10,2), prix_location NUMERIC(10,2),
            prix_stream NUMERIC(10,2), acces_gratuit BOOLEAN DEFAULT FALSE,
            lien_externe TEXT, statut TEXT DEFAULT 'en_attente',
            stripe_product_id TEXT, stripe_price_achat TEXT,
            stripe_price_location TEXT, stripe_price_stream TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS avis (
            id SERIAL PRIMARY KEY, oeuvre_id INTEGER,
            nom TEXT NOT NULL, email TEXT, texte TEXT NOT NULL,
            note INTEGER NOT NULL, verifie BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS stripe_products (
            id SERIAL PRIMARY KEY, book_id TEXT UNIQUE,
            product_id TEXT, price_achat TEXT,
            price_location TEXT, price_stream TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
    ]
    for sql in tables:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ Table: {e}")
    print("✅ Tables prêtes.")

def create_stripe_products():
    try:
        conn = get_db()
        cur = conn.cursor()
        for book in BOOKS:
            cur.execute("SELECT book_id FROM stripe_products WHERE book_id=%s", (book["id"],))
            if cur.fetchone():
                print(f"⏭️  {book['id']} déjà dans Stripe")
                continue
            prod = stripe.Product.create(name=book["titre"], metadata={"book_id": book["id"]})
            pa = stripe.Price.create(product=prod.id, unit_amount=book["achat"],   currency="eur", nickname="Achat")
            pl = stripe.Price.create(product=prod.id, unit_amount=book["location"],currency="eur", nickname="Location")
            ps = stripe.Price.create(product=prod.id, unit_amount=book["stream"],  currency="eur", nickname="Stream")
            cur.execute("""
                INSERT INTO stripe_products (book_id, product_id, price_achat, price_location, price_stream)
                VALUES (%s,%s,%s,%s,%s)
            """, (book["id"], prod.id, pa.id, pl.id, ps.id))
            conn.commit()
            print(f"✅ Stripe: {book['id']} — {prod.id}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Stripe products: {e}")

@app.on_event("startup")
def startup():
    init_db()
    create_stripe_products()

# ── HEALTH ──
@app.get("/")
def root():
    return {"status": "PHG AKHENATON IA ✅", "version": "2.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ── STRIPE PRODUCTS ──
@app.get("/stripe/products")
def get_stripe_products():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM stripe_products ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "products": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── CHECKOUT SESSION ──
@app.post("/checkout")
async def create_checkout(
    book_id: str = Form(...),
    mode: str = Form(...),  # achat, location, stream
    success_url: str = Form("https://phg-akhenaton-frontend-production.up.railway.app/pages/success.html"),
    cancel_url: str = Form("https://phg-akhenaton-frontend-production.up.railway.app/pages/catalogue.html"),
):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM stripe_products WHERE book_id=%s", (book_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(404, "Produit introuvable")
        price_map = {"achat": row["price_achat"], "location": row["price_location"], "stream": row["price_stream"]}
        price_id = price_map.get(mode)
        if not price_id:
            raise HTTPException(400, "Mode invalide")
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
        )
        return {"success": True, "checkout_url": session.url, "session_id": session.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ── UPLOAD OEUVRE ──
@app.post("/upload/oeuvre")
async def upload_oeuvre(
    fichier: UploadFile = File(...),
    couverture: UploadFile = File(None),
    titre: str = Form(...), sous_titre: str = Form(""),
    categorie: str = Form(""), description: str = Form(""),
    tags: str = Form(""), auteur: str = Form(...),
    email_auteur: str = Form(...), biographie: str = Form(""),
    liens_auteur: str = Form(""), prix_achat: float = Form(None),
    prix_location: float = Form(None), prix_stream: float = Form(None),
    acces_gratuit: bool = Form(False), lien_externe: str = Form(""),
):
    fname = fichier.filename.lower()
    if not any(fname.endswith(e) for e in [".pdf", ".epub", ".mobi"]):
        raise HTTPException(400, "Format non supporté")
    content = await fichier.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop lourd (max 50Mo)")
    uid = str(uuid.uuid4())
    ext = fname.rsplit(".", 1)[-1]
    r2 = get_r2()
    r2.put_object(Bucket=R2_BUCKET, Key=f"livres/{uid}.{ext}", Body=content, ContentType="application/octet-stream")
    fichier_url = f"{R2_PUBLIC_URL}/livres/{uid}.{ext}"
    cover_url = None
    if couverture and couverture.filename:
        cc = await couverture.read()
        cext = couverture.filename.rsplit(".", 1)[-1].lower()
        r2.put_object(Bucket=R2_BUCKET, Key=f"covers/{uid}.{cext}", Body=cc, ContentType="image/jpeg")
        cover_url = f"{R2_PUBLIC_URL}/covers/{uid}.{cext}"
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO oeuvres (uid,titre,sous_titre,auteur,email_auteur,categorie,description,
            tags,biographie,liens_auteur,fichier_url,cover_url,prix_achat,prix_location,
            prix_stream,acces_gratuit,lien_externe,statut)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'en_attente')
            RETURNING id, uid
        """, (uid,titre,sous_titre,auteur,email_auteur,categorie,description,
              tags,biographie,liens_auteur,fichier_url,cover_url,prix_achat,
              prix_location,prix_stream,acces_gratuit,lien_externe))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(500, str(e))
    return JSONResponse({"success": True, "message": "Œuvre soumise. Publication sous 24h.", "id": row["id"], "uid": str(row["uid"])})

# ── CATALOGUE ──
@app.get("/catalogue")
def get_catalogue(categorie: str = None, page: int = 1, limit: int = 20):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        offset = (page - 1) * limit
        if categorie:
            cur.execute("SELECT * FROM oeuvres WHERE statut='publie' AND categorie ILIKE %s ORDER BY created_at DESC LIMIT %s OFFSET %s", (f"%{categorie}%", limit, offset))
        else:
            cur.execute("SELECT * FROM oeuvres WHERE statut='publie' ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "oeuvres": [dict(r) for r in rows], "page": page}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── AVIS ──
@app.post("/oeuvre/{oeuvre_id}/avis")
async def poster_avis(oeuvre_id: int, nom: str = Form(...), texte: str = Form(...), note: int = Form(...), email: str = Form("")):
    if not 1 <= note <= 5:
        raise HTTPException(400, "Note invalide")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO avis (oeuvre_id,nom,email,texte,note) VALUES (%s,%s,%s,%s,%s) RETURNING id", (oeuvre_id,nom,email,texte,note))
        avis_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id": avis_id}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/oeuvre/{oeuvre_id}/avis")
def get_avis(oeuvre_id: int):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT nom,texte,note,verifie,created_at FROM avis WHERE oeuvre_id=%s ORDER BY created_at DESC", (oeuvre_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        avg = round(sum(r["note"] for r in rows)/len(rows), 1) if rows else 0
        return {"success": True, "avis": [dict(r) for r in rows], "moyenne": avg, "total": len(rows)}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── ADMIN ──
@app.patch("/admin/oeuvre/{uid}/publier")
def publier(uid: str, admin_key: str = Form(...)):
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "Clé invalide")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE oeuvres SET statut='publie' WHERE uid=%s RETURNING id", (uid,))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(404, "Introuvable")
        return {"success": True, "message": "Publiée ✅"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/admin/oeuvres/en-attente")
def en_attente(admin_key: str = ""):
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "Clé invalide")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id,uid,titre,auteur,email_auteur,fichier_url,created_at FROM oeuvres WHERE statut='en_attente' ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "oeuvres": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(500, str(e))
