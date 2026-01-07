"""
MongoDB User model (using Pydantic for validation).
"""
from pydantic import BaseModel, Field, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from typing import Optional, Any
from datetime import datetime
from bson import ObjectId


class PyObjectId(ObjectId):
    """
    Custom ObjectId type for Pydantic v2.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> Any:
        from pydantic_core import core_schema
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ])
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: Any, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(str)


class User(BaseModel):
    """
    User model for MongoDB (Pydantic schema only, not used directly).
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    username: str
    email: Optional[str] = None
    password_hash: Optional[str] = None
    auth_provider: str = "password"  # "password" or "google"
    google_sub: Optional[str] = None  # Google subject ID
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "is_active": True
            }
        }


class UserIntegration(BaseModel):
    """
    User integration details (e.g., Gmail).
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    provider: str  # e.g., "gmail"
    access_token: str  # Encrypted
    refresh_token: Optional[str] = None  # Encrypted
    expires_at: datetime
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    email: Optional[str] = None  # The connected email address
    sync_status: str = "connected"  # "connected", "syncing", "error"
    last_sync_at: Optional[datetime] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class EmailSource(BaseModel):
    """
    Metadata for an email imported into RAG.
    """
    email_id: str
    thread_id: str
    subject: str
    sender: str  # "From" field
    date: datetime
    received_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

