"""A bunch of utility methods."""
import logging
import zipfile
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Literal, get_args

import pandas as pd

import xarray as xr


# LOGGER
logger = logging.getLogger(__name__)


# CONSTANT
DTTM_ELEMENTS = Literal[
    'second',
    'minute',
    'hour',
    'day',
    'day_of_year',
    'month',
    'quater',
    'year',
]


# ==========================================================================
# Tester
# ==========================================================================
def to_list(x: Any | list[Any]) -> list[Any]:
    """
    Convert the input variable to a list.

    Notes
    -----
    Without effect if x is already of list type.

    Parameters
    ----------
    x: Any | List[Any]
        Input variable
    allowed: List[Any]
        The list of allowed values.

    Raises
    ------
        ValueError
    """
    return [[x], x][isinstance(x, list)]


def is_allowed(val: Any, allowed: list[Any]) -> None:
    """
    Test if the input value is one of the allowed values, \
        raise ValueError if otherwise.

    Parameters
    ----------
    val: Any
        The value to be tested.
    allowed: List[Any]
        The list of allowed values.

    Raises
    ------
        ValueError
    """
    if val not in allowed:
        msg = f'Invalid value "{val}", must be one of "{allowed}". ' \
              'Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)


def is_subset(values: list[Any], allowed: list[Any]) -> None:
    """
    Given a list of elements verify it is a valid subset of the allowed values, \
        raise a ValueError if otherwise.

    Parmaters
    ---------
    values: List[Any]
        A list containing the values to be tested.
    allowed: List[Any]
        A list containing all the possible valid values.

    Raises
    ------
        ValueError
    """
    diff = set(values).difference(allowed)
    if diff != set():
        msg = f'The input contains forbidden values: "{diff}".\n' \
              f'Please check your inputs. Allowed values are: "{allowed}".'
        logger.error(msg)
        raise ValueError(msg)


def is_file(path: str | Path) -> None:
    """
    Test if the input path is a valid file, \
        raises a ValueError if otherwise.

    Parameters
    ----------
    path: str | Path
        Path to be tested.

    Raises
    ------
        ValueError
    """
    # Force type to be Path
    path = Path(path).resolve()

    if not path.is_file():
        msg = f'Input path "{path}" is not a file. ' \
              'Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)


def is_dir(path: str | Path) -> None:
    """
    Test if the input path is a valid directory, \
        raises a ValueError if otherwise.

    Parameters
    ----------
    path: str | Path
        Path to be tested.

    Raises
    ------
        ValueError
    """
    # Force type to be Path
    path = Path(path)

    if not path.is_dir():
        msg = f'Input path "{path}" is not a directory. ' \
              'Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)
# ==========================================================================


# ==========================================================================
# I/O
# ==========================================================================
def validate_folder(path: str | Path) -> Path:
    """
    Verify the input path is a folder, and creates it if does not exist.

    Parameters
    ----------
    path: str | Path
        The path to validate.

    Returns
    -------
        Path
    """
    path = Path(path)
    if not path.exists():
        os.makedirs(path)

    is_dir(path)

    return path


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
    is_file(path)
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


def save_ds(
    ds: xr.Dataset,
    output_path: str | Path,
    out_fname: str
) -> None:
    """
    Given the dataset of ERA5 data, save the monthly chunk following the \
    <YEAR> / <MONTH> folder tree convention.

    Parameters
    ----------
    ds: xr.Dataset
        Input dataset
    output_path: str | Path
        Folder where to save the data.
    out_fname: str
        The name of the file.
    """
    output_path = validate_folder(output_path)
    ds = ds.assign_attrs(
        generated_at=datetime.now().strftime(r'%Y%m%dT%H%M%S')
    )
    ds.to_netcdf(output_path / out_fname)
    logger.info('File saved at ')


def save_groups(
    groups: xr.core.groupby.DatasetGroupBy,
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
    output_root = validate_folder(output_root)
    for n, (key, ds) in enumerate(groups, start=1):
        logger.info(
            f'Save data for group: {key}'
            f'({n:03d} of {len(groups.groups.keys()):03d})'
        )
        output_path = output_root / '/'.join([f'{key:02d}' for key in to_list(key)])
        save_ds(ds, output_path, out_fname)

# ==========================================================================


# ==========================================================================
# Xarray
# ==========================================================================
def check_required(
    ds: xr.Dataset,
    req_elems: str | list[str],
    elem_type: Literal['key', 'dim', 'coord', 'all', 'attr'] = 'key'
) -> None:
    """
    Verify that the required elements are present within the input dataset,
        raise KeyError, otherwise.

    Parameters
    ----------
    ds: xr.Dataset
        Input dataset to be tested.
    req_keys: str | list[str]
        Mandatory key(s)
    elem_type: 'key' | 'dim' | 'coord' | 'all'
        Element type to be tested.
        Default is 'key'

    Returns
    -------
        None

    Raises
    ------
    - KeyError:
        - if any of req_elems is missing from the input dataset.
    - ValueError:
        - if elem_type is not one of 'key' | 'dim' | 'coord' | 'all'
    """
    # Check input
    allowed_type = ['key', 'dim', 'coord', 'all', 'attr']
    if elem_type not in allowed_type:
        msg = 'Invalid value for parameter "elem" type. ' \
              f'Expected one of "{allowed_type}", but received "{elem_type}". ' \
              'Please check your inputs.'
        logger.error(msg)
        raise ValueError(msg)

    # Force input type
    req_elems = [[req_elems], req_elems][isinstance(req_elems, list)]
    ds = [ds, xr.merge([ds])][isinstance(ds, xr.DataArray)]

    all_elems = {
        'key': ds.keys(),
        'dim': ds.dims,
        'coord': ds.coords,
        'all': ds.variables,
        'attr': ds.attrs.keys()
    }[elem_type]
    all_elems = set(all_elems)

    req_elems = set(req_elems)
    if not req_elems.issubset(all_elems):
        diff = list(req_elems - all_elems)
        msg = f'The following mandatory {elem_type}(s) are absent from input ' \
              f'dataset: "{diff}".\nPlease check your inputs.'
        logger.error(msg)
        raise KeyError(msg)


def nondim_coords(xr_obj: xr.DataArray | xr.Dataset) -> list[str]:
    """
    List all to coordinates that are not core dimension of the \
        input xarray object.

    Parameters
    ----------
    xr_obj: DataArray | Dataset
        The input xarray object to be processed.

    Returns
    -------
        List[str]
    """
    coords = [
        c for c in xr_obj.coords
        if c not in xr_obj.dims
    ]
    return coords


def drop_nondim_coords(
    xr_obj: xr.DataArray | xr.Dataset,
    to_keep: str | list[str] | None = None,
) -> xr.DataArray | xr.Dataset:
    """
    Drop all the coordinations that are not dimension of the input xarray object.

    Parameters
    ----------
    xr_obj: DataArray | Dataset
        The input xarray object to be processed.
    to_keep: str | List[str] | None
        (Optional) element(s) to be kept. Leave to None to drop all.
    """
    # Verify inputs
    to_keep = [[], to_list(to_keep)][to_keep is not None]

    # Drop
    xr_obj = xr_obj.drop_vars([
        c for c in nondim_coords(xr_obj)
        if c not in to_keep
    ])

    return xr_obj


def add_dttm(
    ds: xr.Dataset,
    t_dim: str,
    elements: DTTM_ELEMENTS | list[DTTM_ELEMENTS]
) -> xr.Dataset:
    """
    Given a dataset indexed on time, appended the requested datetime properties \
    as coordinates.

    Parameters
    ----------
    ds: xr.Dataset
        Input dataset
    t_dim: str
        The name of the time dimension in the input dataset.
    elements: ALLOWED_DTTM | list[ALLOWED_DTTM]
        The datetime property(ies) to be added.

    Returns
    -------
        Dataset
    """
    # Validate
    elements = to_list(elements)
    is_subset(elements, get_args(DTTM_ELEMENTS))
    check_required(ds, t_dim, 'dim')

    # Append
    times = pd.to_datetime(ds[t_dim].values)
    ds = ds.assign_coords({
        elem: (t_dim, times.__getattribute__(elem))
        for elem in elements
    })

    return ds
# ==========================================================================
