from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import db, create_document, get_documents
from schemas import Idea, Comment

app = FastAPI(title="Idea Hunt API", version="1.0.1")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IdeaCreate(BaseModel):
    title: str
    description: str
    maker: str
    website: Optional[str] = None
    tags: List[str] = []
    thumbnail: Optional[str] = None


class CommentCreate(BaseModel):
    author: str
    text: str


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "Idea Hunt API"}


@app.get("/test", tags=["health"])
async def test_db():
    # attempt a simple count using abstraction (works for both backends)
    count = len(get_documents("idea", {}, 1_000_000))
    return {"ok": True, "collections": ["idea"], "count": count}


@app.get("/ideas", response_model=List[Idea], tags=["ideas"])
async def list_ideas(limit: int = 100):
    docs = get_documents("idea", {}, limit)
    return docs


@app.post("/ideas", response_model=Idea, tags=["ideas"])
async def create_idea(payload: IdeaCreate):
    data = payload.model_dump()
    data.update({
        "upvotes": 0,
        "comments": [],
        "created_at": datetime.utcnow(),
    })
    inserted_id = create_document("idea", data)
    # fetch created document
    doc = get_documents("idea", {"_id": inserted_id}, 1)
    if not doc:
        raise HTTPException(status_code=500, detail="Failed to create idea")
    return doc[0]


@app.post("/ideas/{idea_id}/upvote", tags=["ideas"])
async def upvote_idea(idea_id: str):
    # Implement upvote compatible with both backends
    docs = get_documents("idea", {"_id": idea_id}, 1)
    if not docs:
        raise HTTPException(status_code=404, detail="Idea not found")
    item = docs[0]
    new_votes = int(item.get("upvotes", 0)) + 1
    from database import update_document
    update_document("idea", {"_id": idea_id}, {"upvotes": new_votes})
    updated = get_documents("idea", {"_id": idea_id}, 1)[0]
    return updated


@app.post("/ideas/{idea_id}/comments", response_model=Idea, tags=["comments"]) 
async def add_comment(idea_id: str, payload: CommentCreate):
    docs = get_documents("idea", {"_id": idea_id}, 1)
    if not docs:
        raise HTTPException(status_code=404, detail="Idea not found")
    comment: Comment = Comment(author=payload.author, text=payload.text, created_at=datetime.utcnow())
    item = docs[0]
    comments = list(item.get("comments", []))
    comments.append(comment.model_dump())
    from database import update_document
    update_document("idea", {"_id": idea_id}, {"comments": comments})
    updated = get_documents("idea", {"_id": idea_id}, 1)[0]
    return updated


# Seed mock data endpoint
@app.post("/seed", tags=["dev"]) 
async def seed_data():
    if len(get_documents("idea", {}, 1)) > 0:
        return {"status": "skipped", "reason": "data already exists"}

    samples = [
        {
            "title": "FocusFox",
            "description": "A playful Pomodoro timer with streaks and a friendly fox mascot.",
            "maker": "Ava K.",
            "website": "https://example.com/focusfox",
            "tags": ["productivity", "timer"],
            "thumbnail": "https://picsum.photos/seed/focusfox/200/200",
            "upvotes": 21,
            "comments": [
                {"author": "Noah", "text": "This UI makes me want to work!", "created_at": datetime.utcnow()},
                {"author": "Liam", "text": "Add shortcuts please", "created_at": datetime.utcnow()},
            ],
            "created_at": datetime.utcnow(),
        },
        {
            "title": "SnackScan",
            "description": "Snap a snack, get nutrition and allergy warnings instantly.",
            "maker": "Maya P.",
            "website": "https://example.com/snackscan",
            "tags": ["health", "ai", "mobile"],
            "thumbnail": "https://picsum.photos/seed/snackscan/200/200",
            "upvotes": 54,
            "comments": [
                {"author": "Olivia", "text": "Great for school lunches!", "created_at": datetime.utcnow()},
            ],
            "created_at": datetime.utcnow(),
        },
        {
            "title": "Inkling",
            "description": "Daily writing prompts that grow with your style.",
            "maker": "Ravi S.",
            "website": "https://example.com/inkling",
            "tags": ["writing", "creative"],
            "thumbnail": "https://picsum.photos/seed/inkling/200/200",
            "upvotes": 12,
            "comments": [],
            "created_at": datetime.utcnow(),
        },
    ]

    for s in samples:
        create_document("idea", s)

    return {"status": "seeded", "count": len(samples)}
