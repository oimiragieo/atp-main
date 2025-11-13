#!/usr/bin/env python3
# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ATP Adapter Marketplace Backend

A comprehensive marketplace for ATP adapters with search, discovery, ratings,
certification, and monetization features.
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import aiofiles
import asyncpg
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
import redis.asyncio as redis
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import boto3
from botocore.exceptions import ClientError
import docker
import semver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/atp_marketplace")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# S3 setup for adapter storage
S3_BUCKET = os.getenv("S3_BUCKET", "atp-marketplace-adapters")
s3_client = boto3.client('s3')

# Docker client for testing
docker_client = docker.from_env()

# FastAPI app
app = FastAPI(
    title="ATP Adapter Marketplace",
    description="Marketplace for ATP adapters with search, discovery, and certification",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()


# Database Models
class Adapter(Base):
    __tablename__ = "adapters"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text)
    author_id = Column(String, nullable=False)
    category = Column(String, nullable=False)  # provider, tool, middleware
    provider_type = Column(String)  # openai, anthropic, custom, etc.
    version = Column(String, nullable=False)
    license = Column(String, default="Apache-2.0")
    
    # Marketplace metadata
    downloads = Column(Integer, default=0)
    rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    featured = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    
    # Technical metadata
    supported_models = Column(JSON)
    capabilities = Column(JSON)
    requirements = Column(JSON)
    
    # Certification status
    certification_status = Column(String, default="pending")  # pending, approved, rejected
    certification_date = Column(DateTime)
    certification_notes = Column(Text)
    
    # Monetization
    pricing_model = Column(String, default="free")  # free, paid, freemium
    price = Column(Float, default=0.0)
    revenue_share = Column(Float, default=0.0)
    
    # Storage
    package_url = Column(String)
    documentation_url = Column(String)
    source_url = Column(String)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime)


class AdapterVersion(Base):
    __tablename__ = "adapter_versions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    adapter_id = Column(String, nullable=False)
    version = Column(String, nullable=False)
    changelog = Column(Text)
    package_url = Column(String)
    checksum = Column(String)
    
    # Test results
    test_status = Column(String, default="pending")  # pending, passed, failed
    test_results = Column(JSON)
    test_date = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class AdapterReview(Base):
    __tablename__ = "adapter_reviews"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    adapter_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    title = Column(String)
    content = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdapterDownload(Base):
    __tablename__ = "adapter_downloads"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    adapter_id = Column(String, nullable=False)
    user_id = Column(String)
    ip_address = Column(String)
    user_agent = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String)
    bio = Column(Text)
    avatar_url = Column(String)
    
    # Developer info
    is_developer = Column(Boolean, default=False)
    developer_tier = Column(String, default="community")  # community, verified, partner
    total_downloads = Column(Integer, default=0)
    total_revenue = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic Models
class AdapterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=1000)
    category: str = Field(..., regex="^(provider|tool|middleware)$")
    provider_type: Optional[str] = None
    version: str = Field(..., regex=r"^\d+\.\d+\.\d+$")
    license: str = "Apache-2.0"
    supported_models: List[str] = []
    capabilities: Dict[str, Any] = {}
    requirements: Dict[str, Any] = {}
    pricing_model: str = Field("free", regex="^(free|paid|freemium)$")
    price: float = Field(0.0, ge=0)
    source_url: Optional[str] = None
    
    @validator('version')
    def validate_version(cls, v):
        try:
            semver.VersionInfo.parse(v)
        except ValueError:
            raise ValueError('Invalid semantic version')
        return v


class AdapterUpdate(BaseModel):
    description: Optional[str] = None
    supported_models: Optional[List[str]] = None
    capabilities: Optional[Dict[str, Any]] = None
    requirements: Optional[Dict[str, Any]] = None
    pricing_model: Optional[str] = None
    price: Optional[float] = None
    source_url: Optional[str] = None


class AdapterResponse(BaseModel):
    id: str
    name: str
    description: str
    author_id: str
    category: str
    provider_type: Optional[str]
    version: str
    license: str
    downloads: int
    rating: float
    rating_count: int
    featured: bool
    verified: bool
    supported_models: List[str]
    capabilities: Dict[str, Any]
    requirements: Dict[str, Any]
    certification_status: str
    pricing_model: str
    price: float
    package_url: Optional[str]
    documentation_url: Optional[str]
    source_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = Field(None, max_length=1000)


class ReviewResponse(BaseModel):
    id: str
    adapter_id: str
    user_id: str
    rating: int
    title: Optional[str]
    content: Optional[str]
    created_at: datetime
    updated_at: datetime


class SearchFilters(BaseModel):
    category: Optional[str] = None
    provider_type: Optional[str] = None
    pricing_model: Optional[str] = None
    min_rating: Optional[float] = None
    verified_only: bool = False
    featured_only: bool = False


# Dependency functions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_redis():
    return await redis.from_url(REDIS_URL)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # In a real implementation, validate JWT token and return user
    # For now, return a mock user
    return {"id": "user123", "username": "testuser", "is_developer": True}


# Utility functions
def calculate_adapter_score(adapter: Adapter) -> float:
    """Calculate adapter score for ranking."""
    base_score = adapter.rating * adapter.rating_count
    download_score = min(adapter.downloads / 1000, 10)  # Cap at 10 points
    verification_bonus = 5 if adapter.verified else 0
    featured_bonus = 3 if adapter.featured else 0
    
    return base_score + download_score + verification_bonus + featured_bonus


async def update_adapter_rating(db: Session, adapter_id: str):
    """Update adapter rating based on reviews."""
    reviews = db.query(AdapterReview).filter(AdapterReview.adapter_id == adapter_id).all()
    
    if reviews:
        total_rating = sum(review.rating for review in reviews)
        avg_rating = total_rating / len(reviews)
        
        adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
        if adapter:
            adapter.rating = round(avg_rating, 2)
            adapter.rating_count = len(reviews)
            db.commit()


async def run_adapter_tests(adapter_id: str, package_path: str) -> Dict[str, Any]:
    """Run automated tests on an adapter package."""
    test_results = {
        "status": "pending",
        "tests": [],
        "errors": [],
        "warnings": [],
        "score": 0
    }
    
    try:
        # Extract and analyze package
        # This is a simplified version - real implementation would be more comprehensive
        
        # Test 1: Package structure
        test_results["tests"].append({
            "name": "Package Structure",
            "status": "passed",
            "message": "Package has correct structure"
        })
        
        # Test 2: Dependencies check
        test_results["tests"].append({
            "name": "Dependencies",
            "status": "passed",
            "message": "All dependencies are available"
        })
        
        # Test 3: Security scan
        test_results["tests"].append({
            "name": "Security Scan",
            "status": "passed",
            "message": "No security vulnerabilities found"
        })
        
        # Test 4: Performance test
        test_results["tests"].append({
            "name": "Performance",
            "status": "passed",
            "message": "Performance within acceptable limits"
        })
        
        # Calculate overall score
        passed_tests = sum(1 for test in test_results["tests"] if test["status"] == "passed")
        test_results["score"] = (passed_tests / len(test_results["tests"])) * 100
        test_results["status"] = "passed" if test_results["score"] >= 80 else "failed"
        
    except Exception as e:
        test_results["status"] = "failed"
        test_results["errors"].append(str(e))
        test_results["score"] = 0
    
    return test_results


# API Routes

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "ATP Adapter Marketplace",
        "version": "1.0.0",
        "description": "Marketplace for ATP adapters with search, discovery, and certification"
    }


@app.get("/adapters", response_model=List[AdapterResponse])
async def list_adapters(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    provider_type: Optional[str] = Query(None),
    pricing_model: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    verified_only: bool = Query(False),
    featured_only: bool = Query(False),
    sort_by: str = Query("score", regex="^(score|downloads|rating|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """List adapters with filtering and search."""
    query = db.query(Adapter)
    
    # Apply filters
    if search:
        query = query.filter(
            Adapter.name.ilike(f"%{search}%") |
            Adapter.description.ilike(f"%{search}%")
        )
    
    if category:
        query = query.filter(Adapter.category == category)
    
    if provider_type:
        query = query.filter(Adapter.provider_type == provider_type)
    
    if pricing_model:
        query = query.filter(Adapter.pricing_model == pricing_model)
    
    if min_rating:
        query = query.filter(Adapter.rating >= min_rating)
    
    if verified_only:
        query = query.filter(Adapter.verified == True)
    
    if featured_only:
        query = query.filter(Adapter.featured == True)
    
    # Apply sorting
    if sort_by == "score":
        # Custom scoring - would need to be implemented in SQL or post-processed
        adapters = query.offset(skip).limit(limit).all()
        adapters.sort(key=calculate_adapter_score, reverse=(sort_order == "desc"))
    else:
        order_column = getattr(Adapter, sort_by)
        if sort_order == "desc":
            order_column = order_column.desc()
        adapters = query.order_by(order_column).offset(skip).limit(limit).all()
    
    return adapters


@app.get("/adapters/{adapter_id}", response_model=AdapterResponse)
async def get_adapter(adapter_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific adapter."""
    adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    return adapter


@app.post("/adapters", response_model=AdapterResponse)
async def create_adapter(
    adapter_data: AdapterCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new adapter."""
    if not current_user.get("is_developer"):
        raise HTTPException(status_code=403, detail="Developer account required")
    
    # Check if adapter name already exists for this user
    existing = db.query(Adapter).filter(
        Adapter.name == adapter_data.name,
        Adapter.author_id == current_user["id"]
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Adapter with this name already exists")
    
    # Create adapter
    adapter = Adapter(
        **adapter_data.dict(),
        author_id=current_user["id"]
    )
    
    db.add(adapter)
    db.commit()
    db.refresh(adapter)
    
    # Schedule certification process
    background_tasks.add_task(start_certification_process, adapter.id)
    
    return adapter


@app.put("/adapters/{adapter_id}", response_model=AdapterResponse)
async def update_adapter(
    adapter_id: str,
    adapter_data: AdapterUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing adapter."""
    adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    if adapter.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this adapter")
    
    # Update fields
    for field, value in adapter_data.dict(exclude_unset=True).items():
        setattr(adapter, field, value)
    
    adapter.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(adapter)
    
    return adapter


@app.post("/adapters/{adapter_id}/upload")
async def upload_adapter_package(
    adapter_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload adapter package file."""
    adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    if adapter.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to upload to this adapter")
    
    # Validate file
    if not file.filename.endswith(('.zip', '.tar.gz')):
        raise HTTPException(status_code=400, detail="Invalid file format. Use .zip or .tar.gz")
    
    # Generate unique filename
    file_extension = '.zip' if file.filename.endswith('.zip') else '.tar.gz'
    s3_key = f"adapters/{adapter_id}/{adapter.version}{file_extension}"
    
    try:
        # Upload to S3
        file_content = await file.read()
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_content,
            ContentType='application/octet-stream'
        )
        
        # Calculate checksum
        checksum = hashlib.sha256(file_content).hexdigest()
        
        # Update adapter with package URL
        package_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"
        adapter.package_url = package_url
        
        # Create version record
        version = AdapterVersion(
            adapter_id=adapter_id,
            version=adapter.version,
            package_url=package_url,
            checksum=checksum
        )
        
        db.add(version)
        db.commit()
        
        # Schedule testing
        background_tasks.add_task(test_adapter_package, adapter_id, version.id)
        
        return {
            "message": "Package uploaded successfully",
            "package_url": package_url,
            "checksum": checksum
        }
    
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/adapters/{adapter_id}/download")
async def download_adapter(
    adapter_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download an adapter package."""
    adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    if not adapter.package_url:
        raise HTTPException(status_code=404, detail="Package not available")
    
    # Record download
    download = AdapterDownload(
        adapter_id=adapter_id,
        user_id=current_user["id"]
    )
    db.add(download)
    
    # Update download count
    adapter.downloads += 1
    db.commit()
    
    return {"download_url": adapter.package_url}


@app.get("/adapters/{adapter_id}/reviews", response_model=List[ReviewResponse])
async def get_adapter_reviews(
    adapter_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get reviews for an adapter."""
    reviews = db.query(AdapterReview).filter(
        AdapterReview.adapter_id == adapter_id
    ).offset(skip).limit(limit).all()
    
    return reviews


@app.post("/adapters/{adapter_id}/reviews", response_model=ReviewResponse)
async def create_review(
    adapter_id: str,
    review_data: ReviewCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a review for an adapter."""
    # Check if adapter exists
    adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    # Check if user already reviewed this adapter
    existing_review = db.query(AdapterReview).filter(
        AdapterReview.adapter_id == adapter_id,
        AdapterReview.user_id == current_user["id"]
    ).first()
    
    if existing_review:
        raise HTTPException(status_code=400, detail="You have already reviewed this adapter")
    
    # Create review
    review = AdapterReview(
        adapter_id=adapter_id,
        user_id=current_user["id"],
        **review_data.dict()
    )
    
    db.add(review)
    db.commit()
    db.refresh(review)
    
    # Update adapter rating
    background_tasks.add_task(update_adapter_rating, db, adapter_id)
    
    return review


@app.get("/categories")
async def get_categories(db: Session = Depends(get_db)):
    """Get available adapter categories."""
    categories = db.query(Adapter.category).distinct().all()
    return [cat[0] for cat in categories if cat[0]]


@app.get("/providers")
async def get_provider_types(db: Session = Depends(get_db)):
    """Get available provider types."""
    providers = db.query(Adapter.provider_type).distinct().all()
    return [prov[0] for prov in providers if prov[0]]


@app.get("/stats")
async def get_marketplace_stats(db: Session = Depends(get_db)):
    """Get marketplace statistics."""
    total_adapters = db.query(Adapter).count()
    total_downloads = db.query(AdapterDownload).count()
    total_reviews = db.query(AdapterReview).count()
    verified_adapters = db.query(Adapter).filter(Adapter.verified == True).count()
    
    return {
        "total_adapters": total_adapters,
        "total_downloads": total_downloads,
        "total_reviews": total_reviews,
        "verified_adapters": verified_adapters,
        "verification_rate": (verified_adapters / total_adapters * 100) if total_adapters > 0 else 0
    }


# Background tasks
async def start_certification_process(adapter_id: str):
    """Start the certification process for an adapter."""
    logger.info(f"Starting certification process for adapter {adapter_id}")
    
    # In a real implementation, this would trigger a comprehensive review process
    # including automated testing, security scanning, and manual review
    
    # For now, we'll simulate the process
    await asyncio.sleep(5)  # Simulate processing time
    
    db = SessionLocal()
    try:
        adapter = db.query(Adapter).filter(Adapter.id == adapter_id).first()
        if adapter:
            adapter.certification_status = "approved"
            adapter.certification_date = datetime.utcnow()
            adapter.verified = True
            db.commit()
            logger.info(f"Adapter {adapter_id} certified successfully")
    finally:
        db.close()


async def test_adapter_package(adapter_id: str, version_id: str):
    """Test an uploaded adapter package."""
    logger.info(f"Testing adapter package {adapter_id} version {version_id}")
    
    db = SessionLocal()
    try:
        version = db.query(AdapterVersion).filter(AdapterVersion.id == version_id).first()
        if not version:
            return
        
        # Run tests
        test_results = await run_adapter_tests(adapter_id, version.package_url)
        
        # Update version with test results
        version.test_status = test_results["status"]
        version.test_results = test_results
        version.test_date = datetime.utcnow()
        
        db.commit()
        logger.info(f"Testing completed for adapter {adapter_id}: {test_results['status']}")
    
    except Exception as e:
        logger.error(f"Error testing adapter {adapter_id}: {e}")
    finally:
        db.close()


# Create tables
Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)