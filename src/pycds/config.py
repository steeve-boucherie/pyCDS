"""Library settings."""
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# KEY MAPPING
class KeyMapper(BaseModel):
    """Mapper of dataset keys to standard aliases."""

    # Meta-config
    model_config = ConfigDict(frozen=True, extra='forbid')

    # ERA5 dataset dimensions
    t_dim: str = 'valid_time'

    # ERA5 dataset variables
    u_key: str = 'u100'  # U-componenent of the wind speed at 100m
    v_key: str = 'v100'  # V-componenent of the wind speed at 100m
    sp_key: str = 'sp'  # Surface pressure
    t2m_key: str = 't2m'  # Temperature at 2m
    d2m_key: str = 'd2m'  # Dewpoint temperature at 2m

    # Engineered dataset variables
    rho_key: str = 'rho'  # Air density
    ws_key: str = 'ws'  # Magnitude of the wind speed vector
    wd_key: str = 'wd'  # Wind orientation from North
    ws_corr_key: str = 'ws_corr'  # Density-corrected wind speed


# SETTINGS
class PyCDSSettings(BaseModel):
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
    default_query_vars: list[str] = Field(
        [
            '2m_dewpoint_temperature',
            'surface_pressure',
            '2m_temperature',
            '100m_u_component_of_wind',
            '100m_v_component_of_wind'
        ],
        min_length=1,
    )
    default_output_format: Literal['netcdf', 'csv'] = 'netcdf'
    default_query_start: str | None = None
    default_query_end: str | None = None


# GETTERS
@lru_cache(maxsize=None)
def get_mapper() -> KeyMapper:
    """Return the pyCDS settings."""
    # TODO: Add scan for user-defined options.
    return KeyMapper()


@lru_cache(maxsize=None)
def get_settings() -> PyCDSSettings:
    """Return the pyCDS settings."""
    # TODO: Add scan for user-defined options.
    return PyCDSSettings()
