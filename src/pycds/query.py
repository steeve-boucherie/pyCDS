"""Class for handling queries of ERA5 data to the Copernicus Portal"""
import logging
import os
from datetime import timedelta
from pathlib import Path
from time import time
from functools import cached_property
from typing import Any, Literal

# import cdsapi
from ecmwf.datastores import Client

from xarray import Dataset


# LOGGER
logger = logging.getLogger(__name__)


# UTILS
def _create_parent(path: str | Path) -> None:
    """
    Given a path to a file, verify its parent exists, and \
        create the folder tree if otherwise.

    Parameters
    ----------
    path: str | Path
        The path to validate.

    Returns
    -------
        Path
    """
    parent = Path(path).parent.resolve()
    if not parent.exists():
        os.makedirs(parent)


def _display_request(request: dict[str, Any]) -> None:
    """
    Given the request details, display it in the logger.

    Parameters
    ----------
    request: Dict[str, Any]
        Request to be displayed.
    """
    t_start, t_end = request['date'][0].split('/')
    msg = '\n=====================================================\n' \
          'Request Details\n' \
          '=====================================================\n' \
          f'Latitude: {request["location"]["latitude"]:.2f}°, '\
          f'Longitude: {request["location"]["longitude"]:.2f}°,\n' \
          f'Start date: {t_start}\n' \
          f'End date: {t_end}\n' \
          f'Selected variables: \n  - {"\n  - ".join(request["variable"])}\n' \
          '=====================================================\n'
    logger.info(msg)


def _format_time(ellapsed: float) -> str:
    """
    Given the ellapsed time, return a string to display in the logger.

    Parameters
    ----------
    ellapsed: float
        A float defining the ellapsed time.

    Returns
    -------
        str
    """
    hours, rem = divmod(ellapsed, 3600)
    mins, secs = divmod(rem, 60)

    return f'{int(hours):0>2d}:{int(mins):02d}:{secs:05.2f}'


# CLASS
class CDSQueryHandler():
    """
    Main class to handle query to the Climate Data Store (CDS).

    Attributes
    ----------
    variables: str | list[str]
        A string or list of strings listing the variable(s) to pull \
        as default when executing a query. This can be override in \
        the call of the `download` method.
    t_start: str
        A string defining the start date of the query, in YYYY-mm-dd format. \
        This can be override in the call of the `download` method.
    t_end: str
        A string defining the end date of the query, in YYYY-mm-dd format. \
        This can be override in the call of the `download` method.
    """
    DATASET: str = 'reanalysis-era5-single-levels-timeseries'
    VARIABLES: list[str] = [
        '2m_dewpoint_temperature',
        'surface_pressure',
        '2m_temperature',
        '100m_u_component_of_wind',
        '100m_v_component_of_wind'
    ]
    PREC: int = .25
    FRMT: Literal['netcdf', 'csv'] = 'netcdf'

    def __init__(
        self,
        variables: str | list[str] | None = None,
        t_start: str | None = None,
        t_end: str | None = None,
    ):
        """Instantiate class object."""
        self._variables = variables or self.VARIABLES
        self._t_start = t_start or self.begin_datetime
        self._t_end = t_end or self.end_datetime

    # Propery
    @property
    def variables(self) -> str | list[str]:
        """Return the selected list of variables."""
        return self._variables

    @cached_property
    def begin_datetime(self) -> str:
        """return the begin datetime of the selected collection \
            dataset in yyyy-mm-dd format."""
        dttm = Client().get_collection(self.DATASET).begin_datetime
        return dttm.strftime(r'%Y-%m-%d')

    @cached_property
    def end_datetime(self) -> str:
        """return the end datetime of the selected collection \
            dataset in yyyy-mm-dd format."""
        # NOTE: Currently the end datetime is wrong in the metadata.
        # It returns at Dec 31st, 2024.
        # Instead we use the last updated date with a timedelta of -7 days for safety
        dttm = Client().get_collection(self.DATASET).updated_at
        dttm += timedelta(days=-7)

        # TODO: When the date is fixed. Remove the above and uncomment the below
        # dttm = Client.get_collection(self.dataset).end_datetime
        return dttm.strftime(r'%Y-%m-%d')

    @property
    def t_start(self) -> str:
        """Return the selected start date of the query."""
        return self._t_start

    @property
    def t_end(self) -> str:
        """Return the selected start date of the query."""
        return self._t_end

    # Method
    def download(
        self,
        path: str | Path,
        lat: float,
        lon: float,
        variables: str | list[str] | None = None,
        t_start: str | None = None,
        t_end: str | None = None,
    ) -> Dataset:
        """
        Given the (lat, lon) coordinates, the list of select variables and \
        the time bounds, download data from the CDS and save to the specified \
        path

        Parameters
        ----------
        path: str | Path
            Path where to save the data on disk.
        lat: float
            Latitude coordinate of the selected location.
        lon: float
            Longitude coordinate of the selected location.
        variables: str | list[str]
            A string or list of strings listing the variable(s) to pull. \
            Use the class default if None is passed.
        t_start: str | None
            A string defining the start date of the query, in YYYY-mm-dd format. \
            Use the class default if None is passed.
        t_end: str | None
            A string defining the end date of the query, in YYYY-mm-dd format. \
            Use the class default if None is passed.

        Returns
        -------
            Dataset
        """
        # Assign default
        variables = variables or self.variables
        t_start = t_start or self.t_start
        t_end = t_end or self.t_end

        # Build the request
        request = {
            'variable': variables if isinstance(variables, list) else [variables],
            'location': {
                'latitude': round(lat / self.PREC) / self.PREC,
                'longitude': round(lon / self.PREC) / self.PREC,
            },
            'date': [f'{t_start}/{t_end}'],
            'data_format': self.FRMT,
        }
        _display_request(request)

        # Execute
        client = Client()
        _create_parent(path)
        logger.info('Starting query.')
        t0 = time()
        client.retrieve(
            self.dataset,
            request,
            target=path
        )
        logger.info(
            'Download successful !\n'
            f'Data save to: {(str(path))}.\n'
            f'Ellapsed time: {_format_time(time() - t0)}'
        )
