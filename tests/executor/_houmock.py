"""Recording mock of the Houdini `hou` module, for LICENSE-FREE cloud-CI construction smoke tests.

WHAT THIS IS
------------
A hand-written stand-in for `hou` (and a tiny `hwebserver` stub) rich enough that a typical data-only
handler can run its whole CONSTRUCTION path against it -- create a node, set parameters, wire inputs,
read back plausible geometry counts, and build a return dict -- WITHOUT a Houdini license and WITHOUT
any real cook. It records every createNode / setInput / parm-set on a module-level `LOG` for optional
assertions, and exposes `install()` (put the stub into sys.modules, only if the real `hou` is absent,
matching the sibling cloud tests) and `reset_scene()` (clear the fake scene between tool calls).

DELIBERATE DESIGN CHOICES (so a reviewer can trust what green means)
-------------------------------------------------------------------
* A real fake scene TREE. `hou.node("/obj")` and the other system-manager paths resolve to a node;
  `hou.node(<a path that was created>)` returns that node; `hou.node(<unknown user path>)` returns
  None -- so the repo's "create fresh, fail on name collision" handlers take their happy path.
* Scene objects (MockNode / MockParm / MockGeometry / MockParmTuple and the value types) have NO
  catch-all `__getattr__`. Only real, named methods exist, and geometry reads return real ints / lists
  / strings (never a truthy catch-all Mock). So a genuine wrong-method-name bug in the COMMON path
  still raises AttributeError and is surfaced -- the mock does not paper over handler bugs.
* The permissive layer is confined to the TOP-LEVEL `hou` module only: unknown `hou.<helper>` (rarely
  used UI / enum / math helpers -- hou.ui, hou.paneTabType, hou.parmTemplateType, hou.hmath, ...)
  falls through to a permissive sentinel so those uncommon helpers don't crash the run. Node/parm/geo
  attribute access does not.
* Node subclasses (MockObjNode / MockSopNode / MockDopNode / ...) exist so `isinstance(n, hou.ObjNode)`
  and friends resolve; a created node's `type().name()` returns exactly the type string it was made
  with, so handler guards like `dn.type().name() != "dopnet"` behave.
* Exceptions are REAL Exception subclasses so handler `except hou.OperationFailed:` clauses work.

This is a CONSTRUCTION/DATA-PATH mock, not a Houdini emulator: it does not cook, evaluate VEX, or
compute geometry. It proves the Python runs, not that the node graph is correct.
"""

import sys
import types


# ====================================================================================================
# module-level recording state
# ====================================================================================================
LOG = []          # list of tuples: ("createNode", parent_path, type, name) / ("setInput", ...) / ("set", ...)
_SCENE = {}       # normalized absolute path -> MockNode
_AUTO_NAME = {}   # parent_path -> per-type auto-increment counter


def _norm(path):
    """Normalize an absolute scene path: collapse doubled slashes, drop a trailing slash (keep root)."""
    p = str(path).replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p or "/"


# ====================================================================================================
# node-type / category
# ====================================================================================================
class MockNodeTypeCategory(object):
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def __eq__(self, other):
        return isinstance(other, MockNodeTypeCategory) and other._name == self._name

    def __hash__(self):
        return hash(("cat", self._name))


class MockNodeType(object):
    def __init__(self, type_name, category):
        self._type_name = type_name
        self._category = category

    def name(self):
        return self._type_name

    def nameWithCategory(self):
        return "%s/%s" % (self._category, self._type_name)

    def description(self):
        return self._type_name

    def category(self):
        return MockNodeTypeCategory(self._category)

    def definition(self):
        return None

    def instances(self):
        return ()

    def isManager(self):
        return self._type_name in ("obj", "out", "stage", "mat", "ch", "img", "shop", "root")

    def maxNumInputs(self):
        return 4

    def minNumInputs(self):
        return 0

    def maxNumOutputs(self):
        return 1

    def hasEditableInputData(self):
        return False


# category token -> the run-over child category a node of that container yields.
_CATEGORY_OF_CONTAINER = {
    "root": "Manager", "obj": "Object", "out": "Driver", "stage": "Lop",
    "mat": "Vop", "ch": "Chop", "img": "Cop", "shop": "Shop", "tasks": "Top",
}


def _child_category(type_name, own_category):
    """The category of children a node of `type_name` (living in `own_category`) will contain."""
    t = str(type_name).lower().split("::")[0]
    if t in ("dopnet",):
        return "Dop"
    if t in ("copnet", "cop2net", "cops", "img"):
        return "Cop"
    if t in ("lopnet", "stage"):
        return "Lop"
    if t in ("ropnet", "out"):
        return "Driver"
    if t in ("chopnet", "ch"):
        return "Chop"
    if t in ("matnet", "mat", "shopnet", "shop", "vopnet"):
        return "Vop"
    if t in ("geo", "geometry", "subnet", "sopnet"):
        return "Sop"
    if t in ("obj",):
        return "Object"
    # a plain node inside an Object network (e.g. a geo) yields SOPs; otherwise same category.
    if own_category == "Object":
        return "Sop"
    return own_category


# ====================================================================================================
# geometry + value types
# ====================================================================================================
class MockVector(object):
    """N-component vector: constructible from components or a sequence; indexable, iterable, with the
    small arithmetic / query surface handlers actually use (cross/dot/length/normalized/x/y/z)."""

    __slots__ = ("_v",)

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, MockVector)):
            vals = list(args[0])
        else:
            vals = list(args)
        self._v = [float(x) for x in vals]

    # sequence protocol
    def __len__(self):
        return len(self._v)

    def __iter__(self):
        return iter(self._v)

    def __getitem__(self, i):
        return self._v[i]

    def __setitem__(self, i, val):
        self._v[i] = float(val)

    def __eq__(self, other):
        try:
            return list(self._v) == list(other)
        except TypeError:
            return NotImplemented

    def __repr__(self):
        return "MockVector(%s)" % ", ".join("%g" % x for x in self._v)

    # component accessors
    def x(self):
        return self._v[0]

    def y(self):
        return self._v[1]

    def z(self):
        return self._v[2]

    def w(self):
        return self._v[3]

    # arithmetic
    def _pair(self, other):
        o = list(other) if isinstance(other, (list, tuple, MockVector)) else [other] * len(self._v)
        return o

    def __add__(self, other):
        o = self._pair(other)
        return MockVector([a + b for a, b in zip(self._v, o)])

    def __sub__(self, other):
        o = self._pair(other)
        return MockVector([a - b for a, b in zip(self._v, o)])

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return MockVector([a * other for a in self._v])
        o = self._pair(other)
        return MockVector([a * b for a, b in zip(self._v, o)])

    __rmul__ = __mul__

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return MockVector([a / other for a in self._v])
        o = self._pair(other)
        return MockVector([a / b for a, b in zip(self._v, o)])

    # queries
    def dot(self, other):
        return sum(a * b for a, b in zip(self._v, list(other)))

    def cross(self, other):
        a = self._v
        b = list(other)
        return MockVector([a[1] * b[2] - a[2] * b[1],
                           a[2] * b[0] - a[0] * b[2],
                           a[0] * b[1] - a[1] * b[0]])

    def length(self):
        return sum(a * a for a in self._v) ** 0.5

    def lengthSquared(self):
        return sum(a * a for a in self._v)

    def normalized(self):
        n = self.length()
        return MockVector([a / n for a in self._v]) if n else MockVector(list(self._v))

    def distanceTo(self, other):
        return (self - other).length()

    def __neg__(self):
        return MockVector([-a for a in self._v])


class MockMatrix(object):
    """Square matrix (3 or 4). Constructible from nothing (identity), a scalar, a flat/nested sequence,
    or another matrix. Supports the handful of extract/query ops handlers call; multiply is best-effort."""

    def __init__(self, dim, *args):
        self._dim = dim
        if not args:
            self._m = self._identity(dim)
        elif len(args) == 1 and isinstance(args[0], (int, float)):
            s = float(args[0])
            self._m = [s] * (dim * dim)
        elif len(args) == 1 and isinstance(args[0], MockMatrix):
            self._m = list(args[0]._m)
        elif len(args) == 1 and isinstance(args[0], (list, tuple)):
            flat = []
            for row in args[0]:
                if isinstance(row, (list, tuple)):
                    flat.extend(float(x) for x in row)
                else:
                    flat.append(float(row))
            self._m = (flat + self._identity(dim))[:dim * dim]
        else:
            self._m = (list(float(x) for x in args) + self._identity(dim))[:dim * dim]

    @staticmethod
    def _identity(dim):
        return [1.0 if (i // dim) == (i % dim) else 0.0 for i in range(dim * dim)]

    def __mul__(self, other):
        return MockMatrix(self._dim, list(self._m))

    def inverted(self):
        return MockMatrix(self._dim, list(self._m))

    def transposed(self):
        return MockMatrix(self._dim, list(self._m))

    def determinant(self):
        return 1.0

    def extractTranslates(self, *a, **k):
        return MockVector(0.0, 0.0, 0.0)

    def extractRotates(self, *a, **k):
        return MockVector(0.0, 0.0, 0.0)

    def extractScales(self, *a, **k):
        return MockVector(1.0, 1.0, 1.0)

    def asTuple(self):
        return tuple(self._m)

    def asTupleOfTuples(self):
        d = self._dim
        return tuple(tuple(self._m[r * d:(r + 1) * d]) for r in range(d))

    def setToIdentity(self):
        self._m = self._identity(self._dim)

    def explode(self, *a, **k):
        return {"translate": MockVector(0.0, 0.0, 0.0),
                "rotate": MockVector(0.0, 0.0, 0.0),
                "scale": MockVector(1.0, 1.0, 1.0),
                "shear": MockVector(0.0, 0.0, 0.0)}


def MockMatrix3(*args):
    return MockMatrix(3, *args)


def MockMatrix4(*args):
    return MockMatrix(4, *args)


class MockQuaternion(object):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, MockVector)):
            self._q = [float(x) for x in args[0]]
        elif args:
            self._q = [float(x) for x in args]
        else:
            self._q = [0.0, 0.0, 0.0, 1.0]
        while len(self._q) < 4:
            self._q.append(0.0)

    def __iter__(self):
        return iter(self._q)

    def __getitem__(self, i):
        return self._q[i]

    def __len__(self):
        return 4

    def extractRotationMatrix3(self):
        return MockMatrix3()

    def normalized(self):
        return MockQuaternion(list(self._q))


class MockColor(object):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, MockVector)):
            self._c = [float(x) for x in args[0]]
        elif args:
            self._c = [float(x) for x in args]
        else:
            self._c = [0.0, 0.0, 0.0]
        while len(self._c) < 3:
            self._c.append(0.0)

    def rgb(self):
        return tuple(self._c[:3])

    def __iter__(self):
        return iter(self._c)

    def __getitem__(self, i):
        return self._c[i]


class MockRamp(object):
    def __init__(self, basis=None, keys=None, values=None):
        self.basis = basis
        self.keys = keys
        self.values = values


class MockKeyframe(object):
    def __init__(self, *a, **k):
        self._frame = 0.0
        self._value = 0.0
        self._expr = None

    def setFrame(self, f):
        self._frame = float(f)

    def setValue(self, v):
        self._value = v

    def value(self):
        return self._value

    def frame(self):
        return self._frame

    def setExpression(self, e, *a, **k):
        self._expr = e

    def expression(self):
        return self._expr or ""

    def setInSlopeAuto(self, *a, **k):
        pass

    def setSlope(self, *a, **k):
        pass

    def setInterpretation(self, *a, **k):
        pass


class MockBoundingBox(object):
    def __init__(self, *a):
        self._min = MockVector(-1.0, -1.0, -1.0)
        self._max = MockVector(1.0, 1.0, 1.0)

    def sizevec(self):
        return self._max - self._min

    def minvec(self):
        return self._min

    def maxvec(self):
        return self._max

    def center(self):
        return (self._min + self._max) * 0.5

    def isValid(self):
        return True

    def enlargeToContain(self, *a, **k):
        pass


class MockAttrib(object):
    def __init__(self, name="attr"):
        self._name = name

    def name(self):
        return self._name

    def size(self):
        return 1

    def dataType(self):
        return _perm("hou.attribData.Float")

    def qualifier(self):
        return ""

    def isTransformedAsNormal(self):
        return False

    def strings(self):
        return ()


class MockGeometry(object):
    """A plausible EMPTY-geometry read surface. Every method returns a real int / list / string / value
    (never a catch-all truthy object), so branch conditions on geometry reads behave, but nothing here
    fabricates points/prims that a real cook would have produced."""

    def prims(self):
        return []

    def points(self):
        return []

    def vertices(self):
        return []

    def iterPrims(self):
        return []

    def iterPoints(self):
        return []

    def globalAttribs(self):
        return ()

    def pointAttribs(self):
        return ()

    def primAttribs(self):
        return ()

    def vertexAttribs(self):
        return ()

    def findPointAttrib(self, name):
        return None

    def findPrimAttrib(self, name):
        return None

    def findVertexAttrib(self, name):
        return None

    def findGlobalAttrib(self, name):
        return None

    def findPointGroup(self, name):
        return None

    def findPrimGroup(self, name):
        return None

    def findVertexGroup(self, name):
        return None

    def findEdgeGroup(self, name):
        return None

    def pointGroups(self):
        return ()

    def primGroups(self):
        return ()

    def edgeGroups(self):
        return ()

    def vertexGroups(self):
        return ()

    def boundingBox(self):
        return MockBoundingBox()

    def intrinsicValue(self, name):
        # counts are 0 on empty mock geometry; string intrinsics -> "".
        _num = ("pointcount", "primitivecount", "vertexcount", "primcount")
        return 0 if str(name).lower() in _num else ""

    def intrinsicValueDict(self):
        return {}

    def intrinsicNames(self):
        return ()

    def attribValue(self, name):
        return 0

    def floatAttribValue(self, name):
        return 0.0

    def stringListAttribValue(self, name):
        return ()

    def pointFloatAttribValues(self, name):
        return []

    def primFloatAttribValues(self, name):
        return []

    def setPointFloatAttribValues(self, name, values):
        LOG.append(("setPointFloatAttribValues", name))

    def addAttrib(self, *a, **k):
        return MockAttrib(a[1] if len(a) > 1 else "attr")

    def addArrayAttrib(self, *a, **k):
        return MockAttrib(a[1] if len(a) > 1 else "attr")

    def createPoint(self):
        return MockPoint()

    def createPolygon(self, *a, **k):
        return MockPolygon()

    def createNURBSCurve(self, *a, **k):
        return MockPolygon()

    def createBezierCurve(self, *a, **k):
        return MockPolygon()

    def clear(self):
        pass

    def saveToFile(self, path):
        LOG.append(("geo.saveToFile", path))

    def loadFromFile(self, path):
        LOG.append(("geo.loadFromFile", path))

    def freeze(self):
        return self

    def boundingBoxTuple(self):
        return (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)


class MockPoint(object):
    def __init__(self, num=0):
        self._num = num
        self._pos = MockVector(0.0, 0.0, 0.0)

    def number(self):
        return self._num

    def position(self):
        return self._pos

    def setPosition(self, v):
        self._pos = v if isinstance(v, MockVector) else MockVector(v)

    def attribValue(self, name):
        return 0

    def setAttribValue(self, *a, **k):
        pass

    def point(self):
        return self

    def vertices(self):
        return ()


class MockPolygon(object):
    def __init__(self):
        self._closed = True
        self._verts = []

    def setIsClosed(self, c):
        self._closed = bool(c)

    def addVertex(self, pt):
        self._verts.append(pt)
        return MockVertex(pt)

    def vertices(self):
        return list(self._verts)

    def type(self):
        return _perm("hou.primType.Polygon")

    def attribValue(self, name):
        return 0

    def number(self):
        return 0


class MockVertex(object):
    def __init__(self, pt=None):
        self._pt = pt or MockPoint()

    def point(self):
        return self._pt


# ====================================================================================================
# parameters
# ====================================================================================================
class _EnumMember(object):
    """A single, identity-comparable member of a mock enum (e.g. hou.parmTemplateType.Float)."""

    __slots__ = ("_enum", "_name")

    def __init__(self, enum_name, member):
        self._enum = enum_name
        self._name = member

    def name(self):
        return self._name

    def __repr__(self):
        return "%s.%s" % (self._enum, self._name)


class _Enum(object):
    """A mock enum with REAL, identity-comparable members and a working dir() -- used for the enums a
    handler actually introspects (dir()) or value-compares (==). Everything else stays permissive."""

    def __init__(self, enum_name, members):
        self.__dict__["_enum_name"] = enum_name
        for m in members:
            self.__dict__[m] = _EnumMember(enum_name, m)


# Enums handlers value-compare or dir()-introspect. Others fall through the module's permissive getattr.
parmTemplateType = _Enum("hou.parmTemplateType", (
    "Int", "Float", "String", "Toggle", "Menu", "Button", "FolderSet",
    "Separator", "Label", "Folder", "Ramp", "Data"))


class MockParmTemplate(object):
    def __init__(self, name="parm", ptype="Float"):
        self._name = name
        self._ptype = ptype

    def name(self):
        return self._name

    def type(self):
        # a plain Float parm: NOT a code/button parm, so parms.py's _is_code_parm allows it.
        return getattr(parmTemplateType, self._ptype, parmTemplateType.Float)

    def dataType(self):
        return _perm("hou.parmData.Float")

    def numComponents(self):
        return 1

    def defaultValue(self):
        return (0,)

    def tags(self):
        return {}                       # no editorlang / editor tags -> not a code-carrying parm

    def scriptCallback(self):
        return ""                       # no interactive callback

    def scriptCallbackLanguage(self):
        return _perm("hou.scriptLanguage.Python")

    def menuItems(self):
        return ()

    def menuLabels(self):
        return ()

    def stringType(self):
        return _perm("hou.stringParmType.Regular")


class MockParm(object):
    """Permissive-by-design PARM handle: `node.parm(anything)` always returns one so the repo's
    `_try_set(node, name, v)` "set if it exists" idiom works for any parm name. `.set()` records to LOG.
    Reads return real, benign defaults (0 / "" / ()) -- not a truthy catch-all -- so value-dependent
    branches behave. It has only named methods (no `__getattr__`), so a wrong parm-method name surfaces."""

    def __init__(self, node, name):
        self._node = node
        self._name = name
        self._value = None

    def name(self):
        return self._name

    def node(self):
        return self._node

    def path(self):
        return self._node.path() + "/" + self._name

    def set(self, value, **kwargs):
        self._value = value
        LOG.append(("set", self._node.path(), self._name, _short(value)))

    def setPending(self, value):
        self._value = value

    def eval(self):
        return self._value if isinstance(self._value, (int, float)) else 0

    def evalAsInt(self):
        try:
            return int(self._value)
        except (TypeError, ValueError):
            return 0

    def evalAsFloat(self):
        try:
            return float(self._value)
        except (TypeError, ValueError):
            return 0.0

    def evalAsString(self):
        return str(self._value) if isinstance(self._value, str) else ""

    def rawValue(self):
        return str(self._value) if isinstance(self._value, str) else ""

    def unexpandedString(self):
        return self.rawValue()

    def expression(self):
        return ""

    def setExpression(self, expr, *a, **k):
        LOG.append(("setExpression", self._node.path(), self._name))

    def deleteAllKeyframes(self):
        pass

    def setKeyframe(self, kf):
        LOG.append(("setKeyframe", self._node.path(), self._name))

    def keyframes(self):
        return ()

    def keyframesInRange(self, *a, **k):
        return ()

    def pressButton(self, *a, **k):
        LOG.append(("pressButton", self._node.path(), self._name))

    def parmTemplate(self):
        return MockParmTemplate(self._name)

    def tuple(self):
        return self._node.parmTuple(self._name)

    def tupleIndex(self):
        return 0

    def menuItems(self):
        return ()

    def menuLabels(self):
        return ()

    def isDisabled(self):
        return False

    def isLocked(self):
        return False

    def isSpare(self):
        return False

    def isAtDefault(self):
        return True

    def revertToDefaults(self):
        pass

    def lock(self, *a, **k):
        pass

    def setAutoscope(self, *a, **k):
        pass

    def description(self):
        return self._name

    def overrideTrackFlag(self, *a, **k):
        pass


class MockParmTuple(object):
    """Parm-tuple handle. Reports length 3 (the common vec3 case); handlers that check the length
    against their own vector just skip on a mismatch (they wrap the set in try/except or a len guard)."""

    def __init__(self, node, name, size=3):
        self._node = node
        self._name = name
        self._size = size
        self._parms = [MockParm(node, "%s%s" % (name, ("xyzw"[i] if i < 4 else i))) for i in range(size)]

    def name(self):
        return self._name

    def node(self):
        return self._node

    def set(self, values, **kwargs):
        LOG.append(("setTuple", self._node.path(), self._name, _short(values)))

    def eval(self):
        return tuple(0.0 for _ in range(self._size))

    def evalAsStrings(self):
        return tuple("" for _ in range(self._size))

    def __len__(self):
        return self._size

    def __iter__(self):
        return iter(self._parms)

    def __getitem__(self, i):
        return self._parms[i]

    def parmTemplate(self):
        return MockParmTemplate(self._name)

    def deleteAllKeyframes(self):
        pass


# ====================================================================================================
# nodes
# ====================================================================================================
class MockNode(object):
    """A scene node. Explicit, named method surface only (no `__getattr__`) so a wrong method name in
    the common construction path raises. Records createNode / setInput to LOG."""

    def __init__(self, path, name, type_name, category, child_category):
        self._path = _norm(path)
        self._name = name
        self._type = MockNodeType(type_name, category)
        self._category = category
        self._child_category = child_category
        self._inputs = []            # list of (node, outidx) or None
        self._named_inputs = {}
        self._userdata = {}
        self._children = {}          # name -> node
        self._parms = {}             # name -> MockParm (created lazily; permissive)
        self._flags = {}
        self._display = None
        self._render = None
        self._comment = ""
        self._color = MockColor(0.0, 0.0, 0.0)
        self._geometry = MockGeometry()

    # ---- identity -------------------------------------------------------------------------------
    def path(self):
        return self._path

    def name(self):
        return self._name

    def type(self):
        return self._type

    def childTypeCategory(self):
        return MockNodeTypeCategory(self._child_category)

    def isNull(self):
        return False

    def isInsideLockedHDA(self):
        return False

    def __repr__(self):
        return "<MockNode %s (%s)>" % (self._path, self._type.name())

    # ---- hierarchy ------------------------------------------------------------------------------
    def parent(self):
        parent_path = self._path.rsplit("/", 1)[0] or "/"
        if parent_path == self._path:
            return None
        return _SCENE.get(parent_path)

    def node(self, rel):
        if rel is None:
            return None
        rel = str(rel)
        if rel.startswith("/"):
            return node(rel)
        target = _norm(self._path + "/" + rel)
        return _SCENE.get(target)

    def children(self):
        return list(self._children.values())

    def allSubChildren(self, top_down=True, recurse_in_locked_nodes=True):
        out = []
        for c in self._children.values():
            out.append(c)
            out.extend(c.allSubChildren())
        return out

    def glob(self, pattern):
        # minimal: exact-name match or "*" -> all children.
        pat = str(pattern).strip()
        if pat in ("*", ""):
            return list(self._children.values())
        return [c for n, c in self._children.items() if n == pat]

    def recursiveGlob(self, pattern, *a, **k):
        return self.allSubChildren()

    # ---- creation -------------------------------------------------------------------------------
    def createNode(self, type_name, node_name=None, **kwargs):
        type_name = str(type_name)
        name = str(node_name) if node_name else _auto_name(self._path, type_name)
        child = _make_node(self._path + "/" + name, name, type_name, self._child_category)
        self._children[name] = child
        LOG.append(("createNode", self._path, type_name, name))
        _post_create(child, type_name)
        return child

    def createOutputNode(self, type_name, node_name=None, **kwargs):
        child = (self.parent() or self).createNode(type_name, node_name)
        try:
            child.setInput(0, self)
        except Exception:
            pass
        return child

    def collapseIntoSubnet(self, nodes, name="subnet"):
        return self.parent().createNode("subnet", name) if self.parent() else self

    def changeNodeType(self, new_type, **kwargs):
        self._type = MockNodeType(str(new_type), self._category)
        return self

    def copyTo(self, dest):
        return dest.createNode(self._type.name(), self._name + "_copy")

    # ---- inputs ---------------------------------------------------------------------------------
    def _ensure_inputs(self, idx):
        while len(self._inputs) <= idx:
            self._inputs.append(None)

    def setInput(self, idx, other, output_index=0):
        idx = int(idx)
        self._ensure_inputs(idx)
        self._inputs[idx] = (other, output_index)
        LOG.append(("setInput", self._path, idx, other.path() if other is not None else None))

    def setFirstInput(self, other, output_index=0):
        self.setInput(0, other, output_index)

    def setNamedInput(self, input_name, other, output_index=0):
        self._named_inputs[str(input_name)] = other
        LOG.append(("setNamedInput", self._path, str(input_name)))

    def inputs(self):
        return tuple(i[0] if i is not None else None for i in self._inputs)

    def input(self, idx):
        idx = int(idx)
        if 0 <= idx < len(self._inputs) and self._inputs[idx] is not None:
            return self._inputs[idx][0]
        return None

    def inputNode(self, idx):
        return self.input(idx)

    def inputConnectors(self):
        return tuple([] for _ in range(max(4, len(self._inputs))))

    def inputConnections(self):
        return tuple(MockConnection(i, v[0], v[1], self)
                     for i, v in enumerate(self._inputs) if v is not None)

    def outputConnections(self):
        return ()

    def outputConnectors(self):
        return ([],)

    def outputs(self):
        return ()

    def outputNode(self, idx=0):
        return None

    def inputNames(self):
        return ["Input %d" % (i + 1) for i in range(4)]

    def inputLabels(self):
        return self.inputNames()

    def outputNames(self):
        return ["Output 1"]

    def outputLabels(self):
        return ["Output 1"]

    def inputIndex(self, name):
        names = self.inputNames()
        return names.index(name) if name in names else -1

    def outputIndex(self, name):
        return 0

    # ---- parms ----------------------------------------------------------------------------------
    def parm(self, name):
        name = str(name)
        p = self._parms.get(name)
        if p is None:
            p = MockParm(self, name)
            self._parms[name] = p
        return p

    def parmTuple(self, name):
        return MockParmTuple(self, str(name))

    def parms(self):
        return tuple(self._parms.values())

    def parmTuples(self):
        return ()

    def setParms(self, mapping):
        for k, v in dict(mapping).items():
            self.parm(k).set(v)

    def setParmExpressions(self, mapping, *a, **k):
        for k2 in dict(mapping):
            LOG.append(("setExpression", self._path, k2))

    def parmsInFolder(self, *a, **k):
        return ()

    def parmTemplateGroup(self):
        return _perm("hou.ParmTemplateGroup")

    # ---- flags ----------------------------------------------------------------------------------
    def setDisplayFlag(self, on):
        self._flags["display"] = bool(on)
        if on:
            parent = self.parent()
            if parent is not None:
                parent._display = self

    def isDisplayFlagSet(self):
        return bool(self._flags.get("display", False))

    def setRenderFlag(self, on):
        self._flags["render"] = bool(on)
        if on:
            parent = self.parent()
            if parent is not None:
                parent._render = self

    def isRenderFlagSet(self):
        return bool(self._flags.get("render", False))

    def setGenericFlag(self, flag, on):
        self._flags[str(flag)] = bool(on)

    def isGenericFlagSet(self, flag):
        return bool(self._flags.get(str(flag), False))

    def setTemplateFlag(self, on):
        self._flags["template"] = bool(on)

    def setSelectableTemplateFlag(self, on):
        self._flags["selectable_template"] = bool(on)

    def setBypassFlag(self, on):
        self._flags["bypass"] = bool(on)

    def isBypassed(self):
        return bool(self._flags.get("bypass", False))

    def setHardLocked(self, on):
        self._flags["lock"] = bool(on)

    def setSelected(self, on, clear_all_selected=False, show_asset_if_selected=False):
        self._flags["selected"] = bool(on)

    def setCurrent(self, on, *a, **k):
        self._flags["current"] = bool(on)

    def setColor(self, color):
        self._color = color

    def color(self):
        return self._color

    def setComment(self, text):
        self._comment = str(text)

    def comment(self):
        return self._comment

    # ---- display / render sub-nodes -------------------------------------------------------------
    def displayNode(self):
        if self._display is not None:
            return self._display
        kids = list(self._children.values())
        return kids[-1] if kids else None

    def renderNode(self):
        if self._render is not None:
            return self._render
        return self.displayNode()

    # ---- geometry / cook ------------------------------------------------------------------------
    def geometry(self, *args, **kwargs):
        # real SopNode.geometry() takes no args, but a few callers pass an output index / frame.
        return self._geometry

    def geometryAtFrame(self, frame, *a, **k):
        return self._geometry

    def cook(self, force=False, frame_range=None):
        LOG.append(("cook", self._path))

    def needsToCook(self, *a, **k):
        return False

    def errors(self):
        return ()

    def warnings(self):
        return ()

    def messages(self):
        return ()

    def cookCount(self):
        return 1

    def isTimeDependent(self):
        return False

    # ---- placement ------------------------------------------------------------------------------
    def moveToGoodPosition(self, *a, **k):
        pass

    def setPosition(self, pos):
        self._userdata["_pos"] = tuple(pos)

    def position(self):
        return MockVector(0.0, 0.0)

    def layoutChildren(self, *a, **k):
        pass

    def setName(self, name, unique_name=False):
        new = str(name)
        parent = self.parent()
        if parent is not None and self._name in parent._children:
            del parent._children[self._name]
            parent._children[new] = self
        old_path = self._path
        self._name = new
        self._path = _norm((parent.path() if parent else "") + "/" + new)
        _SCENE.pop(old_path, None)
        _SCENE[self._path] = self

    # ---- user data ------------------------------------------------------------------------------
    def setUserData(self, key, value):
        self._userdata[str(key)] = str(value)

    def userData(self, key):
        return self._userdata.get(str(key))

    def userDataDict(self):
        return dict(self._userdata)

    def setCachedUserData(self, key, value):
        self._userdata[str(key)] = value

    def cachedUserData(self, key):
        return self._userdata.get(str(key))

    def destroy(self, *a, **k):
        parent = self.parent()
        if parent is not None:
            parent._children.pop(self._name, None)
        for p in list(_SCENE):
            if p == self._path or p.startswith(self._path + "/"):
                _SCENE.pop(p, None)

    # ---- transforms -----------------------------------------------------------------------------
    def worldTransform(self):
        return MockMatrix4()

    def localTransform(self):
        return MockMatrix4()

    def parmTransform(self):
        return MockMatrix4()

    def preTransform(self):
        return MockMatrix4()

    def setParmTransform(self, *a, **k):
        pass

    def setWorldTransform(self, *a, **k):
        pass

    def origin(self):
        return MockVector(0.0, 0.0, 0.0)

    # ---- misc -----------------------------------------------------------------------------------
    def path_(self):
        return self._path

    def sopNodeTypeCategory(self):
        return MockNodeTypeCategory("Sop")

    def setSelectableInViewport(self, *a, **k):
        pass

    def setUserData_(self, *a, **k):
        pass

    def isEditable(self):
        return True

    def canCreateDigitalAsset(self):
        return False

    def creationTime(self):
        return 0.0

    def modificationTime(self):
        return 0.0

    def sessionId(self):
        return id(self) % 100000

    def stash(self, *a, **k):
        pass


class MockConnection(object):
    """A node input connection (what MockNode.inputConnections() yields), mirroring the read surface
    handlers use to walk a solver's wired inputs (inputIndex / inputNode / outputIndex)."""

    def __init__(self, index, in_node, out_index, out_node):
        self._index = index
        self._in_node = in_node
        self._out_index = out_index
        self._out_node = out_node

    def inputIndex(self):
        return self._index

    def inputNode(self):
        return self._in_node

    def outputIndex(self):
        return self._out_index

    def outputNode(self):
        return self._out_node

    def inputName(self):
        return "Input %d" % (self._index + 1)

    def outputName(self):
        return "Output 1"

    def subnetIndirectInput(self):
        return None


class MockObjNode(MockNode):
    pass


class MockSopNode(MockNode):
    pass


class MockDopNode(MockNode):
    pass


class MockCopNode(MockNode):
    pass


class MockLopNode(MockNode):
    pass


class MockRopNode(MockNode):
    def render(self, *a, **k):
        LOG.append(("render", self._path))

    def executeGraph(self, *a, **k):
        pass


class MockTrack(object):
    def __init__(self, name="chan"):
        self._name = name

    def name(self):
        return self._name

    def allSamples(self):
        return ()

    def numSamples(self):
        return 0


class MockChopNode(MockNode):
    def track(self, name):
        return MockTrack(str(name))

    def tracks(self):
        return (MockTrack(),)

    def clip(self, *a, **k):
        return None


class MockVopNode(MockNode):
    pass


def _class_for_category(category):
    return {
        "Object": MockObjNode, "Sop": MockSopNode, "Dop": MockDopNode,
        "Cop": MockCopNode, "Lop": MockLopNode, "Driver": MockRopNode,
        "Chop": MockChopNode, "Vop": MockVopNode,
    }.get(category, MockNode)


def _make_node(path, name, type_name, own_category):
    child_cat = _child_category(type_name, own_category)
    cls = _class_for_category(own_category)
    node_obj = cls(path, name, type_name, own_category, child_cat)
    _SCENE[_norm(path)] = node_obj
    return node_obj


def _auto_name(parent_path, type_name):
    base = str(type_name).split("::")[0].split("/")[-1] or "node"
    key = (parent_path, base)
    _AUTO_NAME[key] = _AUTO_NAME.get(key, 0) + 1
    return "%s%d" % (base, _AUTO_NAME[key])


def _post_create(node_obj, type_name):
    """A few node types have a known internal chain that handlers navigate into (node.node("OUT") etc).
    Populate just enough so those construction paths don't hit a None child."""
    t = str(type_name).lower().split("::")[0]
    if t == "sopsolver":
        # sopsolver::2.0 exposes an editable dop_geometry -> OUT SOP chain (probe-confirmed shape).
        dg = node_obj.createNode("dop_geometry", "dop_geometry")
        out = node_obj.createNode("output", "OUT")
        out.setInput(0, dg)
        out.setDisplayFlag(True)


def _short(value):
    s = repr(value)
    return s if len(s) <= 60 else s[:57] + "..."


# ====================================================================================================
# hipFile / exceptions / permissive top-level helpers
# ====================================================================================================
class _HipFile(object):
    def name(self):
        return "untitled.hip"

    def path(self):
        return "untitled.hip"

    def basename(self):
        return "untitled.hip"

    def save(self, *a, **k):
        LOG.append(("hipFile.save",))

    def saveAsBackup(self, *a, **k):
        pass

    def load(self, *a, **k):
        LOG.append(("hipFile.load",))

    def merge(self, *a, **k):
        pass

    def clear(self, *a, **k):
        pass

    def hasUnsavedChanges(self):
        return False

    def isLoadingHipFile(self):
        return False

    def setName(self, *a, **k):
        pass


# Real Exception subclasses so `except hou.OperationFailed:` clauses actually catch.
class Error(Exception):
    pass


class OperationFailed(Error):
    pass


class NodeError(Error):
    pass


class NodeWarning(Error):
    pass


class ObjectWasDeleted(Error):
    pass


class PermissionError(Error):
    pass


class LoadWarning(Error):
    pass


class InvalidInput(Error):
    pass


class InvalidSize(Error):
    pass


class OperationInterrupted(Error):
    pass


class GeometryPermissionError(Error):
    pass


class TypeError_(Error):
    pass


class _Perm(object):
    """Permissive sentinel used ONLY for the top-level `hou` module's rarely-used helpers (hou.ui,
    hou.paneTabType, hou.parmTemplateType, hou.hmath, ...). Any attribute access or call returns another
    _Perm; `.name()` yields the last path segment (so `hou.snappingMode.Off.name()` -> "Off"). It is
    NEVER used for scene objects (nodes/parms/geometry), so real attribute bugs there still surface."""

    __slots__ = ("_name",)

    def __init__(self, name):
        object.__setattr__(self, "_name", name)

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError(key)
        return _Perm(self._name + "." + key)

    def __call__(self, *args, **kwargs):
        return _Perm(self._name + "()")

    def __iter__(self):
        return iter(())

    def __getitem__(self, i):
        return _Perm(self._name + "[]")

    def __len__(self):
        return 0

    def __bool__(self):
        return True

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __str__(self):
        return self._name

    def __repr__(self):
        return "<_Perm %s>" % self._name

    def name(self):
        return self._name.rsplit(".", 1)[-1].replace("()", "")

    def label(self):
        return self.name()


def _perm(name):
    return _Perm(name)


# ====================================================================================================
# the `hou` module object
# ====================================================================================================
def node(path):
    """hou.node(path): resolve an absolute scene path. Returns the node, or None for an unknown user
    path (so 'create fresh, fail on collision' handlers proceed). Relative paths resolve from root."""
    if path is None:
        return None
    return _SCENE.get(_norm(path))


def nodes(paths):
    return tuple(node(p) for p in paths)


def item(path):
    return node(path)


def pwd():
    return _SCENE.get("/obj") or _SCENE.get("/")


def frame():
    return 1.0


def setFrame(f):
    LOG.append(("setFrame", f))


def time():
    return 0.0


def fps():
    return 24.0


def expandString(s):
    return str(s)


def hscript(cmd):
    return ("", "")


def hscriptExpression(expr):
    return 0.0


def applicationVersion():
    return (21, 0, 671)


def applicationVersionString():
    return "21.0.671"


def isUIAvailable():
    return True


def _build_hou_module():
    mod = types.ModuleType("hou")

    # scene access
    mod.node = node
    mod.nodes = nodes
    mod.item = item
    mod.pwd = pwd
    mod.cd = lambda p=None: None
    mod.frame = frame
    mod.setFrame = setFrame
    mod.time = time
    mod.fps = fps
    mod.setFps = lambda f: None
    mod.expandString = expandString
    mod.hscript = hscript
    mod.hscriptExpression = hscriptExpression
    mod.applicationVersion = applicationVersion
    mod.applicationVersionString = applicationVersionString
    mod.isUIAvailable = isUIAvailable

    # node-type-category accessors (compared against node.childTypeCategory()).
    mod.sopNodeTypeCategory = lambda: MockNodeTypeCategory("Sop")
    mod.objNodeTypeCategory = lambda: MockNodeTypeCategory("Object")
    mod.dopNodeTypeCategory = lambda: MockNodeTypeCategory("Dop")
    mod.cop2NodeTypeCategory = lambda: MockNodeTypeCategory("Cop")
    mod.copNodeTypeCategory = lambda: MockNodeTypeCategory("Cop")
    mod.lopNodeTypeCategory = lambda: MockNodeTypeCategory("Lop")
    mod.ropNodeTypeCategory = lambda: MockNodeTypeCategory("Driver")
    mod.chopNodeTypeCategory = lambda: MockNodeTypeCategory("Chop")
    mod.vopNodeTypeCategory = lambda: MockNodeTypeCategory("Vop")
    mod.shopNodeTypeCategory = lambda: MockNodeTypeCategory("Shop")
    mod.nodeType = lambda category, name: MockNodeType(str(name), "Sop")
    mod.hipFile = _HipFile()
    mod.session = types.SimpleNamespace()

    # value types
    mod.Vector2 = MockVector
    mod.Vector3 = MockVector
    mod.Vector4 = MockVector
    mod.Matrix2 = lambda *a: MockMatrix(2, *a)
    mod.Matrix3 = MockMatrix3
    mod.Matrix4 = MockMatrix4
    mod.Quaternion = MockQuaternion
    mod.Color = MockColor
    mod.Ramp = MockRamp
    mod.Keyframe = MockKeyframe
    mod.StringKeyframe = MockKeyframe
    mod.BoundingBox = MockBoundingBox
    mod.Geometry = MockGeometry

    # node classes (for isinstance checks) + a few template classes handlers isinstance-test.
    mod.Node = MockNode
    mod.ObjNode = MockObjNode
    mod.SopNode = MockSopNode
    mod.DopNode = MockDopNode
    mod.CopNode = MockCopNode
    mod.LopNode = MockLopNode
    mod.RopNode = MockRopNode
    mod.ChopNode = MockChopNode
    mod.VopNode = MockVopNode
    mod.NodeType = MockNodeType
    mod.NodeTypeCategory = MockNodeTypeCategory
    mod.Parm = MockParm
    mod.ParmTuple = MockParmTuple
    mod.ParmTemplate = MockParmTemplate
    mod.ToggleParmTemplate = type("ToggleParmTemplate", (MockParmTemplate,), {})
    mod.StringParmTemplate = type("StringParmTemplate", (MockParmTemplate,), {})
    mod.MenuParmTemplate = type("MenuParmTemplate", (MockParmTemplate,), {})
    mod.FloatParmTemplate = type("FloatParmTemplate", (MockParmTemplate,), {})
    mod.IntParmTemplate = type("IntParmTemplate", (MockParmTemplate,), {})

    # exceptions (real subclasses)
    mod.Error = Error
    mod.OperationFailed = OperationFailed
    mod.NodeError = NodeError
    mod.NodeWarning = NodeWarning
    mod.ObjectWasDeleted = ObjectWasDeleted
    mod.PermissionError = PermissionError
    mod.LoadWarning = LoadWarning
    mod.InvalidInput = InvalidInput
    mod.InvalidSize = InvalidSize
    mod.OperationInterrupted = OperationInterrupted
    mod.GeometryPermissionError = GeometryPermissionError
    mod.TypeError = TypeError_

    # Enums a handler value-compares or dir()-introspects get REAL, identity-comparable members (their
    # exact member sets are probe-confirmed in the handler docstrings). Everything else stays permissive.
    mod.parmTemplateType = parmTemplateType
    mod.viewportColorScheme = _Enum("hou.viewportColorScheme", ("Dark", "DarkGrey", "Grey", "Light"))
    mod.viewportLighting = _Enum("hou.viewportLighting",
                                 ("Headlight", "HighQuality", "HighQualityWithShadows", "Normal", "Off"))
    mod.glShadingType = _Enum("hou.glShadingType", (
        "Flat", "FlatWire", "HiddenLineGhost", "HiddenLineInvisible", "MatCap", "MatCapWire",
        "ShadedBoundingBox", "Smooth", "SmoothWire", "Wire", "WireBoundingBox", "WireGhost"))
    mod.markerVisibility = _Enum("hou.markerVisibility",
                                 ("Always", "AroundPointer", "Selected", "UnderPointer"))
    mod.boundaryDisplay = _Enum("hou.boundaryDisplay", ("Off", "On", "View3D", "ViewUV"))
    mod.displaySetType = _Enum("hou.displaySetType", (
        "CurrentModel", "DisplayModel", "GhostObject", "SceneObject", "SelectedObject", "TemplateModel"))
    mod.geometryViewportLayout = _Enum("hou.geometryViewportLayout", (
        "DoubleSide", "DoubleStack", "Quad", "QuadBottomSplit", "QuadLeftSplit", "Single",
        "TripleBottomSplit", "TripleLeftSplit"))
    mod.paneLinkType = _Enum("hou.paneLinkType", (
        "FollowSelection", "Pinned", "Group1", "Group2", "Group3", "Group4",
        "Group5", "Group6", "Group7", "Group8", "Group9"))
    mod.snappingMode = _Enum("hou.snappingMode", ("Off", "Grid", "Prim", "Point", "Multi"))
    mod.promptMessageType = _Enum("hou.promptMessageType", ("Error", "Message", "Prompt", "Warning"))

    # rarely-used helper namespaces -> permissive sentinels (top-level module only).
    for _perm_attr in ("ui", "hotkeys", "hda", "text", "hmath", "qt", "galleries", "styles",
                       "playbar", "undos", "audio", "viewportVisualizers", "properties"):
        setattr(mod, _perm_attr, _perm("hou." + _perm_attr))

    # a permissive __getattr__ for any other rarely-used top-level helper / enum namespace
    # (hou.parmTemplateType, hou.nodeFlag, hou.primType, hou.paneTabType, hou.severityType, ...).
    def _mod_getattr(name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _perm("hou." + name)

    mod.__getattr__ = _mod_getattr
    return mod


def _build_hwebserver_module():
    mod = types.ModuleType("hwebserver")

    class Response(object):
        def __init__(self, body="", status=200, content_type="application/json", headers=None):
            self.body = body
            self.status = status
            self.content_type = content_type

    mod.Response = Response
    mod.run = lambda *a, **k: None
    mod.urlHandler = lambda *a, **k: (lambda fn: fn)
    mod.requestShutdown = lambda *a, **k: None

    def _getattr(name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _perm("hwebserver." + name)

    mod.__getattr__ = _getattr
    return mod


# ====================================================================================================
# public API
# ====================================================================================================
def reset_scene():
    """Clear the fake scene and re-create the system-manager containers. Call before EVERY handler
    invocation so one tool call never sees another's nodes."""
    _SCENE.clear()
    _AUTO_NAME.clear()
    del LOG[:]
    # root + the standard manager networks the handlers reach for (/obj, /out, /stage, /mat, ...).
    root = MockNode("/", "", "root", "Manager", "Manager")
    _SCENE["/"] = root
    for name, container_type in (("obj", "obj"), ("out", "out"), ("stage", "stage"),
                                 ("mat", "mat"), ("ch", "ch"), ("img", "img"),
                                 ("shop", "shop"), ("tasks", "tasks")):
        own_cat = "Manager"
        child_cat = _CATEGORY_OF_CONTAINER.get(container_type, "Object")
        n = MockNode("/" + name, name, container_type, own_cat, child_cat)
        root._children[name] = n
        _SCENE["/" + name] = n
    return sys.modules.get("hou")


def install():
    """Install the mock `hou` + `hwebserver` into sys.modules, but ONLY when the real modules are
    absent (mirrors the sibling cloud tests: under a licensed hython the real `hou` must win). Returns
    the installed (or pre-existing real) `hou` module. Safe to call more than once."""
    if "hou" not in sys.modules:
        sys.modules["hou"] = _build_hou_module()
        reset_scene()
    if "hwebserver" not in sys.modules:
        sys.modules["hwebserver"] = _build_hwebserver_module()
    return sys.modules["hou"]


# a node factory the smoke test uses to build fixtures the handlers can resolve.
def make_node(path, type_name):
    """Create (or return) a node at an absolute path, materializing any missing parent containers.
    Used by the smoke harness to pre-create NodePath fixtures a handler will resolve_node()."""
    path = _norm(path)
    existing = _SCENE.get(path)
    if existing is not None:
        return existing
    parent_path, _, leaf = path.rpartition("/")
    parent_path = parent_path or "/"
    parent = _SCENE.get(parent_path) or make_node(parent_path, "subnet")
    return parent.createNode(type_name, leaf)
