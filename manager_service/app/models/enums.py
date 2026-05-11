from enum import Enum


class JobStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskType(str, Enum):
    MAP = "MAP"
    REDUCE = "REDUCE"


class TaskStatus(str, Enum):
    IDLE = "IDLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    FAILED = "FAILED"
