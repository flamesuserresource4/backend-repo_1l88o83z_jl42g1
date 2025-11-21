"""
Database Schemas for Product Hunt-like app

Define MongoDB collection schemas using Pydantic models.
Each class name lowercased maps to the collection name.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class Comment(BaseModel):
    author: str = Field(..., description="Display name of commenter")
    text: str = Field(..., description="Comment body")
    created_at: Optional[datetime] = Field(None, description="UTC timestamp of creation")


class Idea(BaseModel):
    title: str = Field(..., description="Idea title")
    description: str = Field(..., description="Short description of the idea")
    maker: str = Field(..., description="Who submitted the idea")
    website: Optional[HttpUrl] = Field(None, description="Optional landing page or demo URL")
    tags: List[str] = Field(default_factory=list, description="Topic tags")
    upvotes: int = Field(0, ge=0, description="Number of upvotes")
    thumbnail: Optional[HttpUrl] = Field(None, description="Image or logo URL")
    comments: List[Comment] = Field(default_factory=list, description="Comments on the idea")
    created_at: Optional[datetime] = Field(None, description="UTC timestamp of creation")
