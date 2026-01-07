"""
Response models and custom exception classes
"""
from typing import Optional, Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar('T')


class Result(BaseModel, Generic[T]):
    """Response model"""
    code: int = Field(description="Status code, 0 for success, non-0 for failure")
    message: str = Field(description="Return message")
    data: Optional[T] = Field(default=None, description="Return data")

    @classmethod
    def success(cls, data: Optional[T] = None, message: str = "Operation successful") -> "Result[T]":
        """Success response"""
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: Optional[T] = None) -> "Result[T]":
        """Error response"""
        return cls(code=code, message=message, data=data)


class BizError(Exception):
    """Custom business exception"""
    
    def __init__(self, code: int, message: str):
        """
        Initialize business exception
        
        Args:
            code: Error code
            message: Error message
        """
        self.code = code
        self.message = message
        super().__init__(message)

    def __str__(self):
        return f"BizError(code={self.code}, message={self.message})"

    def __repr__(self):
        return self.__str__()
