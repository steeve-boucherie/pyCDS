"""Library settings."""
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict


# CLASS
class PyCDSConfig(BaseModel):
    """
    Class centralizing the project level settings.

    Attributes
    ----------
    default_vars: list[str]
        Variable to query by default.
    default_format: 'netcdf' | 'csv'
        Default output format of the query.
    default_start: str | None
        (Optional) Default start date of the queries in "yyyy-mm-dd" format. \
        Set to None to query data from the earliest available date.
    default_query_end: str | None
        (Optional) Default end date of the queries in "yyyy-mm-dd" format. \
        Set to None to query data from the latest available date.
    """

    # Meta-config
    model_config = ConfigDict(frozen=True, extra='forbid')

    # Query settings
    default_query_vars: list[str] = [
        '2m_dewpoint_temperature',
        'surface_pressure',
        '2m_temperature',
        '100m_u_component_of_wind',
        '100m_v_component_of_wind'
    ]
    default_output_format: Literal['netcdf', 'csv'] = 'netcdf'
    default_query_start: str | None = None
    default_query_end: str | None = None


# GETTER
@lru_cache
def get_settings() -> PyCDSConfig:
    """Return the pyCDS settings."""
    # TODO: Add scan for user-defined options.
    return PyCDSConfig()
