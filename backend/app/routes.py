from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import schemas
from .database import SessionLocal
from .services import application_service

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/applications", response_model=schemas.Application)
def create_application(application: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    return application_service.create_application(db, application.dict())


@router.get("/applications", response_model=list[schemas.Application])
def get_applications(db: Session = Depends(get_db)):
    return application_service.list_applications(db)


@router.get("/applications/{application_id}", response_model=schemas.Application)
def get_application(application_id: int, db: Session = Depends(get_db)):
    application = application_service.get_application_by_id(db, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return application


@router.put("/applications/{application_id}", response_model=schemas.Application)
def update_application(application_id: int, update_data: schemas.ApplicationUpdate, db: Session = Depends(get_db)):
    application = application_service.get_application_by_id(db, application_id)

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return application_service.update_application(
        db,
        application,
        update_data.dict(exclude_unset=True),
    )


@router.delete("/applications/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db)):
    application = application_service.get_application_by_id(db, application_id)

    if application:
        application_service.delete_application(db, application)

    return {"message": "Application deleted"}
