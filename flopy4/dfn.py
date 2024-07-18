from dataclasses import asdict, fields
from typing import List, Mapping

from flopy4.compound import MFKeystring, MFRecord
from flopy4.list import MFList
from flopy4.model import MFModel
from flopy4.package import MFPackage
from flopy4.parameter import MFParamSpec
from flopy4.scalar import MFDouble, MFInteger, MFKeyword, MFString
from flopy4.simulation import MFSimulationBase


def get_base_class(component, subcomponent):
    # todo support subpackages
    if component == "sim":
        if subcomponent == "nam":
            return MFSimulationBase
        else:
            return MFPackage
    else:
        if subcomponent == "nam":
            return MFModel
        else:
            return MFPackage


def get_param_class(param: MFParamSpec):
    # todo support array
    if param.type == "keyword":
        return MFKeyword
    elif param.type == "string":
        return MFString
    elif param.type == "integer":
        return MFInteger
    elif param.type == "double precision":
        return MFDouble
    elif param.type == "recarray":
        return MFList
    elif param.type == "record":
        return MFRecord
    elif param.type == "keystring":
        return MFKeystring


def consolidate_params(params: List[MFParamSpec]) -> List[MFParamSpec]:
    # todo consolidate compound parameters (record, keystring)
    pass


class DFN:
    @staticmethod
    def load(f) -> Mapping:
        component = None
        subcomponent = None
        params = []
        blocks = []
        while True:
            line = f.readline()
            if not line:
                break
            elif line == "\n":
                param = asdict(MFParamSpec.load(f))
                param.cls = get_param_class(param).__name__
                param.fields = fields(MFParamSpec)
                params.append()
                continue
            elif line.startswith("#"):
                line = line.replace("-", "").replace("#", "").strip()
                component, subcomponent, block = line.split()
                blocks.append(block)

        return {
            "component": component,
            "subcomponent": subcomponent,
            "base_cls": get_base_class(component, subcomponent).__name__,
            "params": consolidate_params(params),
            "blocks": blocks,
        }
