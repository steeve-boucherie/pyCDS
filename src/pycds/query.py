"""Class for handling queries of ERA5 data to the Copernicus Portal"""
import logging
import os
from datetime import timedelta
from pathlib import Path
from time import time
from functools import cached_property
from typing import Any, Literal

from ecmwf.datastores import Client

from xarray import Dataset


# PACKAGE IMPORTS
from pycds.config import PyCDSConfig, get_settings


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
    default_query_vars: list[str]
        Variable to query by default.
    default_output_format: 'netcdf' | 'csv'
        Default output format of the query.
    default_query_start: str | None
        (Optional) Default start date of the queries in "yyyy-mm-dd" format. \
        Set to None to query data from the earliest available date.
    default_query_end: str | None
        (Optional) Default end date of the queries in "yyyy-mm-dd" format. \
        Set to None to query data from the latest available date.

    Parameters
    ----------
    cfg: PyCDSConfig | None
        (Optional) Instance of pyCDS config for user-defined default.
    """

    # Class Constant
    # NOTE: These are fixed and thus should not be accessible for the user
    # to be modified.
    DATASET: str = 'reanalysis-era5-single-levels-timeseries'
    PREC: int = .25

    # Init
    def __init__(self, cfg: PyCDSConfig | None = None) -> None:
        """Instantiate class object."""
        cfg = cfg or get_settings()
        self.default_query_vars = cfg.default_query_vars
        self.default_output_format = cfg.default_output_format
        self.default_query_start = cfg.default_query_start
        self.default_query_end = cfg.default_query_end

    # Properties
    @cached_property
    def dataset_start(self) -> str:
        """return the begin date of the selected collection \
            dataset in yyyy-mm-dd format."""
        dttm = Client().get_collection(self.DATASET).begin_datetime
        return dttm.strftime(r'%Y-%m-%d')

    @cached_property
    def dataset_end(self) -> str:
        """return the end date of the selected collection \
            dataset in yyyy-mm-dd format."""
        # NOTE: Currently the end datetime is wrong in the metadata.
        # It returns at Dec 31st, 2024.
        # Instead we use the last updated date with a timedelta of -7 days for safety
        dttm = Client().get_collection(self.DATASET).updated_at
        dttm += timedelta(days=-7)

        # TODO: When the date is fixed. Remove the above and uncomment the below
        # dttm = Client.get_collection(self.dataset).end_datetime
        return dttm.strftime(r'%Y-%m-%d')

    # Method
    def download(
        self,
        path: str | Path,
        lat: float,
        lon: float,
        variables: str | list[str] | None = None,
        t_start: str | None = None,
        t_end: str | None = None,
        output_format: Literal['netcdf', 'csv'] | None = None,
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
        variables: str | list[str] | None = None
            Dataset variable(s) to be queried. Use the library default if \
            None ise passed.
        t_start: 'netcdf' | 'csv'
            Query start date in 'yyyy-mm-dd' format. Use the class default if \
            None ise passed.
        t_end: 'netcdf' | 'csv'
            Query end date in 'yyyy-mm-dd' format. Use the class default if \
            None ise passed.
        output_format: Literal['netcdf', 'csv'] | None
            Desired output format. Use the class default if None is passed.

        Returns
        -------
            Dataset
        """
        # Assign default
        variables = variables or self.default_query_vars
        t_start = t_start or self.default_query_start or self.dataset_start
        t_end = t_end or self.default_query_end or self.dataset_end
        output_format = output_format or self.default_output_format

        # Validate
        allowed = ['netcdf', 'csv']
        if output_format not in allowed:
            msg = f'Invalid output format: {output_format}. Allowed values are: ' \
                  f'{allowed}. Please check your inputs.'
            logger.error(msg)
            raise ValueError(msg)

        # Build the request
        request = {
            'variable': variables if isinstance(variables, list) else [variables],
            'location': {
                'latitude': round(lat / self.PREC) / self.PREC,
                'longitude': round(lon / self.PREC) / self.PREC,
            },
            'date': [f'{t_start}/{t_end}'],
            'data_format': output_format,
        }
        _display_request(request)

        # Execute
        client = Client()
        _create_parent(path)
        logger.info('Starting query.')
        t0 = time()
        client.retrieve(
            self.DATASET,
            request,
            target=path
        )
        logger.info(
            'Download successful !\n'
            f'Data save to: {(str(path))}.\n'
            f'Ellapsed time: {_format_time(time() - t0)}'
        )
