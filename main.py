import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from passlib.context import CryptContext
from bson import ObjectId

from database import db

# Environment
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "60"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Rahi Enterprise API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------- Pydantic Models -------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    username: str

class ProductIn(BaseModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    price: float = Field(..., ge=0)
    imageUrl: Optional[str] = Field(None)
    amazonLink: Optional[str] = Field(None)

class ProductOut(ProductIn):
    id: str
    createdAt: Optional[datetime]


# ------------------------- Helpers -------------------------

def create_jwt(payload: dict, expires_minutes: int = JWT_EXPIRES_MIN) -> str:
    to_encode = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")
    return token


def verify_jwt(token: str) -> dict:
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return decoded
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    return parts[1]


def require_auth(token: str = Depends(get_bearer_token)) -> dict:
    return verify_jwt(token)


def seed_admin_if_needed():
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        return
    existing = db["admin"].find_one({"username": username})
    if not existing:
        hashed = pwd_context.hash(password)
        db["admin"].insert_one({
            "username": username,
            "password": hashed,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })


def serialize_product(doc: dict) -> ProductOut:
    return ProductOut(
        id=str(doc.get("_id")),
        name=doc.get("name"),
        description=doc.get("description"),
        price=float(doc.get("price", 0)),
        imageUrl=doc.get("imageUrl"),
        amazonLink=doc.get("amazonLink"),
        createdAt=doc.get("createdAt") or doc.get("created_at"),
    )


# ------------------------- Routes -------------------------
@app.on_event("startup")
def on_startup():
    # Seed admin if env provided
    try:
        seed_admin_if_needed()
    except Exception:
        pass

@app.get("/")
def root():
    return {"message": "Rahi Enterprise API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# Auth: POST /api/admin/login
@app.post("/api/admin/login", response_model=LoginResponse)
def admin_login(payload: LoginRequest):
    admin = db["admin"].find_one({"username": payload.username})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    hashed = admin.get("password")
    if not pwd_context.verify(payload.password, hashed):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_jwt({"sub": payload.username, "role": "admin"})
    return LoginResponse(token=token, username=payload.username)

# Public: GET /api/products
@app.get("/api/products", response_model=List[ProductOut])
def get_products():
    cursor = db["product"].find({}).sort("createdAt", -1)
    products = [serialize_product(doc) for doc in cursor]
    return products

# Protected: POST /api/products
@app.post("/api/products", response_model=ProductOut)
def add_product(product: ProductIn, _: dict = Depends(require_auth)):
    doc = product.model_dump()
    now = datetime.now(timezone.utc)
    doc.update({
        "createdAt": now,
        "created_at": now,
        "updated_at": now,
    })
    result = db["product"].insert_one(doc)
    saved = db["product"].find_one({"_id": result.inserted_id})
    return serialize_product(saved)

# Protected: DELETE /api/products/{id}
@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, _: dict = Depends(require_auth)):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")
    res = db["product"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "id": product_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
