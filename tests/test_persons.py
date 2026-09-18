"""Unit tests: database sessions are mocked; PostgreSQL is not required."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.main import (
    create_person,
    delete_person,
    get_person,
    list_persons,
    update_person,
)
from app.models import Person
from app.schemas import PersonRequest


@pytest.fixture
def db():
    return Mock(spec=Session)


@pytest.fixture
def person():
    return Person(id=7, name="Ana", age=25, address="Madrid", work="Student")


def test_create_person_returns_location_and_empty_body(db):
    data = PersonRequest(name="Ana", age=25, address="Madrid", work="Student")
    db.refresh.side_effect = lambda record: setattr(record, "id", 7)

    response = create_person(data, db)

    assert response.status_code == 201
    assert response.body == b""
    assert response.headers["location"] == "/api/v1/persons/7"
    record = db.add.call_args.args[0]
    assert (record.name, record.age, record.address, record.work) == (
        "Ana", 25, "Madrid", "Student"
    )
    db.commit.assert_called_once()


def test_get_person_and_missing_id(db, person):
    db.get.return_value = person
    assert get_person(7, db) is person
    db.get.assert_called_with(Person, 7)

    db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        get_person(999, db)
    assert error.value.status_code == 404


def test_list_persons_including_empty_database(db, person):
    db.scalars.return_value.all.return_value = [person]
    assert list_persons(db) == [person]

    db.scalars.return_value.all.return_value = []
    assert list_persons(db) == []


def test_update_preserves_omitted_fields_and_rejects_missing_id(db, person):
    db.get.return_value = person

    updated = update_person(7, PersonRequest(name="Ana Maria", address="Barcelona"), db)

    assert updated.id == 7
    assert updated.name == "Ana Maria"
    assert updated.address == "Barcelona"
    assert updated.age == 25
    assert updated.work == "Student"
    db.commit.assert_called_once()

    db.reset_mock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        update_person(999, PersonRequest(name="Ana"), db)
    assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_delete_returns_empty_response_and_rejects_missing_id(db, person):
    db.get.return_value = person

    response = delete_person(7, db)

    assert response.status_code == 204
    assert response.body == b""
    db.delete.assert_called_once_with(person)
    db.commit.assert_called_once()

    db.reset_mock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        delete_person(999, db)
    assert error.value.status_code == 404
    db.delete.assert_not_called()
    db.commit.assert_not_called()
