from pydantic import BaseModel, ConfigDict, Field


class PersonRequest(BaseModel):
    name: str
    age: int | None = Field(default=None, ge=-(2**31), le=2**31 - 1)
    address: str | None = None
    work: str | None = None


class PersonResponse(PersonRequest):
    model_config = ConfigDict(from_attributes=True)

    id: int
