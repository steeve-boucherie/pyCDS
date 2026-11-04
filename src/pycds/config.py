"""Library settings."""
import os
import tomllib
from datetime import date
from pathlib import Path
from typing import Any, Annotated, Literal, get_args

from platformdirs import user_config_path

from pydantic import BaseModel, ConfigDict, Field, model_validator


# TYPES
AllowedDttm = Literal['month', 'year']
AllowedVars = Literal['ws', 'wd', 'rho', 'ws_corr']
Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]
OutputFormats = Literal['netcdf', 'csv']
SplitFreq = Literal['yearly', 'monthly']


# DEFAULT
USER_CONFIG_PATH = user_config_path('pycds')  # NOTE: Declare here for re-use
OUTPUT_FORMAT: str = 'netcdf'
GENESIS: date = date(1940, 1, 1)


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
    TODO: Update docstring
    tmp_folder: Path
        The path to the temporary folder where the downloaded archives \
        will be saved for extraction.
    download_folder: Path
        The path to the folder where the consolidated dataset will be saved.
    output_subdir: str | None
        (Optional) The subfolder that will be created in download_folder and where \
        the data will be saved.
    output_fname: str
        The name of the file containing the downloaded data as it will be saved.
    split_frequency: 'monthly' | 'yearly' | None
        (Optional) The frequency for splitting the downloaded data into smaller \
        time chunks for saving. If "yearly", save the each yearly chunk in a \
        subfolder, "YYYY", whose name is the corresponding year. If "month", \
        save each monthly chunk in a subfolder tree, "YYYY/mm", with name defined \
        by the corresponding year and month.
    query_start: str | None
        (Optional) The query start date in yyyy-mm-dd format. \
        Use the library default if None is passed.
    query_end: str | None
        (Optional) The query end date in yyyy-mm-dd format. \
        Use the library default if None is passed.
    variable: list[str] | None
        (Optional) The variable(s) to be queried . \
        Use the library default if None is passed.
    eng_vars: str | list[str] | None
        (Optional) The additional variables that must be appended to the \
        downloaded as a post-processing step. These must be valid variables \
        with a builder associated to it.
    """

    # Meta-config
    model_config = ConfigDict(frozen=True, extra='forbid')

    # I/O
    download_folder: Path = Path.home() / 'pycds-downloads'
    temp_folder: Path | None = None
    output_subdir: str | None = None
    output_fname: str = 'era5.nc'
    split_frequency: SplitFreq | None = None

    # Query settings
    variables: list[str] = Field(
        [
            '2m_dewpoint_temperature',
            'surface_pressure',
            '2m_temperature',
            '100m_u_component_of_wind',
            '100m_v_component_of_wind'
        ],
        min_length=1,
    )

    query_start: date | None = None
    query_end: date | None = None

    # Data enrichment
    eng_variables: list[AllowedVars] = list(get_args(AllowedVars))

    # Validator
    @model_validator(mode='after')
    def end_must_be_later_than_start(self) -> 'PyCDSSettings':
        """
        Verify that the query end date (if defined) is later than the query \
        start date (if defined), and raise ValueError if otherwise.

        Returns
        -------
            PyCDSSettings

        Raises
        ------
            ValueError
        """
        min_date = self.query_start or GENESIS
        if self.query_end is not None and self.query_end < min_date:
            raise ValueError(
                'Attempt to specify a query end date earlier than the query '
                f'start. Set query end date: {self.query_end}.'
                f'Query start date: {min_date}). '
                'Please check your inputs.'
            )
        return self


# UTILS
def _read_toml(path: Path, table: str | None = None) -> dict[str, Any]:
    """
    Given the path to a .toml file read the its content and return \
    the data.

    Parameters
    ----------
    path: Path
        Path to the .toml file.
    table: str | None
        (Optional) The name of the table to return data for.

    Returns
    -------
        dict[str, Any]
    """
    with path.open('rb') as f:
        data = tomllib.load(f)
    if table:
        # NOTE: We read from the pyproject.toml
        data = data.get('tool', {}).get(table, {})
    for key in ['download_folder', 'temp_folder']:
        if key in data:
            # NOTE: Magic to define relative path from the folder containing
            # the .toml file. This is useful for project-level settings with
            # a dedicated folder in <ROOT>/data.
            p = Path(data[key]).expanduser()
            data[key] = p if p.is_absolute() else path.parent / p
    return data


def _project_config(start: Path) -> dict[str, Any]:
    """
    Given the current working directory, scan for user-defined settings in \
    the available .toml file.

    Parameters
    ----------
    start: Path
        Start where to look for .toml files. The parent tree is also tested.

    Returns
    -------
        dict[str, Any]
    """
    for d in (start, *start.parents):
        # NOTE: Stop on first find
        if (f := d / 'pycds.toml').is_file():
            return _read_toml(f)
        if (f := d / 'pyproject.toml').is_file():
            if data := _read_toml(f, table='pycds'):
                return data
    return {}


def _env_config() -> dict[str, Any]:
    """
    Load user-defined from environment variables.

    Returns
    -------
        dict[str, Any]
    """
    def _env_var(key: str) -> str | None:
        return os.getenv(f'PYCDS_{key.upper()}')

    out: dict = {}
    # Test folders
    for key in ['download_folder', 'temp_folder']:
        if v := _env_var(key):
            out[key] = Path(v).expanduser()
    # Test variable lists
    for key in ['variables', 'eng_variables']:
        if v := _env_var(key):
            out[key] = [s.strip() for s in v.split(',')]
    # Any other settings
    keys = [
        'output_subdir',
        'output_fname',
        'split_frequency',
        'query_start',
        'query_end',
    ]
    for key in keys:
        if v := _env_var(key):
            out[key] = v

    return out


# GETTERS
def get_mapper() -> KeyMapper:
    """Return the pyCDS settings."""
    # TODO: Add scan for user-defined options.
    return KeyMapper()


def get_settings(overrides: dict[str, Any] | None = None) -> PyCDSSettings:
    """Return the pyCDS settings."""
    merged: dict = {}
    user_file = USER_CONFIG_PATH / 'config.toml'
    layers = [
        # User settings
        _read_toml(user_file) if user_file.is_file() else {},
        # Project settings
        _project_config(Path.cwd()),
        # Environment var
        _env_config(),
        {key: val for key, val in (overrides or {}).items() if val is not None}
    ]
    for layer in layers:
        merged.update(layer)
    return PyCDSSettings(**merged)
