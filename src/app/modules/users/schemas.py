from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Annotated
import uuid


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseSchema):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=20)]


class UserCreateResponse(BaseSchema):
    id: uuid.UUID
    name: str
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
