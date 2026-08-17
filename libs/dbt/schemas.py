"""dbt process contracts."""

from libs.core.pydantic_base import NewmanLabsModel


class DBTCommandResult(NewmanLabsModel):
    """Result from one dbt Core command."""

    return_code: int
    stdout: str
    stderr: str
