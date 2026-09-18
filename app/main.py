from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Person
from app.schemas import PersonRequest, PersonResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Person Service", version="1.0.0", lifespan=lifespan)
Database = Annotated[Session, Depends(get_db)]
PREFIX = "/api/v1/persons"


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = {
        ".".join(str(part) for part in error["loc"]): error["msg"]
        for error in exc.errors()
    }
    return JSONResponse(
        status_code=400, content={"message": "Invalid data", "errors": errors}
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


def find_person(person_id: int, db: Session) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@app.get(PREFIX, response_model=list[PersonResponse])
def list_persons(db: Database):
    return db.scalars(select(Person).order_by(Person.id)).all()


@app.post(PREFIX, status_code=201, response_class=Response)
def create_person(data: PersonRequest, db: Database):
    person = Person(**data.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return Response(status_code=201, headers={"Location": f"{PREFIX}/{person.id}"})


@app.get(PREFIX + "/{person_id}", response_model=PersonResponse)
def get_person(person_id: int, db: Database):
    return find_person(person_id, db)


@app.patch(PREFIX + "/{person_id}", response_model=PersonResponse)
def update_person(person_id: int, data: PersonRequest, db: Database):
    person = find_person(person_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person


@app.delete(PREFIX + "/{person_id}", status_code=204, response_class=Response)
def delete_person(person_id: int, db: Database):
    person = find_person(person_id, db)
    db.delete(person)
    db.commit()
    return Response(status_code=204)
