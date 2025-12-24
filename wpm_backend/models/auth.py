"""Pydantic models for authentication-related data structures."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request model for login endpoint."""

    username: str = Field(..., min_length=1, description="User's login username")
    password: str = Field(..., min_length=1, description="User's login password")


class LoginResponse(BaseModel):
    """Response model for login endpoint."""

    access_token: str = Field(..., description="JWT access token for subsequent API requests")
    token_type: str = Field(default="bearer", description="Type of authentication token")

