# pyCDS

> ⚠️ **Under construction.** This project is in early development. The API, command-line interface, and repository structure may change without notice.

A small command-line utility to download long ERA5 time series for a single location from the [Copernicus Climate Data Store (CDS)](https://cds.climate.copernicus.eu/).

## Installation

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/).

### User

Install the command-line tool in an isolated environment:

```bash
uv tool install git+https://github.com/steeve-boucherie/pyCDS.git
```

Or add it as a dependency to another uv project:

```bash
uv add git+https://github.com/steeve-boucherie/pyCDS.git
```

### Developer

```bash
git clone git@github.com:steeve-boucherie/pyCDS.git
cd pyCDS
uv sync --extra dev                    # development tools (pytest, ruff)
uv sync --extra dev --extra jupyter    # also install ipykernel (e.g. for VSCode notebooks)
```

## Setting up the CDS API

pyCDS relies on the official [`cdsapi`](https://github.com/ecmwf/cdsapi) client, which requires a few one-time steps:

1. Create a free account on the [Climate Data Store](https://cds.climate.copernicus.eu/).
2. Create a `~/.cdsapirc` file containing your personal API key.
3. Accept the licence of the ERA5 dataset(s) you want to download (on the dataset's "Download" tab).

See the [official instructions](https://cds.climate.copernicus.eu/how-to-api) for details.

## Usage

```bash
# TODO: replace with the actual command
pycds --lat <LAT> --lon <LON> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --output <FILE>
```

## License

[MIT](LICENSE)
