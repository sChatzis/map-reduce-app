from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "plain_user"


class UserStatus(str, Enum):
    PENDING_APPROVAL = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
