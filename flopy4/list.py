from pandas import DataFrame

from flopy4.parameter import MFParameter


class MFList(MFParameter, DataFrame):
    """
    A MODFLOW 6 tabular (i.e. list) input backed by a Pandas `DataFrame`.
    """

    def __init__(
        self,
        data=None,
        *args,
        description=None,
        optional=True,
        **kwargs,
    ):
        MFParameter().__init__(description, optional)
        DataFrame.__init__(data, *args, **kwargs)

    @property
    def value(self) -> DataFrame:
        return self.copy()

    @classmethod
    def load(cls, f):
        # todo
        pass

    def write(self, f):
        # todo
        pass

    @staticmethod
    def resolve_dtypes(package, aux=None, boundname=None):
        # todo
        pass
