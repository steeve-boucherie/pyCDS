"""Class for handling queries of ERA5 data to the Copernicus Portal"""
import logging
from datetime import date, timedelta
from pathlib import Path
from time import time
from functools import cached_property
from typing import Any

from ecmwf.datastores import Client

from pydantic import validate_call


# PACKAGE IMPORTS
from pycds.config import (
    Lat,
    Lon,
    PyCDSSettings,
    OutputFormats,
    get_settings,
    OUTPUT_FORMAT
)
from pycds.utils import to_list


# LOGGER
logger = logging.getLogger(__name__)


# UTILS
def _display_request(request: dict[str, Any]) -> None:
    """
    Given the request details, display it in the logger.

    Parameters
    ----------
    request: Dict[str, Any]
        Request to be displayed.
    """
    t_start, t_end = request['date'][0].split('/')
    var_list = '\n  - '.join(request['variable'])
    msg = '\n=====================================================\n' \
          'Request Details\n' \
          '=====================================================\n' \
          f'Latitude: {request["location"]["latitude"]:.2f}°, '\
          f'Longitude: {request["location"]["longitude"]:.2f}°,\n' \
          f'Start date: {t_start}\n' \
          f'End date: {t_end}\n' \
          f'Selected variables: \n  - {var_list}\n' \
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

    Parameters
    ----------
    settings: PyCDSSettings | None
        (Optional) Instance of pyCDS config for user-defined settings.

    Attributes
    ----------
    settings: PyCDSSettings
        Intance of pyCDS query settings.
    """

    # Class Constant
    # NOTE: These are fixed and thus should not be accessible for the user
    # to be modified.
    DATASET: str = 'reanalysis-era5-single-levels-timeseries'
    PREC: float = .25

    # Init
    def __init__(self, settings: PyCDSSettings | None = None) -> None:
        """Instantiate class object."""
        self.settings = settings or get_settings()

    # Properties
    @cached_property
    def client(self) -> Client:
        """Return the client."""
        return Client()

    @cached_property
    def dataset_start(self) -> str:
        """return the begin date of the selected collection \
            dataset in yyyy-mm-dd format."""
        dttm = self.client.get_collection(self.DATASET).begin_datetime
        return dttm.date()

    @cached_property
    def dataset_end(self) -> str:
        """return the end date of the selected collection \
            dataset in yyyy-mm-dd format."""
        # NOTE: Currently the end datetime is wrong in the metadata.
        # It returns at Dec 31st, 2024.
        # Instead we use the last updated date with a timedelta of -7 days for safety
        dttm = self.client.get_collection(self.DATASET).updated_at
        dttm += timedelta(days=-7)

        # TODO: When the date is fixed. Remove the above and uncomment the below
        # dttm = Client.get_collection(self.dataset).end_datetime
        return dttm.date()

    # Method
    @validate_call
    def download(
        self,
        lat: Lat,
        lon: Lon,
        path: str | Path,
        variables: str | list[str] | None = None,
        query_start: date | None = None,
        query_end: date | None = None,
        output_format: OutputFormats | None = None,
    ) -> None:
        """
        Given the (lat, lon) coordinates, the list of select variables and \
        the time bounds, download data from the CDS and save to the specified \
        path

        Parameters
        ----------
        lat: float
            Latitude coordinate of the selected location.
        lon: float
            Longitude coordinate of the selected location.
        path: str | Path
            Path where to save the data on disk.
        variables: str | list[str] | None = None
            Dataset variable(s) to be queried. Use to override the requested
            variables defined at at class initialization.
        query_start: str | None
            (Optional) Query start date in 'yyyy-mm-dd' format. Use to override \
            the start date defined at class initialization.
        query_end: str | None
            (Optional) Query end date in 'yyyy-mm-dd' format. Use to override \
            the end date defined at class initialization.
        output_format: Literal['netcdf', 'csv'] | None
            Desired output format. Use to override the end format defined \
            at class initialization.

        Returns
        -------
            None
        """
        # Assign default
        variables = variables or self.settings.variables
        query_start = query_start or self.settings.query_start or self.dataset_start
        query_end = query_end or self.settings.query_end or self.dataset_end
        output_format = output_format or OUTPUT_FORMAT

        # Build the request
        request = {
            'variable': to_list(variables),
            'location': {
                'latitude': round(lat / self.PREC) * self.PREC,
                'longitude': round(lon / self.PREC) * self.PREC,
            },
            'date': [f'{query_start}/{query_end}'],
            'data_format': output_format,
        }
        _display_request(request)

        # Execute
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        logger.info('Starting query.')
        t0 = time()
        self.client.retrieve(
            self.DATASET,
            request,
            target=path
        )
        logger.info(
            'Download successful !\n'
            f'Data save to: {(str(path))}.\n'
            f'Ellapsed time: {_format_time(time() - t0)}'
        )
