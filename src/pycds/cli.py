"""Script for ERA5 data download."""
import argparse
import logging
import os
import shutil
import zipfile
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd

from pydantic import BaseModel, ConfigDict, Field

import xarray as xr


# PACKAGE IMPORTS
from pycds.config import get_settings
from pycds.path import DOWNLOAD_FOLDER, TMP_FOLDER
from pycds.query import CDSQueryHandler


# LOGGER
logger = logging.getLogger(__name__)


# DEFAULT
NAME: str = 'ERA5Downloader'

# SETTINGS
# List of allowed additionnal variables
# ALLOWED_VARS = Literal['ws', 'wd', 'rho']


# ============================================================================
# CONFIGURATION
# ============================================================================
class ERA5DownloadConfig(BaseModel):
    """
    Configuration class for handling download of ERA5 data for existing wind farms.

    Attributes
    ----------
    input_root: Path
        The root folder to scan for finding wind farm folders (see farms below).
    farms: Dict[str, str | List[str] | None] | None
        The farms for which ERA5 data will be downloaded. The attribute must be \
        a dictionnary of the form form owner_name -> selected_farms listing \
        the selected farm for each owner. All farms and owner will be return \
        if None is passed. Returns all farm associated to on owner if \
        farm_dict[owner] is None.
    site_info_file: str
        The name of the site info file as it should appear in the wind \
        farm subolders.
    lat_col: str
        The name of the column containing the latitude coordinates of the turbines \
        as it should appear in the site info data frame.
    lon_col: str
        The name of the column containing the longitude coordinates of the turbines \
        as it should appear in the site info data frame.
    tmp_folder: Path
        The temporary folder where the downloaded files from ECMWF are saved \
        before being processed and split in monthly chunks.
    output_root: Path
        The root folder where the monthly ERA5 datasets will be saved. The resulting \
        folder tree will follow the same <OWNER>/<FARM> architecture as the input \
        folder tree.
    output_sub_dir: str
        The name of the folder containing the ERA5 data that will be created in \
        each <OWNER>/<FARM> subfolder.
    output_fname: str
        The file name for the ERA5 dataset.
    extra_query_vars: str | List[str]
        Extra variable(s) that should be queried in addition to the mandatory \
        channel. Refer to the ECMWF portal for a complete list of available \
        variables.
    query_start_date: str | None
        The start date of the query. Download from the first available date \
        if None is passed.
    query_end_date: str | None
        (Optional) The end date of the query. Download until the latest \
        available date if None is passed.
    extra_eng_vars: str | List[str]
        Engineered variable that should be added to the ERA5 data during the \
        processing of the raw dataset. These must be defined function of the \
        existing dataset variables.
    """

    # Config
    model_config = ConfigDict(frozen=True, extra='forbid')

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

    # Output settings
    # output_format: Literal['netcdf', 'csv'] | None = None
    tmp_folder: Path = TMP_FOLDER
    output_root: Path = DOWNLOAD_FOLDER
    output_subdir: str = 'era5'
    output_fname: str = 'era5.nc'
    # ------------------------------------------------------------------------

    # ------------------------------------------------------------------------
    # Data enrichment
    # ------------------------------------------------------------------------
    # extra_eng_vars: ALLOWED_VARS | list[ALLOWED_VARS] = list(get_args(ALLOWED_VARS))
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
    """

    # Class defaults
    CFG_CLS = ERA5DownloadConfig

    # Init
    def __init__(self, cfg: ERA5DownloadConfig):
        """Create class instance."""
        # Validate inputs
        self.validate_inputs(cfg)
        self._cfg = cfg

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
            # path=self.cfg.tmp_folder,
            lat=self.cfg.lat,
            lon=self.cfg.lon,
            variables=self.cfg.variables,
            t_start=self.cfg.start,
            t_end=self.cfg.end,
            output_format='netcdf'  # NOTE: We need it to be a CSV
        )
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
    # @cached_property
    # def default_builders(self) -> Mapping[str, transformer_like]:
        # """
        # Assemble the default builders from the configuration.

        # Returns
        # -------
        #     Mapping[str, transformer_like]
        # """
        # # Build
        # builders: Mapping[str, transformer_like] = {
        #     # Extra variables
        #     # Air density
        #     'rho': Era5AirDensityCalculator(
        #         var_name='rho',
        #         p_key='sp',
        #         t_key='t2m',
        #         dew_key='d2m',
        #     ),
        #     # Wind direction
        #     'wd': WDirCalculator(
        #         wd_key='wd',
        #         u_key='u100',
        #         v_key='v100',
        #         unit='deg',
        #     ),
        #     # Wind speed
        #     'ws': WSCalculator(
        #         ws_key='ws',
        #         u_key='u100',
        #         v_key='v100',
        #     ),
        #     # DTTM Elem (for saving)
        #     # Year
        #     'year': DttmElemAdder(
        #         t_dim='valid_time',
        #         elements=['year'],
        #     ),
        #     'month': DttmElemAdder(
        #         t_dim='valid_time',
        #         elements=['month'],
        #     ),
        # }

        # return builders

    @cached_property
    def query_handler(self) -> CDSQueryHandler:
        """Build the query handler object."""
        return CDSQueryHandler(get_settings())

    # Builders
    # def build_var_registry(self) -> VariableRegistry:
    #     """
    #     Build the VariableRegistry object.

    #     Returns
    #     -------
    #         Mapping[str, transformer_like]
    #     """
    #     return VariableRegistry(self.default_builders)
# ============================================================================


# ============================================================================
# UTILS
# ============================================================================
def load_archive(path: Path) -> xr.Dataset:
    """
    Exract data from the zip file downloaded from ECMWF and load into a dataset.

    Parameters
    ----------
    path: Path
        The name of the archive downloaded from the ECMWF.

    Returns
    -------
        Dataset
    """
    if not path.is_file():
        msg = f'Input path ({str(path)})is not a valid file. Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)

    with zipfile.ZipFile(path) as zip_ref:
        all_files = zip_ref.namelist()
        zip_ref.extractall(path.parent)

    nc_files = [f for f in all_files if f.endswith('.nc')]
    if nc_files == []:
        msg = 'No netCDF file (with ".nc" extension) found in the archive. ' \
              'Check the query output on the ECMWF portal.'
        logger.error(msg)
        raise ValueError(msg)

    if len(nc_files) != 1:
        logger.warning(
            'Multiple netCDF file (with ".nc" extension) were found in the '
            'archive.\nOnly the first file from the list will be loaded.\n'
            f'Please check this is the expected behavior.\nList of files: {nc_files}.'
        )

    with xr.open_dataset(path.parent / nc_files[0]) as ds:
        ds.load()

    return ds


# TODO: Move to a proper I/O submodule
def save_monthly_ds(
    ds: xr.Dataset,
    output_root: str | Path,
    out_fname: str
) -> None:
    """
    Given the dataset of ERA5 data, save the monthly chunk following the \
    <YEAR> / <MONTH> folder tree convention.

    Parameters
    ----------
    ds: xr.Dataset
        Input dataset
    output_root: str | Path
        Folder where to save the data.
    out_fname: str
        The name of the file.
    """
    def _drop_non_dims_coords(ds: xr.Dataset):
        """Drop the non-dimencoordinate before saving."""
        ds = ds.drop_vars([
            c for c in ds.coords
            if c not in ds.dims
        ])
        return ds

    # Add the year/month
    all_dims = list(ds.dims)
    if 'valid_time' not in all_dims:
        msg = 'Input dataset misses the time dimension (name= "valid_time").' \
              f'Dataset dimensions ares: {all_dims}. Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)

    times = pd.to_datetime(ds['valid_time'].data)
    ds = ds.assign_coords({
        'month': ('valid_time', times.month),
        'year': ('valid_time', times.year),
    })

    # Group and save
    groups = ds.groupby(['year', 'month'])
    for n, ((year, month), sub) in enumerate(groups):
        logger.info(
            f'{NAME}: Save data for year: {year}, month: {month} '
            f'({n + 1:3d} of {len(groups.groups.keys())})'
        )
        out_path = output_root / f'{year:4d}' / f'{month:02d}'
        if not out_path.exists():
            os.makedirs(out_path)
        _drop_non_dims_coords(sub).to_netcdf(out_path / out_fname)
# ============================================================================


# ============================================================================
# MAIN
# ============================================================================
def download_era5(cfg: ERA5DownloadConfig) -> None:
    """
    Download the ERA5 data and save the resulting datasets using the \
    year/month folder tree.

    Parameters
    ----------
    cfg: ERA5DownloadConfig
        Instance of configuration handler, containing \
        analysis specific settings.
    """
    # Model factory
    mf = ModelFactory(cfg)

    # Run query
    logger.info(f'{NAME}: Run query.')
    try:
        logger.info(f'{NAME}: Download data')
        tmp_path = cfg.tmp_folder / 'ecmwf_query.zip'
        mf.query_handler.download(tmp_path, **mf.query_params)

        # Enrich data
        logger.info(f'{NAME}: Extract from archive data.')
        ds = load_archive(tmp_path)

        # Save to year/month
        logger.info(f'{NAME}: Save to year month format.')
        save_monthly_ds(
            ds,
            cfg.output_root / cfg.output_subdir,
            cfg.output_fname
        )

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
        description=__file__.__doc__,
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
