"""
Custom exceptions for shiftcore.
"""


class ShiftCoreError(Exception):
    """Base exception for shiftcore."""

    pass


class ConstraintViolation(ShiftCoreError):
    """Raised when a scheduling constraint is violated."""

    def __init__(
        self,
        message: str,
        constraint_type: str = "",
        person_id: int = 0,
        date: str = "",
    ):
        super().__init__(message)
        self.constraint_type = constraint_type
        self.person_id = person_id
        self.date = date


class NoEligibleSubstitute(ShiftCoreError):
    """Raised when no eligible substitute can be found."""

    def __init__(
        self,
        message: str = "No eligible substitute found",
        date: str = "",
        shift_type: int = 0,
    ):
        super().__init__(message)
        self.date = date
        self.shift_type = shift_type


class NotificationFailed(ShiftCoreError):
    """Raised when notification delivery fails after retries."""

    def __init__(
        self, message: str, target_type: str = "", target_id: str = "", retries: int = 0
    ):
        super().__init__(message)
        self.target_type = target_type
        self.target_id = target_id
        self.retries = retries


class RotationError(ShiftCoreError):
    """Raised when rotation configuration is invalid."""

    def __init__(self, message: str, rotation_group_id: int = 0):
        super().__init__(message)
        self.rotation_group_id = rotation_group_id


class StorageError(ShiftCoreError):
    """Raised when database operation fails."""

    def __init__(self, message: str, operation: str = "", table: str = ""):
        super().__init__(message)
        self.operation = operation
        self.table = table


class ValidationError(ShiftCoreError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str = "", value: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
