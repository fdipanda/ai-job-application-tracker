from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/applications", response_model=schemas.Application)
def create_application(application: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    db_application = models.Application(**application.dict())
    db.add(db_application)
    db.commit()
    db.refresh(db_application)
    return db_application


@router.get("/applications", response_model=list[schemas.Application])
def get_applications(db: Session = Depends(get_db)):
    return db.query(models.Application).all()


@router.get("/applications/{application_id}", response_model=schemas.Application)
def get_application(application_id: int, db: Session = Depends(get_db)):
    return db.query(models.Application).filter(models.Application.id == application_id).first()


@router.put("/applications/{application_id}", response_model=schemas.Application)
def update_application(application_id: int, update_data: schemas.ApplicationUpdate, db: Session = Depends(get_db)):
    application = db.query(models.Application).filter(models.Application.id == application_id).first()

    if not application:
        return {"error": "Application not found"}

    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(application, key, value)

    db.commit()
    db.refresh(application)

    return application


@router.delete("/applications/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db)):
    application = db.query(models.Application).filter(models.Application.id == application_id).first()

    if application:
        db.delete(application)
        db.commit()

    return {"message": "Application deleted"}