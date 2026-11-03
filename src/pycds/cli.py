"""Command line script for downloading ERA5 timeseries."""
import argparse
import logging
import shutil
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field


# PACKAGE IMPORTS
from pycds.config import KeyMapper, PyCDSSettings, get_mapper, get_settings
from pycds.path import DOWNLOAD_FOLDER, TMP_FOLDER
from pycds.query import CDSQueryHandler
from pycds.transform import (
    DataTransformerInterface,
    Era5AirDensityCalculator,
    WDirCalculator,
    WSCalculator,
    WSDensityCorrector,
)
from pycds.utils import (
    add_dttm,
    load_archive,
    save_ds,
    save_groups,
    to_list,
)
from pycds.variable_registry import VariableRegistry


# LOGGER
logger = logging.getLogger(__name__)


# DEFAULT
NAME: str = 'ERA5Downloader'

# SETTINGS
# List of allowed additionnal variables
ALLOWED_VARS = Literal['ws', 'wd', 'rho', 'ws_corr']
ALLOWED_DTTM = Literal['month', 'year']


# ============================================================================
# CONFIGURATION
# ============================================================================
class ERA5DownloadConfig(BaseModel):
    """
    Configuration class for handling download of ERA5 data for existing wind farms.

    Attributes
    ----------
    tmp_folder: Path
        The path to the temporary folder where the downloaded archive \
        will be saved before extraction.
    output_root: Path
        The path to the folder where the consolidated dataset will be saved.
    output_subdir: str
        The subfolder that will be created in output_root and where the data \
        will be saved. Default is "era5".
    output_fname: str
        The name of the file containing the downloaded data as it will be saved.
    split_frequency: 'monthly' | 'yearly' | None
        (Optional) The frequency for splitting the downloaded data into smaller \
        time chunks for saving. If "yearly", save the each yearly chunk in a \
        subfolder, "YYYY", whose name is the corresponding year. If "month", \
        save each monthly chunk in a subfolder tree, "YYYY/mm", with name defined \
        by the corresponding year and month.
    lat: float
        The latitude coordinate of the query in degress. This must be \
        in [-90°, 90°] interval.
    lon: float
        The longitude coordinate of the query in degress. This must be \
        in [-180°, 180°] interval.
    start: str | None
        (Optional) The query start date in yyyy-mm-dd format. \
        Use the library default if None is passed.
    end: str | None
        (Optional) The query end date in yyyy-mm-dd format. \
        Use the library default if None is passed.
    variable: list[str] | None
        (Optional) The variable(s) to be queried . \
        Use the library default if None is passed.
    eng_vars: str | list[str] | None
        (Optional) The additional variables that must be appended to the \
        downloaded as a post-processing step. These must be valid variables \
        with a builder associated to it.
    wd_unit: 'deg' | 'rad'
        The unit in which the wind direction should be calculated. This is \
        used only if "wd" is passed in "eng_vars".
    rho_ref: float | None
        The reference air density for wind speed correction. This is used \
        only if "ws_corr" is passed in "eng_vars". Use the library default \
        if None is passed.
    """

    # Config
    model_config = ConfigDict(frozen=True, extra='forbid')

    # ------------------------------------------------------------------------
    # I/O settings
    # ------------------------------------------------------------------------
    # Split results
    split_frequency: Literal['monthly', 'yearly'] | None = None

    # Output settings
    tmp_folder: Path = TMP_FOLDER
    output_root: Path = DOWNLOAD_FOLDER
    output_subdir: str = 'era5'
    output_fname: str = 'era5.nc'
    # ------------------------------------------------------------------------

    # ------------------------------------------------------------------------
    # Query settings
    # ------------------------------------------------------------------------
    # lat/lon
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    # Query dates
    start: str | None = None
    end: str | None = None

    # Queried variables
    variables: str | list[str] | None = None
    # ------------------------------------------------------------------------

    # ------------------------------------------------------------------------
    # Data enrichment
    # ------------------------------------------------------------------------
    # Engineered variables
    # TODO: Add validator
    eng_vars: ALLOWED_VARS | list[ALLOWED_VARS] | None = list(get_args(ALLOWED_VARS))

    # Wind direction unit
    wd_unit: Literal['deg', 'rad'] = 'deg'

    # Reference air density (leave None to use default)
    rho_ref: float | None = None
    # ------------------------------------------------------------------------
# ============================================================================


# ============================================================================
# MODEL FACTORY
# ============================================================================
class ModelFactory():
    """
    Model builder for ERA5 data download.

    Attributes
    ----------
    cfg: ERA5DownloadConfig
        Instance of configuration handler, containing \
        analysis specific settings.
    settings: KeyMapper | None
        (Optional) Custom library settings. Use the \
        package default if None is passed.
    mapper: KeyMapper | None
        (Optional) Custom mapper from aliases to dataset keys. Use the \
        package default if None is passed.
    """

    # Class defaults
    CFG_CLS = ERA5DownloadConfig

    # Init
    def __init__(
        self,
        cfg: ERA5DownloadConfig,
        settings: PyCDSSettings | None = None,
        mapper: KeyMapper | None = None,
    ) -> None:
        """Create class instance."""
        # Validate inputs
        self.validate_inputs(cfg)
        self._cfg = cfg

        # System
        self.settings = settings if settings is not None else get_settings()
        self.mapper = mapper if mapper is not None else get_mapper()

    # Properties
    @property
    def name(self) -> str:
        """Return the class name."""
        return self.__class__.__name__

    @property
    def cfg(self) -> ERA5DownloadConfig:
        """Access the config object."""
        return self._cfg

    @property
    def required_settings(self) -> list[str]:
        """Return the list of settins that must be defined in the CFG"""
        return self.CFG_CLS.model_fields.keys()

    @property
    def query_params(self) -> dict[str, Any]:
        """Return the query parameters."""
        out = dict(
            lat=self.cfg.lat,
            lon=self.cfg.lon,
            variables=self.cfg.variables,
            t_start=self.cfg.start,
            t_end=self.cfg.end,
            output_format='netcdf'  # NOTE: We need it to be a NetCDF
        )
        return out

    @property
    def eng_vars(self) -> list[str]:
        """Return the list of engineered variables to append to the dataset."""
        out = [
            self.mapper.__getattribute__(f'{alias}_key')
            for alias in to_list(self.cfg.eng_vars)
        ]
        return out

    @property
    def output_path(self) -> Path:
        """Return the path to the folder where the data will be saved."""
        return self.cfg.output_root / self.cfg.output_subdir

    @property
    def group_coords(self) -> ALLOWED_DTTM | list[ALLOWED_DTTM]:
        """Return the grouping coordinate(s) for splitting the dataset \
            in time chunk."""
        out = {
            'yearly': 'year',
            'monthly': ['year', 'month']
        }[self.cfg.split_frequency]
        return out

    # Utils
    def validate_inputs(self, cfg: ERA5DownloadConfig) -> None:
        """
        Validate that the given config object, contains the required settings \
        and raise a ValueError if otherwise.

        Parameters
        ----------
        cfg: Config
            Configuration handler to be tested.

        Raises
        ------
            ValueError
        """
        missing = set(self.required_settings).difference(cfg.__class__.model_fields.keys())
        if missing != set():
            msg = f'{self.name}: The configuration object is missing required settings.\n' \
                  f'Missing settings: {missing}.\nPlease check your inputs.'
            logger.error(msg)
            raise ValueError(msg)

    # Model
    @cached_property
    def default_builders(self) -> dict[str, DataTransformerInterface]:
        """
        Assemble the default builders from the configuration.

        Returns
        -------
            dict[str, transformer_like]
        """
        # Build
        builders: dict[str, DataTransformerInterface] = {
            # Extra variables
            # Air density
            self.mapper.rho_key: Era5AirDensityCalculator(
                mapper=self.mapper
            ),
            # Wind direction
            self.mapper.wd_key: WDirCalculator(
                unit=self.cfg.wd_unit,
                mapper=self.mapper,
            ),
            # Wind speed
            self.mapper.ws_key: WSCalculator(
                mapper=self.mapper
            ),
            # Density-correct wind speed
            self.mapper.ws_corr_key: WSDensityCorrector(
                rho_ref=self.cfg.rho_ref,
                mapper=self.mapper
            )
        }
        return builders

    @cached_property
    def query_handler(self) -> CDSQueryHandler:
        """Build the query handler object."""
        return CDSQueryHandler(self.settings)

    # Builders
    def build_var_registry(self) -> VariableRegistry:
        """
        Build the VariableRegistry object.

        Returns
        -------
            VariableRegistry
        """
        return VariableRegistry(self.default_builders)
# ============================================================================


# ============================================================================
# UTILS
# ============================================================================
# ============================================================================


# ============================================================================
# MAIN
# ============================================================================
def download_era5(
    cfg: ERA5DownloadConfig,
    settings: PyCDSSettings | None = None,
    mapper: KeyMapper | None = None,
) -> None:
    """
    Download the ERA5 data and save the resulting datasets using the \
    year/month folder tree.

    Parameters
    ----------
    cfg: ERA5DownloadConfig
        Instance of configuration handler, containing \
        analysis specific settings.
    settings: KeyMapper | None
        (Optional) Custom library settings. Use the \
        package default if None is passed.
    mapper: KeyMapper | None
        (Optional) Custom mapper from aliases to dataset keys. Use the \
        package default if None is passed.
    """
    # Model factory
    mf = ModelFactory(cfg, settings, mapper)
    var_reg = mf.build_var_registry()

    # Run query
    logger.info(f'{NAME}: Run query.')
    try:
        logger.info(f'{NAME}: Download data')
        tmp_path = cfg.tmp_folder / 'ecmwf_query.zip'
        mf.query_handler.download(tmp_path, **mf.query_params)

        # Extract data from archive data
        logger.info(f'{NAME}: Extract from archive data.')
        ds = load_archive(tmp_path)

        # Entich dataset
        logger.info(f'{NAME}: Enrich dataset')
        ds = var_reg.ensure_flags(ds, mf.eng_vars)

        # Save to year/month
        logger.info(f'{NAME}: Save data.')
        if mf.cfg.split_frequency is not None:
            ds = add_dttm(ds, mf.mapper.t_dim, mf.group_coords)
            save_groups(
                ds.groupby(mf.group_coords),
                mf.output_path,
                mf.cfg.output_fname
            )
        else:
            save_ds(ds, mf.output_path, mf.cfg.output_fname)

    except Exception:
        logger.exception(f'{NAME}: Failed to download data. Check terminal for more details')
        return

    # Clear temp folder
    if cfg.tmp_folder.is_dir():
        logger.info(f'{NAME}: Clear temporay folder.')
        shutil.rmtree(cfg.tmp_folder)
# ============================================================================


# ============================================================================
# COMMAND LINE EXECUTION
# ============================================================================
# PARSER
def _parse_arguments() -> argparse.Namespace:
    """Parse user inputs."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description=__doc__,
        epilog='Run with code using uv run <path_to_file> --[OPTION] [VALUE]',
    )

    # Get all fields
    fields = ERA5DownloadConfig.model_fields

    # Query latitude and longitude
    field = 'lat'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        type=float,
        help='Latitude coordinate of the query in decimal format.'
    )
    field = 'lon'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        type=float,
        help='Longitude coordinate of the query in decimal format.'
    )

    # Query start and end dates
    field = 'start'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        type=str,
        help='Start date of the query in yyyy-mm-dd format.'
    )
    field = 'end'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        type=str,
        help='End date of the query in yyyy-mm-dd format.'
    )

    # Output subdir
    field = 'output_subdir'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        type=str,
        help='Sub-folder where to save the data in the output root.'
    )

    # Split results
    field = 'split_frequency'
    parser.add_argument(
        f'--{field}'.replace('_', '-'),
        required=fields[field].is_required(),
        default=fields[field].default,
        dest=field,
        choices=get_args(fields[field].annotation),
        type=str,
        help='The frequency at which the result should be split (yearly or monthly).'
    )

    return parser.parse_args()


def main() -> None:
    """Run the command line execution."""
    # Set up logger
    logging.basicConfig(
        format=(
            '[%(asctime)s %(filename)s->%(funcName)s():%(lineno)s] '
            '%(levelname)s: %(message)s'
        ),
        level=logging.INFO,
        datefmt='%I:%M:%S'
    )

    # Parse argument
    logger.info(f'{NAME}: Parse user inputs.')
    args = _parse_arguments()

    # Run
    logger.info(f'{NAME}: Download ERA5 data for all sites.')
    download_era5(ERA5DownloadConfig(**vars(args)))

    # Closing
    logger.info(f'{NAME}: Success !')


# EXECUTION
if __name__ == '__main__':
    main()
# ============================================================================
