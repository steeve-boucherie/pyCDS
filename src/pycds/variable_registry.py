"""Variable Registry class for automatic generation of missing dataset \
    variables and filters in analysis pipelines."""
import logging
from typing import Iterable


# PACKAGE IMPORT
from pycds.transform import DataTransformerInterface

from xarray import Dataset

# LOGGER
logger = logging.getLogger(__name__)


# CLASS
class VariableRegistry():
    """
    Named, idempotent registry of dataset-level boolean flags.

    Attributes
    ----------
    builders: dict[str, transformer_like]
        A mapping of the form key -> transformer defining the transformer object \
        to be called for each missing dataset key.
    overrides: dict[str, transformer_like]
        A mapping of the form key -> transformer defining transformers to override \
        the analysis-specific default.
    """

    # Init
    def __init__(
        self,
        builders: dict[str, DataTransformerInterface],
        overrides: dict[str, DataTransformerInterface] | None = None,
    ) -> None:
        """Create class instance."""
        self._builders: dict[str, DataTransformerInterface] = {**builders, **(overrides or {})}
        self._is_override = {key: key in (overrides or {}) for key in self._builders}

    def update(self, overrides: dict[str, DataTransformerInterface]) -> None:
        """
        Given a set of new builders, upddate the current class instance to by \
        overriding the current builders.

        Parameters
        ----------
        overrides: dict[str, transformer_like]
            A mapping of the form key -> transformer defining transformers to override \
            the analysis-specific default.
        """
        self._builders = {**self._builders, **overrides}
        self._is_override = {key: key in overrides for key in self._builders}

    # Properties
    @property
    def name(self) -> str:
        """Return the class name."""
        return self.__class__.__name__

    @property
    def registered_vars(self) -> list[str]:
        """Return the list of registered variables."""
        return list(self._builders.keys())

    @property
    def builders(self) -> dict[str, DataTransformerInterface]:
        """Return the builders."""
        return self._builders

    # Utils
    def topological_order(
        self,
        requested: Iterable[str],
        done: Iterable[str] | None = None,
    ) -> list[str]:
        """
        Return `requested` keys plus their transitive dependencies, ordered so
        that each key comes after everything it depends on.

        Parameters
        ----------
        requested: Iterable[str]
            The requested key(s) that must be appended to the dataset.
        done: Iterable[str] | None
            (Optional) Key(s) already existing/generated. Use parameters to \
            test existence of keys that may appear as intermediate step when \
            building the topological order.

        Returns
        -------
        ordered: list[str]
            List of required keys ordered to solve dependency issues.
        root: list[str]
            List of required keys that are "root" (i.e., assigned to any builder) \
            and must appear in the input dataset.

        Raises
        ------
        ValueError: if a circular dependency is detected.
        """
        # Internal
        def visit(key: str, path: list[str]) -> None:
            if key in done:
                return  # The key is already there, no build.

            # Test if the key has a builder assign to it, else make it root
            if key not in self.builders:
                root.add(key)
                return

            # Raise Error on circular dependency
            if key in in_progress:
                cycle = ' -> '.join(path + [key])
                msg = f'{self.name}: Circular dependency detected: {cycle}.'
                logger.error(msg)
                raise ValueError(msg)

            in_progress.add(key)
            transformer = self._builders[key]
            deps = list(getattr(transformer, 'required_keys', []))
            deps += list(getattr(transformer, 'required_coords', []))
            for dep in deps:
                visit(dep, path + [key])
            in_progress.remove(key)
            done.add(key)
            order.append(key)

        # Create object
        order = []
        in_progress: set[str] = set()
        done: set[str] = set(done or [])
        root: set[str] = set()

        # Build topological order
        for key in requested:
            visit(key, [])

        return order, list(root)

    # Methods
    def validate_keys(self, requested: str | list[str]) -> None:
        """
        Validate that the requested key(s) form a subset of the registered \
        variables, and raise a ValueError if otherwise.

        Parameters
        ----------
        requested: str | list[str]
            The key(s) to be added to the input dataset.

        Raises
        ------
            ValueError
        """
        if isinstance(requested, str):
            requested = [requested]
        missing = set(requested).difference(self.registered_vars)
        if missing != set():
            msg = 'Some requested key are not associated with a specific builder.\n' \
                  f'Key missing builders: {missing}.\nPlease check your inputs.'
            logger.error(msg)
            raise ValueError(msg)

    def ensure_flags(self, ds: Dataset, requested: str | list[str]) -> Dataset:
        """
        Given a dataset, generated the requested key(s) using the registered \
        transformers.

        Parameters
        ----------
        ds: Dataset
            Input dataset.
        requested: str | list[str]
            The key(s) to be added to the input dataset.
        """
        # Validate
        existing = ds.variables
        missing = (
            set(requested if isinstance(requested, list) else [requested])
            .difference(existing)
        )
        self.validate_keys(missing)

        # Generate keys
        order, _ = self.topological_order(missing, existing)
        for key in order:
            logger.info(f'{self.name}: Generating additional key: "{key}"')
            transformer = self._builders[key]
            ds = transformer.fit_transform(ds)
            ds[key].attrs['flag_source'] = (
                'override' if self._is_override[key] else 'default'
            )

        return ds
