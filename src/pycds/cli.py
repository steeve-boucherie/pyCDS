"""Command line script for downloading ERA5 timeseries."""
import argparse
import logging
import sys
import tempfile
from functools import cached_property
from pathlib import Path
from typing import get_args

from pydantic import ValidationError, validate_call


# PACKAGE IMPORTS
from pycds.config import (
    AllowedDttm,
    Lat,
    Lon,
    PyCDSSettings,
    SplitFreq,
    get_mapper,
    get_settings
)
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
)
from pycds.variable_registry import VariableRegistry


# LOGGER
logger = logging.getLogger(__name__)


# DEFAULT
NAME: str = 'pycds'


# =========================================================================
# MODEL FACTORY
# =========================================================================
class ModelFactory():
    """
    Factory class for handling ERA5 data download.

    Parameters
    ----------
    params: PyCDSSettings
        Dictionnary of parsed input.

    Attributes
    ----------
    _cfg: PyCDSSettings
        Instance of configuration handler, request specific settings.
    mapper: KeyMapper
        Custom mapper from aliases to dataset keys.
    """

    # Init
    def __init__(self, settings: PyCDSSettings) -> None:
        """Create class instance."""
        self._settings = settings
        # System
        self.mapper = get_mapper()

    # Properties
    @property
    def name(self) -> str:
        """Return the class name."""
        return self.__class__.__name__

    @property
    def settings(self) -> PyCDSSettings:
        """Access the config object."""
        return self._settings

    @property
    def eng_vars(self) -> list[str]:
        """Return the list of engineered variables to append to the dataset."""
        out = [
            getattr(self.mapper, f'{alias}_key')
            for alias in self.settings.eng_variables
        ]
        return out

    @property
    def output_path(self) -> Path:
        """Return the path to the folder where the data will be saved."""
        return self.settings.download_folder / (self.settings.output_subdir or '')

    @property
    def group_coords(self) -> AllowedDttm | list[AllowedDttm] | None:
        """Return the grouping coordinate(s) for splitting the dataset \
            in time chunk."""
        if self.settings.split_frequency is not None:
            out = {
                'yearly': 'year',
                'monthly': ['year', 'month']
            }[self.settings.split_frequency]
            return out

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
                mapper=self.mapper,
            ),
            # Wind speed
            self.mapper.ws_key: WSCalculator(
                mapper=self.mapper
            ),
            # Density-correct wind speed
            self.mapper.ws_corr_key: WSDensityCorrector(
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
# =========================================================================


# =========================================================================
# MAIN
# =========================================================================
@validate_call
def download_era5(
    lat: Lat,
    lon: Lon,
    settings: PyCDSSettings
) -> None:
    """
    Download the ERA5 data and save the resulting datasets in the \
    user-defined directories.

    Parameters
    ----------
    lat: float
        Latitude coordinate of the selected location.
    lon: float
        Longitude coordinate of the selected location.
    settings: PyCDSSettings
        Custom query settings.
    """
    # Model factory
    mf = ModelFactory(settings)
    var_reg = mf.build_var_registry()

    # Run query
    logger.info(f'{NAME}: Run query.')
    temp_folder = mf.settings.temp_folder
    if temp_folder is not None:
        Path(temp_folder).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pycds-', dir=temp_folder) as tmp:
        logger.info(f'{NAME}: Download data')
        tmp_path = Path(tmp) / 'ecmwf_query.zip'
        mf.query_handler.download(lat, lon, tmp_path)

        # Extract data from archive data
        logger.info(f'{NAME}: Extract from archive data.')
        ds = load_archive(tmp_path)

        # Entich dataset
        logger.info(f'{NAME}: Enrich dataset')
        ds = var_reg.ensure_flags(ds, mf.eng_vars)

        # Save to year/month
        logger.info(f'{NAME}: Save data.')
        if mf.settings.split_frequency is not None:
            ds = add_dttm(ds, mf.mapper.t_dim, mf.group_coords)
            save_groups(
                ds.groupby(mf.group_coords),
                mf.output_path,
                mf.settings.output_fname
            )
        else:
            save_ds(ds, mf.output_path, mf.settings.output_fname)
# =========================================================================


# =========================================================================
# COMMAND LINE EXECUTION
# =========================================================================
# PARSER
def _parse_arguments() -> argparse.Namespace:
    """Parse user inputs."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description=__doc__,
        epilog='Run with code using `pycds --[OPTION] [VALUE]`',
    )

    # Mandatory
    # Query latitude and longitude
    parser.add_argument(
        '--lat',
        type=float,
        help='Latitude coordinate of the query in degrees (decimal format).'
    )
    parser.add_argument(
        '--lon',
        type=float,
        help='Longitude coordinate of the query degrees (decimal format).'
    )
    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Print the effective settings and exit (no download).'
    )

    # Optional overrides: only forwarded if type by the user
    overrides: dict[str, dict] = {
        'query_start': dict(
            type=str,
            help='Start date of the query in yyyy-mm-dd format.'
        ),
        'query_end': dict(
            type=str,
            help='End date of the query in yyyy-mm-dd format.'
        ),
        'output_subdir': dict(
            type=str,
            help='Sub-folder where to save the data in the output root.'
        ),
        'split_frequency': dict(
            type=str,
            choices=get_args(SplitFreq),
            help='The frequency at which the result should be split (yearly or monthly).'
        )
    }
    for field, kwargs in overrides.items():
        parser.add_argument(
            f'--{field}'.replace('_', '-'),
            dest=field,
            default=argparse.SUPPRESS,
            **kwargs
        )

    args = parser.parse_args()
    if not args.show_config and (args.lat is None or args.lon is None):
        parser.error('--lat and --lon are required unless --show-config is used')

    return args


def main() -> None:
    """Run the command line execution."""
    # Set up logger
    logging.basicConfig(
        format=(
            '[%(asctime)s %(filename)s->%(funcName)s():%(lineno)s] '
            '%(levelname)s: %(message)s'
        ),
        level=logging.INFO,
        datefmt='%H:%M:%S'
    )

    # Parse argument
    logger.info(f'{NAME}: Parse user inputs.')
    params = vars(_parse_arguments())

    # Run
    show_config = params.pop('show_config')
    lat, lon = params.pop('lat'), params.pop('lon')
    logger.info(f'{NAME}: Downoading era5 for lat = {lat:.5f}, lon = {lon:.5f}.')
    try:
        settings = get_settings(params)
        if show_config:
            print(settings.model_dump_json(indent=2))
            return
        download_era5(lat, lon, settings)

    except ValidationError as e:
        logger.error(f'{NAME}: Invalid inputs or settings:\n{e}')
        sys.exit(2)

    except Exception:
        logger.exception('Download failed. See traceback above.')
        sys.exit(1)

    # Closing
    logger.info(f'{NAME}: Success !')


# EXECUTION
if __name__ == '__main__':
    main()
# =========================================================================
