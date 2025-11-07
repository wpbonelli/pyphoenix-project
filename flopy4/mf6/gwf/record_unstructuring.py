import attrs
import cattrs
from flopy4.mf6.gwf.oc import Oc, Steps
# attrs.astuple(Oc.SaveRecord("head", Steps([1])))
# attrs.astuple(Oc.SaveRecord("head", Oc.Steps([1])))
# cattrs.unstructure(Oc.SaveRecord("head", Steps([1])))
# cattrs.unstructure(Oc.SaveRecord("head", Oc.Steps([1])))
c = cattrs.Converter(unstructure_strat=cattrs.UnstructureStrategy.AS_TUPLE)
c.register_unstructure_hook(Oc.Steps, lambda s: tuple([t for t in attrs.astuple(s) if t]))
c.unstructure(Oc.SaveRecord("head", Oc.Steps([1])))
