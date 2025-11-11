"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- Admin -> "admin" collection
- Product -> "product" collection
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime

class Admin(BaseModel):
    """
    Admins collection schema
    Collection name: "admin"
    """
    username: str = Field(..., description="Admin username")
    password: str = Field(..., description="Hashed password")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product"
    """
    name: str = Field(..., description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in currency units")
    imageUrl: Optional[str] = Field(None, description="Image URL")
    amazonLink: Optional[str] = Field(None, description="Amazon product link")
    createdAt: Optional[datetime] = Field(default=None, description="Created at timestamp")
