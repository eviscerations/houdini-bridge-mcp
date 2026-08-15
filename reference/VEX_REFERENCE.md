# VEX reference

A shared VEX lookup for the user and the AI assistant, plus the workflow it supports. This is generic Houdini H21 VEX (public knowledge), organized as a scannable reference rather than a tutorial.

> **Curated vs exhaustive.** This sheet is a curated set of verified idioms and patterns. For the *complete* API — every VEX function's full signature and documentation — the running Houdini also serves its entire offline help at the MCP's local help server (`127.0.0.1:<port>/ref/...`; get the URL from `capabilities`). Use this cookbook for the patterns, the help server for the exhaustive reference.

---

## Why this doc exists

The MCP executor is **data-only**. Every capability is a fixed, typed handler; there is deliberately **no raw-VEX / wrangle-authoring tool** and no "run this snippet" path. Houdini's embedded Python and VEX are full, unrestricted execution — a general wrangle-authoring endpoint would be remote code execution with the owner's full privileges. So that endpoint simply does not exist in the catalog.

VEX is not gone, though — it is **user-mediated**. The AI drives the scene up to the point a wrangle is needed; the **user** drops and wires the wrangle node and pastes the VEX. The boundary stays intact because the code enters the session through the user's own hands, not through a tool call. This sheet is the reference that makes that handoff fast and correct.

---

## The wrangle handoff

1. **AI builds the scene** with typed tools up to the node where custom VEX is needed, and names the upstream node so the user can find it.
2. **AI states the intent** — run-over class (points/prims/detail), which inputs feed the wrangle, and which attributes are read vs written.
3. **User drops the wrangle** — an Attribute Wrangle (geometry) or Volume Wrangle (volumes/heightfields) — and wires the named upstream node into input 0 (plus inputs 1–3 if the snippet reads other geometry).
4. **User sets Run Over** to match the intent (Points / Primitives / Vertices / Detail).
5. **AI + user write the VEX together** using this sheet; the user pastes it into the wrangle's code field.
6. **User verifies** the result in the viewport / geometry spreadsheet and reports back.
7. **AI resumes** driving the pipeline with typed tools from the wrangle's output.

Rule of thumb: the AI never receives or executes VEX; it only proposes text for the user to paste.

---

## Surfacing a wrangle — when to offer, and the consent handshake

Wrangles are a first-class part of Houdini, not an escape hatch — but here they are HUMAN-GATED. The AI's job is to *surface* them proactively and teach, never to reach for raw code on its own.

**When to surface one (offer it without being asked):** when the task needs logic the typed tools can't express — conditional/measured breaking (break constraints when a solver-measured attribute crosses a threshold), cluster/boundary detection (compare an attribute across a primitive's two points), custom particle/point masks (a point-cloud query driving forces or density), per-piece naming/bookkeeping, or debug coloring keyed off any attribute. Recipe steps flag these with a `wrangle_opportunity` field (see recipe_reference) — treat it as a cue to offer.

**The consent handshake (never skip it):**
1. **Recognize + explain** — say a wrangle is the right tool here, and teach what it will do and why. This MCP is also a Houdini *learning* tool: explain along the way, don't just act.
2. **Propose the VEX** — build the snippet from this reference (cite the functions), and state the run-over class and which attributes are read vs written.
3. **Two consented paths to run it:**
   - **Validated lane** — if (and only if) the user has enabled `allow_attrib_expr`, the AI may apply the snippet via `set_attrib_expr`, which validates it allowlist-first before Houdini ever sees it.
   - **Paste-by-hand** — otherwise (or by preference), hand the VEX text over for the user to paste into a wrangle themselves (the handoff above). The AI never executes it.
4. **Verify + teach the result** — read it back / look at it, and explain what happened.

Why this shape: Houdini's embedded Python is full, unrestricted CPython and raw VEX has RCE escape hatches (`system`/`run`, expression/`ophook` bridges, file + network builtins), so arbitrary code never reaches Houdini. Safe VEX is not "no VEX" — it is **AI-assisted, human-gated VEX**.

---

## Wrangle contexts & run-over

An Attribute Wrangle runs its snippet once per element of the **Run Over** class. Choose the class to match what you are iterating.

| Run Over | Iterates | Element index | Count |
|---|---|---|---|
| Points | points | `@ptnum` | `@numpt` |
| Primitives | primitives | `@primnum` | `@numprim` |
| Vertices | linear vertices | `@vtxnum` | `@numvtx` |
| Detail (only once) | whole geo, once | `@elemnum` (0) | — |

`@elemnum` is the generic current-element index for any class. Time context is available everywhere:

```vex
// runs once per point
@P.y += 0.1;                 // ptnum = @ptnum, of @numpt total

// detail wrangle: run once, e.g. write a global attribute
i@total = @numpt;

// time
f@t = @Time;                 // seconds
i@f = @Frame;                // current frame
```

Detail-run-over is for reductions and single global writes. Point/prim/vertex run-over is parallel — do not assume execution order.

---

## Attribute syntax & types

`@name` binds a geometry attribute. Common built-ins carry an implicit type:

| Attribute | Type | Meaning |
|---|---|---|
| `@P` | vector | position |
| `@N` | vector | normal |
| `@Cd` | vector | diffuse color |
| `@v` | vector | velocity |
| `@pscale` | float | per-point scale |
| `@id` | int | stable id |
| `@ptnum @numpt` | int | point index / count |
| `@primnum @numprim` | int | prim index / count |
| `@Time @Frame` | float / int | time |

For any non-standard attribute, **declare the type explicitly** with a prefix so the binding is unambiguous:

| Prefix | Type | Tuple size |
|---|---|---|
| `f@` | float | 1 |
| `i@` | int | 1 |
| `v@` | vector (3) | 3 |
| `u@` | vector2 | 2 |
| `p@` | vector4 (quaternion-style, e.g. `p@orient`) | 4 |
| `2@` | matrix2 (2×2) | 4 |
| `3@` | matrix3 (3×3) | 9 |
| `4@` | matrix4 (4×4) | 16 |
| `s@` | string | 1 |

A numeric `N@` prefix means an **N×N matrix** — `2@`/`3@`/`4@` bind matrix2/matrix3/matrix4, **not** vectors. There is **no** `9@` or `16@` prefix (both are VEX syntax errors): a 3×3 is `3@`, a 4×4 is `4@`. Quaternion-style vector4 attributes (`orient`, `rot`) take `p@`; `u@` binds a **vector2**, not a quaternion. (Prefix types/sizes verified empirically under H21.0.671.)

```vex
f@mask   = 0.5;          // create/write a float attribute
v@up     = {0,1,0};      // vector literal
i@class  = 2;            // int
s@name   = "wall";       // string
p@rgba   = set(1,0,0,1); // vector4 (p@ = vector4; 4@ would be a matrix4)
3@rot    = ident();      // matrix3

float m  = f@mask;       // read back (type must match on first bind)
```

Writing to `@name` **creates** the attribute if it does not exist; reading a missing attribute yields zero/empty. Declare the type on first use — a later mismatched prefix errors.

Group membership reads/writes as an int attribute via the `@group_` prefix:

```vex
i@group_high = @P.y > 100;   // membership: nonzero = in group "high"
if (@group_wall) { @Cd = {1,0,0}; }
```

---

## Core functions

```vex
float d  = length(@P);              // magnitude
vector u = normalize(@v);           // unit vector
float k  = dot(@N, {0,1,0});        // projection / cosine
vector c = cross(u, {0,1,0});       // perpendicular
float g  = distance(@P, point(1,"P",0));

// remap
float a = fit(x, 0, 100, 0, 1);     // arbitrary in-range → out-range
float b = fit01(x, -1, 1);          // 0..1 → -1..1
float e = fit11(x, 0, 1);           // -1..1 → 0..1
float f = clamp(x, 0, 1);
vector L = lerp(@Cd, {1,1,1}, 0.5); // linear blend

// smoothing / ramps
float s = smooth(0, 1, x);          // smoothstep
float r = chramp("ramp", x);        // ramp parameter on the node

// channel references (create UI params on the wrangle)
float amp  = ch("amp");
float freq = chf("freq");
vector off = chv("offset");

// angles
float rad = radians(45);
float deg = degrees(rad);
```

`ch`/`chf`/`chv`/`chramp` reference parameters on the wrangle node itself — the user can then tweak values with sliders instead of re-pasting VEX.

---

## Noise

```vex
// scalar/vector value noise: amplitude * noise(P * frequency)
float n  = noise(@P * 0.1);            // 0..1-ish
vector vn = noise(@P * 0.1);           // vector-valued (noise has a vector overload)
float an = anoise(@P * 0.1);           // Perlin, signed-ish

// curl noise — divergence-free, great for velocity fields
vector c = curlnoise(@P * 0.5);
@v += c * ch("amp");

// hashed randoms (deterministic per seed)
float ra = rand(@ptnum);               // 0..1 from an int/float seed
float rb = random(@P);                 // 0..1 from a vector seed
vector rn = nrandom("twister");        // fresh random each call
```

Typical displacement pattern — amplitude scales output, frequency scales input:

```vex
float freq = chf("freq");   // e.g. 0.05
float amp  = chf("amp");    // e.g. 5.0
@P += @N * noise(@P * freq) * amp;
```

---

## Geometry lookups

Read attributes from any input geometry by element number:

```vex
vector p1 = point(1, "P", @ptnum);     // input 1, point attrib
vector cd = prim(0, "Cd", @primnum);   // input 0, primitive attrib
float  u  = vertex(0, "uv", @vtxnum);
int    n  = detail(1, "count", 0);     // input 1, detail attrib
```

Write attributes back onto geometry (typically from a detail wrangle or when targeting another element):

```vex
setpointattrib(0, "Cd", @ptnum, {1,0,0}, "set");
setprimattrib(0, "name", @primnum, "wall", "set");
```

Create / remove topology (detail or point wrangle):

```vex
int pt = addpoint(0, @P + {0,1,0});
int pr = addprim(0, "polyline", @ptnum, pt);
int vx = addvertex(0, pr, pt);
removepoint(0, @ptnum);                // second arg del-attached prims
removeprim(0, @primnum, 1);            // 1 = also delete unused points
```

Spatial queries:

```vex
int   near  = nearpoint(1, @P);              // nearest point in input 1
int[] knn   = nearpoints(1, @P, 0.5);        // all within radius
float dist  = xyzdist(1, @P, prim_id, uv);   // dist to nearest surface
vector sp   = primuv(1, "P", prim_id, uv);   // sample at that uv
```

Ray intersect:

```vex
vector hitP, hitUV;
int prim = intersect(1, @P, @N * -10, hitP, hitUV);  // -1 = miss
```

Point clouds:

```vex
int h = pcopen(1, "P", @P, 1.0, 32);         // handle: radius 1, max 32
vector avg = pcfilter(h, "Cd");              // averaged neighbor attrib
```

---

## Groups & selection

```vex
// create/set membership (int attribute, nonzero = member)
i@group_steep = degrees(acos(@N.y)) > 30;

// test membership in an existing group
if (inpointgroup(0, "wall", @ptnum)) @Cd = {1,0,0};

// set membership explicitly
setpointgroup(0, "keep", @ptnum, 1, "set");   // 0 removes
```

`i@group_x = expr;` is the fast, common way to build a group inside a wrangle.

---

## Common terrain / geo patterns

Mask by slope — flat ground vs steep faces from the up-component of the normal:

```vex
// N.y = 1 flat, 0 vertical. Steepness mask 0..1.
f@mask = 1.0 - clamp(@N.y, 0, 1);
```

Colorize by height:

```vex
@Cd = fit(@P.y, 0, 200, 0, 1);          // grayscale by elevation
@Cd = chramp("grade", fit01(@P.y, 0, 200));  // ramp-driven palette
```

Scatter-density from a mask (write `density`, feed a Scatter node's density attribute):

```vex
f@density = fit01(f@mask, 0, 1) * ch("max_density");
```

Displace along normal by noise (needs valid `@N` — see gotchas):

```vex
@P += @N * anoise(@P * chf("freq")) * chf("amp");
```

Transfer / read an attribute between inputs:

```vex
// input 1 provides reference geo at matching topology
@Cd = point(1, "Cd", @ptnum);
// or by the built-in alias
@Cd = v@opinput1_Cd;
```

Delete by condition (point wrangle):

```vex
if (@P.y < chf("water_level")) removepoint(0, @ptnum);
```

Compute a slope angle and simple curvature proxy:

```vex
f@slope = degrees(acos(clamp(@N.y, -1, 1)));   // degrees from horizontal
// curvature proxy: variance of neighbor normals
int h = pcopen(0, "P", @P, 1.0, 16);
vector navg = pcfilter(h, "N");
f@curv = 1.0 - length(navg);                   // 0 flat, →1 bumpy
```

Wall vs floor from normals (mirrors `segment_planar`'s intent):

```vex
// classify each point: floor if the normal points mostly up, else wall.
float upness = @N.y;                 // dot(N, up)
if (upness > chf("floor_thresh")) {  // e.g. 0.7
    i@class = 0;                     // floor
    i@group_floor = 1;
    @Cd = {0.2, 0.6, 1.0};
} else {
    i@class = 1;                     // wall
    i@group_wall = 1;
    @Cd = {1.0, 0.4, 0.2};
}
```

---

## Gotchas

- **Wrangle vs VOP.** A wrangle is textual VEX; an Attribute VOP is the node-graph form of the same language. This sheet is for wrangles. Both compile to VEX and share these functions.
- **Binding vs local variables.** `@name` and `f@name` bind geometry attributes (persist downstream); a plain `float x` is a local variable that vanishes at the end of the snippet. Prefix only what should persist.
- **`@N` must exist first.** Displacement, orientation, and copy-to-points rely on point normals. If `@N` is missing, `@N` reads as zero and displacement does nothing. Add a Normal node (or compute normals) upstream before a wrangle that reads `@N`.
- **Run over the right class.** `@P`/`@N` per point vs `@Cd` per prim behave differently by class. Reading `@primnum` in a point wrangle, or `@ptnum` in a detail wrangle, gives meaningless indices. Match Run Over to the attribute you touch.
- **`@Cd` needs to exist to show color.** Viewport color requires a `Cd` attribute; writing `@Cd` in a wrangle creates it. If nothing changes color, confirm the wrangle actually ran over the class that owns the geometry you see.
- **Export / read direction.** `point(1, ...)` **reads** from an input; `setpointattrib(0, ...)` **writes** to input 0. Reading an input never modifies it. In a point wrangle, writing `@attr` targets the current element on input 0 only.
- **First-bind type wins.** The first `@name` (or prefixed `x@name`) sets the attribute's type. A later mismatched prefix on the same name is an error — pick the type once.
- **Parallelism.** Point/prim/vertex wrangles run in parallel; do not depend on one element seeing another's writes within the same wrangle. Use a detail wrangle or a second wrangle for order-dependent work.

---

## KineFX rigs & skeletons

Rig wrangles in KineFX run over a skeleton's **points** — each point *is* a joint. A joint carries its
world orientation in `3@transform` (a matrix3) and its world position in `@P`; its transform relative
to its parent lives in `4@localtransform` (a matrix4). Bones are 2-point open polylines with vertex 0 =
parent and the last vertex = child, so hierarchy is walked through the point/prim connectivity. Use a
**Rig Attribute Wrangle** (`kinefx::rigattribwrangle`) — it exposes the KineFX attributes by name and
runs point-parallel like any Attribute Wrangle. Nothing here auto-propagates down the chain unless you
cascade it yourself (idiom *Cascade a delta to descendants*).

### World matrix of a joint
Compose a joint's `3@transform` + `@P` into a single 4×4 world matrix you can multiply points by.
Run over: Points
```vex
// KineFX stores a joint's world orientation in 3@transform (matrix3) and its world
// position in @P. Compose them into a single 4x4 world matrix.
matrix xform = matrix(ident());        // start from identity 4x4
xform = set(3@transform);              // rotation/scale block from the matrix3
setcomp(xform, @P.x, 3, 0);
setcomp(xform, @P.y, 3, 1);
setcomp(xform, @P.z, 3, 2);
4@world = xform;
```
`set(matrix3)` widens the 3×3 into the upper-left block of a 4×4; `setcomp(m, v, 3, c)` writes the
translation row. The KineFX pair (`3@transform`, `@P`) and the packed 4×4 hold the same information — the
matrix form is what you feed to `cracktransform`, `invert`, or a point multiply. Remember VEX matrices are
row-major, so translation sits in row 3 (`setcomp(..., 3, col)`).

### Find parent and hierarchy depth
Resolve each joint's parent point and how many hops it sits below the root.
Run over: Points
```vex
// Bones are 2-point open polylines with vertex 0 = parent, last vertex = child.
// Find the prim where this point is the child end; its first point is the parent.
int parent = -1;
foreach (int pr; pointprims(0, @ptnum)) {
    int pts[] = primpoints(0, pr);
    if (pts[-1] == @ptnum) { parent = pts[0]; break; }
}
i@parent = parent;
int depth = 0, cur = parent;
while (cur >= 0) {                      // climb to the root, counting hops
    int up = -1;
    foreach (int pr; pointprims(0, cur)) {
        int pts[] = primpoints(0, pr);
        if (pts[-1] == cur) { up = pts[0]; break; }
    }
    cur = up; depth++;
}
i@depth = depth;
```
`pointprims` gives the bones touching a joint; `primpoints(...)[-1] == @ptnum` tests whether this joint
is the *child* end of that bone, so its point 0 is the parent. Root joints have no bone where they are
the child, so `parent` stays −1. The `while` loop reuses that lookup to climb to the root — `depth` is the
generation index you key twist, colour, or falloff on.

### Convert world to local transform
Express a joint's world matrix in its parent's frame — the local transform an FK edit modifies.
Run over: Points
```vex
// A joint's local transform is its world matrix expressed in the parent's frame:
//   local = world * invert(parentWorld).  Root joints keep their world as local.
int parent = -1;
foreach (int pr; pointprims(0, @ptnum)) {
    int pts[] = primpoints(0, pr);
    if (pts[-1] == @ptnum) { parent = pts[0]; break; }
}
matrix world = set(3@transform);
setcomp(world, @P.x, 3, 0); setcomp(world, @P.y, 3, 1); setcomp(world, @P.z, 3, 2);
matrix pworld = ident();
if (parent >= 0) {
    matrix3 pr3 = point(0, "transform", parent);
    vector pp   = point(0, "P", parent);
    pworld = set(pr3);
    setcomp(pworld, pp.x, 3, 0); setcomp(pworld, pp.y, 3, 1); setcomp(pworld, pp.z, 3, 2);
}
4@localtransform = world * invert(pworld);
```
The identity `local = world · parentWorld⁻¹` is the heart of every FK/IK conversion. Reading the parent's
`transform`/`P` with `point(0, ...)` is safe because a wrangle input is immutable during the cook. If the
parent is −1 (root) the parent world stays identity, so local == world, which is exactly what KineFX
expects at the top of a chain.

### Rebuild world from local transform
The inverse trip — turn a `4@localtransform` back into the KineFX `3@transform` + `@P` pair.
Run over: Points
```vex
// Inverse of the previous idiom: world = local * parentWorld. Here parents are still at
// identity-ish world, so we read the parent's stored world to compose. Splits the 4x4 back
// into the KineFX pair (3@transform + @P) that the rest of the rig expects.
int parent = -1;
foreach (int pr; pointprims(0, @ptnum)) {
    int pts[] = primpoints(0, pr);
    if (pts[-1] == @ptnum) { parent = pts[0]; break; }
}
matrix pworld = ident();
if (parent >= 0) {
    matrix3 pr3 = point(0, "transform", parent);
    vector pp   = point(0, "P", parent);
    pworld = set(pr3);
    setcomp(pworld, pp.x, 3, 0); setcomp(pworld, pp.y, 3, 1); setcomp(pworld, pp.z, 3, 2);
}
matrix world = 4@localtransform * pworld;
@P = cracktransform(0, 0, 0, {0,0,0}, world);   // pull translation out of the 4x4
3@transform = matrix3(world);                    // rotation/scale block back to matrix3
```
`cracktransform(..., 0, ...)` extracts the translate component (mode 0 = translate, 1 = rotate,
2 = scale); `matrix3(world)` drops the translation row to leave the orientation block. Because parents are
read from input (not the just-written locals), do this on one generation at a time or in a solver if you
need true multi-level propagation. It's the write-back half of the world↔local round trip.

### Rotate a joint about its local axis
Twist a joint in place about its own axis without moving its pivot.
Run over: Points
```vex
// Pre-multiplying by a rotation applied in the joint's own frame twists it in place without
// moving @P. rotate() builds the delta about an arbitrary axis; ch() exposes a slider.
matrix3 x = 3@transform;
matrix3 spin = ident();
rotate(spin, radians(chf("angle")), chv("axis"));   // axis default {0,1,0}, angle in degrees
3@transform = spin * x;
```
`rotate(m, angle, axis)` mutates `m` in place, building a rotation about any unit axis; multiplying
`spin * x` applies it in the joint's current frame. `@P` is untouched, so the joint spins on the spot —
the atomic move behind pose tweaks and roll controls. Swap the multiply order (`x * spin`) to rotate in
world space instead.

### Aim a joint at a target
Point a joint's primary axis at a world-space target position.
Run over: Points
```vex
// Point the joint's primary axis at a world-space target. maketransform(zaxis, up) builds an
// orthonormal frame whose Z looks down 'aim'; swap the return's columns if your bone rolls
// along a different axis. Leaves @P untouched, so only orientation changes.
vector target = chv("target");           // e.g. {2, 3, 0}
vector aim = normalize(target - @P);
vector up  = {0, 1, 0};
3@transform = maketransform(aim, up);
```
`maketransform(zaxis, up)` returns a matrix3 whose Z axis follows `aim` and whose Y is `up`
orthogonalized against it — an instant look-at frame. This is the VEX core of an aim constraint; drive
`target` from another joint's `@P` to make one bone track another. If your bone's "forward" isn't Z, roll
the result by a fixed 90° or rebuild the axes with `set()`.

### Cascade a delta to descendants (FK)
Rotate a joint *and everything below it*, the way forward-kinematics propagates a pose.
Run over: Points
```vex
// Points are independent world transforms, so moving one joint does NOT move its children by
// itself. To get FK behaviour, build a delta about the driven joint and apply it to the joint
// and every descendant. Run this on ONE selected root joint (guarded by @name).
if (s@name == chs("joint")) {            // e.g. "spine"
    matrix3 delta = ident();
    rotate(delta, radians(chf("bend")), {0, 0, 1});
    vector pivot = @P;
    // gather this joint + all descendants by walking children forward
    int stack[] = array(@ptnum); int subtree[] = {};
    while (len(stack)) {
        int j = pop(stack); append(subtree, j);
        foreach (int pr; pointprims(0, j)) {
            int pts[] = primpoints(0, pr);
            if (pts[0] == j) append(stack, pts[-1]);   // child end
        }
    }
    foreach (int j; subtree) {
        vector jp = point(0, "P", j);
        matrix3 jx = point(0, "transform", j);
        setpointattrib(0, "P", j, pivot + (jp - pivot) * delta, "set");
        setpointattrib(0, "transform", j, jx * delta, "set");
    }
}
```
Because KineFX points are independent world transforms, editing one joint won't move its children — FK
is something you author. The `stack`/`subtree` loop is an iterative depth-first walk of the children
(prims where this joint is point 0). Rotating each descendant's offset about `pivot` and post-multiplying
its `transform` by `delta` rigidly swings the whole limb. Guard it with `@name` so it fires from exactly
one joint and use `setpointattrib` because you're writing to *other* points, not the current one.

### Blend two poses by weight
Mix a joint toward a second pose with correct (quaternion) orientation blending.
Run over: Points
```vex
// Blend the current pose toward a second pose stored in point attributes (transform2 / P2).
// Orientations must be blended as quaternions (slerp) -- lerping matrices shears them.
float w = chf("weight");                       // 0 = pose A, 1 = pose B
matrix3 a = 3@transform;
matrix3 b = 3@transform;                        // stand-in: same rig, swap for a 2nd input
vector4 qa = quaternion(a), qb = quaternion(b);
3@transform = qconvert(slerp(qa, qb, w));
@P = lerp(@P, @P, w);                            // positions lerp linearly
```
The rule that matters: **orientations blend as quaternions, not matrices** — `slerp` walks the shortest
arc at constant angular speed, whereas lerping two rotation matrices shears the frame. `quaternion(m3)`
converts a matrix3 to a quaternion and `qconvert` converts back. Wire pose B in as a second input and
read `point(1, "transform", @ptnum)` / `point(1, "P", @ptnum)` in place of the stand-ins to blend two
real poses; positions are safe to `lerp`.

### Mirror a pose across X
Reflect a joint to the opposite side of the YZ plane, keeping the frame consistent.
Run over: Points
```vex
// Reflect a joint to the opposite side of the YZ plane. Position flips in X; the orientation
// is conjugated by the reflection so the frame stays right-handed-consistent for the mirror.
matrix3 M = set(-1,0,0, 0,1,0, 0,0,1);          // reflection across X
@P = @P * M;
3@transform = M * 3@transform * M;              // similarity transform keeps it orthonormal-ish
```
Reflecting a rotation isn't just flipping a sign — you conjugate it (`M · R · M`) so the orientation is
mirrored consistently with the position. A pure reflection has determinant −1, so for a clean symmetric
rig you'd usually also match joints by name (e.g. `arm_L` ↔ `arm_R`) and copy the reflected transform
onto the twin. This is the transform math at the centre of any mirror-pose tool.

### Look up a joint by name
Find a joint by its `name` string instead of its unstable point number.
Run over: Points
```vex
// Names are the stable handle in KineFX (ptnum reorders). findattribval locates the point whose
// 'name' equals a target, so a control joint can drive another by name rather than index.
int head = findattribval(0, "point", "name", "head");
if (@ptnum == head) {
    @P += chv("offset");                         // nudge just the named joint
}
i@head_pt = head;                                // handy for debugging the lookup
```
`findattribval(input, "point", "name", value)` returns the point number whose `name` equals `value`, or
−1 if none — the stable way to address a joint, since point numbers reshuffle when a rig is rebuilt.
Guarding an edit with `@ptnum == head` targets exactly one joint. For repeated lookups in the same
wrangle, cache results rather than re-scanning per point.

### Bone length and stretch
Measure the bone to a joint's parent and re-length it — the core of stretchy IK.
Run over: Points
```vex
// Measure the bone from this joint to its parent, then scale the child's offset to a target
// length -- the building block of stretchy IK. @bonelen is written for inspection.
int parent = -1;
foreach (int pr; pointprims(0, @ptnum)) {
    int pts[] = primpoints(0, pr);
    if (pts[-1] == @ptnum) { parent = pts[0]; break; }
}
if (parent >= 0) {
    vector pp = point(0, "P", parent);
    vector dir = @P - pp;
    float len = length(dir);
    f@bonelen = len;
    float target = len * chf("stretch");         // 1.0 = unchanged
    @P = pp + normalize(dir) * target;
} else {
    f@bonelen = 0;
}
```
The bone is just the vector from the parent's `@P` to this joint; `length` measures it and
`pp + normalize(dir) * target` re-seats the child at a new distance along the same direction. Set
`stretch` from a ratio (current chain length / rest length) and you have the squash-and-stretch term of a
stretchy IK setup. Doing this parent-relative keeps the joint on its bone axis rather than drifting.

### Distribute twist along a chain
Spread a total roll evenly across a chain so no single joint pops.
Run over: Points
```vex
// Spread a total roll evenly across a chain by depth so no single joint pops. Each joint rolls
// by (depth / maxdepth) * total about its own aim axis. Uses the depth walk from idiom #2.
int depth = 0, cur = @ptnum;
while (1) {
    int up = -1;
    foreach (int pr; pointprims(0, cur)) {
        int pts[] = primpoints(0, pr);
        if (pts[-1] == cur) { up = pts[0]; break; }
    }
    if (up < 0) break;
    cur = up; depth++;
}
float frac = float(depth) / max(1, @numpt - 1);
matrix3 roll = ident();
rotate(roll, radians(chf("total_twist")) * frac, {0,1,0});
3@transform = roll * 3@transform;
i@depth = depth;
```
Distributing `total_twist` by `depth / maxdepth` gives each joint a fraction of the roll, so a wrist
twist blends smoothly up the forearm instead of snapping at one joint. The `while` loop is the same
root-climb as the hierarchy idiom, reused inline. For a branching rig, normalize by per-branch length
rather than `@numpt` so separate limbs twist independently.

### Copy-constrain one joint to another
Make one joint inherit another's world transform plus a fixed offset — a parent constraint in VEX.
Run over: Points
```vex
// A copy/parent constraint: make the driven joint inherit a source joint's world transform plus
// a fixed local offset. Read the source by name, compose offset * source into the driven frame.
if (s@name == chs("driven")) {                   // e.g. "head"
    int src = findattribval(0, "point", "name", chs("source"));  // e.g. "chest"
    if (src >= 0) {
        matrix3 srcx = point(0, "transform", src);
        vector  srcp = point(0, "P", src);
        matrix3 offset = ident();
        rotate(offset, radians(chf("offset_roll")), {0,1,0});
        3@transform = offset * srcx;
        @P = srcp + chv("offset_pos");
    }
}
```
A copy/parent constraint is just "adopt the source's transform, then apply my offset." Reading the source
by name (`findattribval`) keeps the link stable across rebuilds. `offset * srcx` layers a fixed local
rotation on top of the inherited orientation; add `offset_pos` for a positional offset. Extend it with a
blend weight (`slerp` toward the source) for a weighted constraint.

### Inspect and normalize capture weights
Read per-point skin (`boneCapture`) weights and derive a normalized dominant-influence mask.
Run over: Points (on the captured geometry, not the skeleton)
```vex
// Skinned geometry carries per-point boneCapture weights (region index + weight pairs). Read
// them as a float array, sum, and write a normalized dominant weight for masking / debug.
// Run on the CAPTURED geometry (the tube), not the skeleton.
float caps[] = point(0, "boneCapture", @ptnum);
float total = 0, best = 0;
for (int i = 1; i < len(caps); i += 2) {         // odd slots hold the weights
    total += caps[i];
    best = max(best, caps[i]);
}
f@capture_sum = total;
f@capture_dom = total > 0 ? best / total : 0;    // 0..1 dominant-bone influence
```
`boneCapture` packs alternating (region-index, weight) pairs into one float array per point, so the
weights sit at the odd indices — stepping `i += 2` from 1 sums them. `capture_dom` (largest weight over
the total) is a cheap "how single-bone is this point" mask, handy for finding seams or driving deform
falloff. Normalizing by the sum guards against captures that don't already add to 1.

---

## Curves & polylines

These idioms run over the **points** (or **primitives**) of polyline curves. The recurring move is to
find a point's place *along its own strand* from the primitive's ordered point list — `pointprims` gives
the curve a point belongs to, `primpoints`/`primvertices` give that curve's points in order, and `find`
locates the point's index within them. Working through topology (rather than assuming a global point
order) means these patterns survive multiple curves in one detail and arbitrary point numbering.

### Tangent from neighbours
Estimate a curve point's direction from the points either side of it.
Run over: Points
```vex
// A curve point's tangent is the direction through its neighbours. Use the prim's point list to
// find the previous/next point along THIS curve, with one-sided differences at the endpoints.
int pr = pointprims(0, @ptnum)[0];
int pts[] = primpoints(0, pr);
int i = find(pts, @ptnum);
vector prevP = point(0, "P", pts[max(i-1, 0)]);
vector nextP = point(0, "P", pts[min(i+1, len(pts)-1)]);
v@tangent = normalize(nextP - prevP);
```
A central difference (`next − prev`) is a smoother tangent than a one-sided step; clamping the indices
with `max`/`min` collapses it to a one-sided difference at the two ends. Because the neighbours come from
`primpoints`, the tangent respects the strand — it won't jump to a different curve that happens to be
nearby. This is the seed for `@N`, orient frames, and sweep cross-sections.

### Parametric u along the curve
Author a 0..1 parameter per point from its vertex order within its curve.
Run over: Points
```vex
// Author a 0..1 parameter per point from its vertex order within its own primitive -- the raw
// material for ramps, tapers and matched-u sampling. Robust to multiple curves in one detail.
int pr = pointprims(0, @ptnum)[0];
int vtxs[] = primvertices(0, pr);
int nv = len(vtxs), idx = 0;
for (int i = 0; i < nv; i++)
    if (vertexpoint(0, vtxs[i]) == @ptnum) { idx = i; break; }
f@curveu = nv > 1 ? float(idx) / (nv - 1) : 0;
```
Walking the primitive's vertices and matching `vertexpoint` back to this point gives its ordinal position
on the strand, which divided by `nv − 1` is a normalized parameter. This is an *index-based* u (even
spacing per point); for a true arc-length u, pair it with the cumulative-length idiom below. Every ramp,
taper, and cross-section lookup keys off this value.

### Cumulative arc length
Stamp a running arc length onto every point and the total length onto each curve.
Run over: Primitives
```vex
// Walk each curve's points IN ORDER, accumulating segment lengths, and stamp a running arc
// length onto every point. Run over PRIMITIVES so each strand is summed independently; write to
// points with setpointattrib. The per-prim total lands in f@curvelen.
int pts[] = primpoints(0, @primnum);
float acc = 0;
setpointattrib(0, "arclen", pts[0], 0.0, "set");
for (int i = 1; i < len(pts); i++) {
    vector a = point(0, "P", pts[i]);            // bind to vector so distance() isn't ambiguous
    vector b = point(0, "P", pts[i-1]);
    acc += distance(a, b);
    setpointattrib(0, "arclen", pts[i], acc, "set");
}
f@curvelen = acc;
```
Running over primitives lets you walk each strand's points in order and accumulate true segment lengths —
something a point-parallel wrangle can't do, since points don't see each other. `setpointattrib` writes
the running total back onto each point. Bind the `point()` reads to `vector` locals first, otherwise
`distance()` is ambiguous about which vector width you mean. Divide `arclen` by `curvelen` for an
arc-length-accurate 0..1 parameter.

### Build a per-point frame
Turn a tangent + reference up into a `@orient` quaternion for copy-to-points.
Run over: Points
```vex
// Turn a tangent + a reference up into an orthonormal frame (a quaternion @orient ready for
// copy-to-points). Ortho-normalize up against the tangent so the frame stays square; maketransform
// packs the three axes into a matrix which quaternion() converts to @orient.
int pr = pointprims(0, @ptnum)[0];
int pts[] = primpoints(0, pr);
int i = find(pts, @ptnum);
vector tan = normalize(point(0, "P", pts[min(i+1,len(pts)-1)]) - point(0, "P", pts[max(i-1,0)]));
vector up  = v@up;
vector side = normalize(cross(up, tan));
up = cross(tan, side);                            // re-orthogonalize
matrix3 frame = set(side, up, tan);               // columns: x=side, y=up, z=tangent
p@orient = quaternion(frame);
```
Two crosses build a clean orthonormal basis: `side = up × tan`, then `up = tan × side` fixes any
non-perpendicularity in the supplied up. `set(side, up, tan)` packs the axes into a matrix3 and
`quaternion()` converts it to the `p@orient` that copy-to-points reads. A fixed world up will flip where
the tangent passes vertical — for a twist-stable frame, carry the previous point's up forward (parallel
transport) instead.

### Taper width along the curve
Drive `@pscale` from a ramp along the curve for tapered sweeps/polywires.
Run over: Points
```vex
// Drive @pscale from the parametric u through a ramp so a downstream Sweep / PolyWire tapers.
// Recompute u inline so the idiom stands alone; chramp("profile", u) is the artist-tunable curve.
int pr = pointprims(0, @ptnum)[0];
int vtxs[] = primvertices(0, pr);
int nv = len(vtxs), idx = 0;
for (int i = 0; i < nv; i++)
    if (vertexpoint(0, vtxs[i]) == @ptnum) { idx = i; break; }
float u = nv > 1 ? float(idx) / (nv - 1) : 0;
@pscale = chramp("profile", u) * chf("width");
```
`chramp("profile", u)` exposes a ramp parameter on the wrangle, so an artist shapes the taper (fat root,
thin tip, bulges) with a curve instead of code. A downstream Sweep or PolyWire reads `@pscale` as its
radius, giving per-point thickness. Feed `u` from `arclen / curvelen` instead of the index if you want the
taper measured in real distance.

### Detect endpoints vs interior
Tag the open ends of curves versus their interior points.
Run over: Points
```vex
// A point sitting at the end of an open polyline connects to exactly one neighbour. Count the
// point's unique neighbours to tag ends, interior points, and (for later) branch points.
int nb[] = neighbours(0, @ptnum);
int deg = len(nb);
i@is_end = (deg == 1);
i@degree = deg;
if (deg == 1) @Cd = {1,0,0};
else if (deg == 2) @Cd = {0.6,0.6,0.6};
```
`neighbours` returns the connected points, so its length is the point's degree: 1 at an open end, 2 along
a span, 3+ at a fork. Endpoints are where you cap geometry, seed growth, or pin a wire. Storing `degree`
outright saves recomputing it for the branch-classification idiom.

### Classify branch points
Sort curve points into tips, spans, and forks for branching networks.
Run over: Points
```vex
// On a wire/tree network, a point with 3+ neighbours is a fork. Classify each point so branches
// can be split, coloured, or seeded differently. @branch = number of extra limbs at a fork.
int deg = len(neighbours(0, @ptnum));
i@class = deg == 1 ? 0 : (deg == 2 ? 1 : 2);      // 0 tip, 1 span, 2 fork
i@branch = max(0, deg - 2);
@Cd = set(deg >= 3, deg == 1, deg == 2);
```
Degree cleanly separates the three cases on any wire graph — tips (1), spans (2), forks (3+) — and
`deg − 2` counts how many extra limbs leave a fork. This is the classifier you run before splitting a tree
into individual branches or scattering differently on trunks versus twigs. The `@Cd = set(...)` line is a
quick visual check in the viewport.

### Per-curve id for variation
Give every strand a stable id and hashed random for per-curve variation.
Run over: Points
```vex
// Stamp each point with the primitive (strand) it belongs to, plus a hashed random so every
// curve gets a stable, distinct value for width/colour/seed variation.
int pr = pointprims(0, @ptnum)[0];
i@curveid = pr;
f@curverand = rand(pr * 17 + 3);
@Cd = set(f@curverand, frac(f@curverand*7), frac(f@curverand*13));
```
The primitive number is a stable per-strand id (every point on a curve shares it), and hashing it through
`rand` gives a repeatable 0..1 value unique to that curve. Use `curverand` to vary width, colour, or a
seed so a bundle of curves doesn't look uniform. `frac(rand * k)` cheaply spins one random into a few
decorrelated channels.

### Sample another curve at matching u
Read a companion curve at the same parameter to build ribs, lofts, or offsets.
Run over: Points (second curve wired into input 1)
```vex
// Read a companion curve at the same parametric u to build ribs / lofts. primuv samples input 1
// at (u, primitive); here input 1 is the same detail, primitive 1 is the offset arc B.
int pr = pointprims(0, @ptnum)[0];
int vtxs[] = primvertices(0, pr);
int nv = len(vtxs), idx = 0;
for (int i = 0; i < nv; i++)
    if (vertexpoint(0, vtxs[i]) == @ptnum) { idx = i; break; }
float u = nv > 1 ? float(idx) / (nv - 1) : 0;
int otherprim = 1;                                // arc B
vector opposite = primuv(1, "P", otherprim, set(u, 0, 0));
v@rib = opposite - @P;                            // vector spanning to the matched point
```
`primuv(1, "P", prim, {u,0,0})` evaluates the *continuous* position along another curve at parameter u —
so the two strands don't need matching point counts. The difference vector `opposite − @P` is a rib you
could add geometry along, or the offset for a lofted surface. Point `otherprim` at whichever primitive is
your companion curve (or derive it per strand).

### Project onto the nearest curve
Snap arbitrary points onto the closest position on a set of polylines.
Run over: Points (curves wired into input 1)
```vex
// Snap arbitrary points to the closest position ON a set of polylines (input 1). xyzdist returns
// the nearest prim + its uv; primuv then evaluates the exact surface point to snap or measure to.
int prim; vector uv;
float d = xyzdist(1, @P, prim, uv);
vector oncurve = primuv(1, "P", prim, uv);
f@curvedist = d;
v@snapped = oncurve;
@P = lerp(@P, oncurve, chf("snap"));              // snap = 1 fully projects
```
`xyzdist` finds the nearest primitive and fills its parametric `uv`; feeding that back through `primuv`
gives the exact closest point *on* the curve, not just the nearest vertex. `curvedist` is the perpendicular
distance — a ready-made falloff for wrapping geometry to a spline. The `lerp` lets you dial the projection
from a gentle pull (`snap` small) to a hard snap (`snap` = 1).

### Smooth along the curve
Relax a value by averaging with the two curve neighbours, respecting strand topology.
Run over: Points
```vex
// Relax a value by averaging with the two curve neighbours -- a 1D blur that respects strand
// topology (won't bleed between separate curves). Iterate the wrangle for stronger smoothing.
int pr = pointprims(0, @ptnum)[0];
int pts[] = primpoints(0, pr);
int i = find(pts, @ptnum);
vector a = point(0, "P", pts[max(i-1,0)]);
vector b = point(0, "P", pts[min(i+1,len(pts)-1)]);
vector avg = (a + @P + b) / 3.0;
@P = lerp(@P, avg, chf("smooth"));
```
Averaging each point with its two strand-neighbours is a one-dimensional blur that follows the curve, so
separate curves never bleed into each other. `lerp(@P, avg, smooth)` controls the strength; chain several
wrangles (or raise a loop count) for heavier relaxing. Swap `@P` for any attribute — width, colour,
temperature — to smooth data along a spline.

---

## Matrices & quaternions

The rotation/space toolkit the rest of the cookbook leans on. A **matrix3** (`3@`) is a pure
rotation/scale basis; a **matrix4** (`4@`) adds translation; a **quaternion** is a `vector4` (`p@`) that
stores an orientation compactly and blends correctly with `slerp`. Two prefix gotchas worth pinning:
`N@` for a numeric prefix means an **N×N matrix** (`2@`, `3@`, `4@`), while vectors are `u@` (vector2),
`v@` (vector3) and `p@` (vector4) — there is no `9@`/`16@`. VEX matrices are row-major, so translation
lives in the last row. These run over **points** but the math is context-free.

### Build a transform from T/R/S
Assemble a 4×4 from translate, rotate, and scale in the right order.
Run over: Points
```vex
// Assemble a 4x4 from translate/rotate/scale. Order matters: scale, then rotate, then translate
// so the object scales in its own frame before being placed. rotate() mutates the matrix in place.
matrix m = ident();
scale(m, chv("scale"));                            // e.g. {1,2,1}
rotate(m, radians(chf("rz")), {0,0,1});
translate(m, chv("translate"));
4@xform = m;
@P *= m;                                            // apply to the point for a visible check
```
`scale`, `rotate`, and `translate` each *pre-multiply* the matrix in place, so calling them in
scale→rotate→translate order applies them in that intuitive order to a point. Reverse the order and the
object orbits the origin instead of spinning in place. `@P *= m` is the point transform; this is the same
matrix a Transform SOP builds, authored in code.

### Rotate a vector about an axis
Spin a vector about an arbitrary axis via a matrix or a quaternion.
Run over: Points
```vex
// Two equivalent routes to spin a vector about an axis: a rotation matrix, or a quaternion via
// qrotate (cheaper to compose/slerp). Both leave length unchanged.
vector axis = normalize(chv("axis"));              // default {0,1,0}
float ang = radians(chf("angle"));
matrix3 R = ident(); rotate(R, ang, axis);
v@byMatrix = @N * R;
v@byQuat   = qrotate(quaternion(ang, axis), @N);
```
The matrix route (`rotate` a matrix3, then `v * R`) and the quaternion route (`qrotate`) give identical
results; both preserve length. Reach for the quaternion when you'll blend or accumulate rotations —
`slerp` and `qmultiply` are cleaner and drift-free compared with matrix math. `quaternion(angle, axis)`
is the axis-angle constructor.

### Quaternions three ways
Author a quaternion from axis+angle, from euler, or as the shortest arc between two vectors.
Run over: Points
```vex
// Three common ways to author a quaternion: from an axis+angle, from euler angles (via a matrix),
// and the rotation that carries one direction onto another (dihedral -> the shortest arc).
vector4 qAxis  = quaternion(radians(chf("angle")), {0,1,0});
vector4 qEuler = eulertoquaternion(radians(chv("euler")), 0);   // already a vector4 quaternion
vector4 qTwo   = dihedral(@N, normalize(chv("target") - @P));
p@q = qmultiply(qTwo, qAxis);                      // compose them (right-to-left)
p@qe = qEuler;
```
`quaternion(angle, axis)` is axis-angle; `eulertoquaternion(radians, order)` converts XYZ euler angles
(the second arg is the rotation order); `dihedral(a, b)` is the shortest rotation taking direction `a` onto
`b` — the go-to for "align this to that." `qmultiply` composes rotations right-to-left, so `qTwo * qAxis`
applies `qAxis` first. Quaternions compose without the gimbal problems of stacked euler rotations.

### Slerp between orientations
Blend two rotations along the shortest arc at constant speed.
Run over: Points
```vex
// Spherical-linear interpolation blends two rotations along the shortest arc at constant speed --
// the correct way to mix orientations (a matrix lerp would shear). Feeds @orient for instancing.
vector4 qa = quaternion(radians( 0.0), {0,1,0});
vector4 qb = quaternion(radians(90.0), {0,1,0});
p@orient = slerp(qa, qb, chf("t"));                // t 0..1
```
`slerp` is the correct orientation blend: constant angular velocity along the shortest arc, which a
component-wise lerp of matrices or even quaternions can't guarantee. Driving `t` from a mask, falloff, or
`@curveu` blends smoothly between two poses or aim directions. The result drops straight into `p@orient`
for copy-to-points.

### Decompose a matrix into T/R/S
Pull translate, rotate, and scale back out of a 4×4.
Run over: Points
```vex
// Pull translate / rotate / scale back out of a 4x4. cracktransform is the inverse of building
// one; the rotation it returns is in degrees. Useful for reading a packed or captured transform.
matrix m = ident();
scale(m, {1, 2, 3});
rotate(m, radians(30), {0,0,1});
translate(m, {5, 0, 0});
v@t = cracktransform(0, 0, 0, {0,0,0}, m);         // translate
v@r = cracktransform(0, 0, 1, {0,0,0}, m);         // rotate (degrees)
v@s = cracktransform(0, 0, 2, {0,0,0}, m);         // scale
```
`cracktransform(trs, rot, component, pivot, m)` reads one channel out of a matrix — the fourth-from-last
arg picks translate (0), rotate (1), or scale (2), and the returned rotation is in **degrees**. It's the
inverse of `scale`/`rotate`/`translate` and how you inspect a packed-primitive intrinsic or a captured
joint transform. Watch the degrees/radians boundary: you build with `radians`, but crack returns degrees.

### Point vs direction vs normal transform
Transform positions, directions, and normals correctly under non-uniform scale.
Run over: Points
```vex
// A 4x4 moves POINTS (rotation + translation). Directions ignore translation -- use the 3x3 part.
// Normals need the INVERSE-TRANSPOSE so they stay perpendicular under non-uniform scale.
matrix m = ident();
scale(m, {1, 3, 1});
translate(m, {2, 0, 0});
matrix3 basis = matrix3(m);
v@pointT  = @P * m;                                // full transform
v@dirT    = @N * basis;                            // direction: rotation/scale only
v@normalT = normalize(@N * transpose(invert(basis)));  // correct normal transform
```
Three different rules for three different quantities: a **point** gets the full 4×4 (rotation +
translation), a **direction** gets only the 3×3 basis (no translation), and a **normal** must use the
inverse-transpose of the basis or it stops being perpendicular to the surface under non-uniform scale.
`matrix3(m)` grabs the basis from the 4×4. Getting the normal rule wrong is a classic source of shading
errors after a squash.

### World to unit-bbox space
Normalize positions into 0..1 across the geometry's bounding box.
Run over: Points
```vex
// Normalize positions into 0..1 over the geometry's bounding box -- a change of space handy for
// procedural masks and triplanar coords. getbbox returns the min/max corners of input 0.
vector bmin, bmax;
getbbox(0, bmin, bmax);
vector local = (@P - bmin) / (bmax - bmin);        // 0..1 across the bbox
v@uvw = clamp(local, 0, 1);
@Cd = v@uvw;
```
`getbbox` fills the min/max corners of the input, and rescaling `@P` by that span maps the whole object
into a 0..1 cube regardless of its world size or position. This bbox-local space is the basis for
resolution-independent gradients, triplanar coordinates, and masks that follow the geometry. Divide-by-zero
is only a risk on a perfectly flat axis, where you'd guard the span.

### Look-at aim matrix
Build an orientation that aims one axis at a target with a chosen up.
Run over: Points
```vex
// Build a frame that aims one axis at a target with a chosen up. lookat returns a matrix3 whose
// -Z (camera style) points from @P to the target; feed it to @orient or copy it into a transform.
vector target = chv("target");                     // e.g. {0, 5, 0}
matrix3 m = lookat(@P, target, {0,1,0});
p@orient = quaternion(m);
3@aim = m;
```
`lookat(from, to, up)` returns the matrix3 that aims toward the target — camera-style, so −Z points along
the view direction. Convert it to `p@orient` for instancing, or keep the matrix to transform geometry.
`lookat` and `maketransform` overlap; `lookat` takes explicit from/to positions, which is convenient when
the target is another point's `@P`.

### Signed angle, projection, reflection
The everyday dot/cross recipes: signed angle between vectors, projection, and reflection.
Run over: Points
```vex
// The everyday dot/cross toolkit. Signed angle uses atan2(|axb|, a.b) with a reference axis for
// sign; projection drops a vector onto another; reflection bounces it off a plane normal.
vector a = normalize(@N);
vector b = normalize(chv("ref") + {0.001,0,0});
float signedAng = degrees(atan2(length(cross(a,b)), dot(a,b))) * sign(dot(cross(a,b), {0,1,0}));
vector proj = dot(a, b) * b;                        // component of a along b
vector refl = reflect(a, {0,1,0});                 // reflect across the ground plane
f@ang = signedAng;
v@proj = proj;
v@refl = refl;
```
`atan2(|a×b|, a·b)` is a more robust angle than `acos(dot)` near 0° and 180°; multiplying by the sign of
`(a×b)·axis` turns the unsigned angle into a signed one about a reference axis. `dot(a,b)*b` projects `a`
onto `b`, and `reflect` mirrors a vector across a plane normal (bounce, mirror-ray). These three are the
backbone of most vector-geometry masks.

### Polar and spherical conversions
Convert between cartesian and angular coordinates for radial layouts and dome sampling.
Run over: Points
```vex
// Convert between cartesian and angular coordinates -- the basis for radial layouts and dome
// sampling. theta = azimuth around Y, phi = elevation from the XZ plane.
float r     = length(@P);
float theta = atan2(@P.z, @P.x);                   // azimuth
float phi   = r > 0 ? asin(@P.y / r) : 0;          // elevation
f@radius = r; f@theta = theta; f@phi = phi;
// round-trip back to cartesian
v@roundtrip = set(r*cos(phi)*cos(theta), r*sin(phi), r*cos(phi)*sin(theta));
```
`atan2(z, x)` gives the azimuth around Y and `asin(y/r)` the elevation, decomposing a position into
(radius, angles). Working in angular space makes radial arrays, spiral placement, and hemisphere sampling
trivial; the round-trip block shows the inverse mapping back to XYZ. Guard `asin` against `r == 0` to avoid
a divide-by-zero at the origin.

### Wrap angles and shortest blend
Wrap angles into (−180, 180] so interpolation takes the short way round.
Run over: Points
```vex
// Angle bookkeeping: wrap any angle into (-180,180] so interpolation takes the short way round,
// then blend two headings without the 359->1 degree jump.
float a = ch("from"), b = ch("to");                // degrees
float diff = b - a;
diff -= 360 * floor((diff + 180) / 360);           // wrap to (-180,180]
f@blended = a + diff * chf("t");
```
The `diff -= 360 * floor((diff + 180) / 360)` line folds any difference into (−180, 180], so blending from
359° to 1° crosses the short 2° gap instead of unwinding 358° the wrong way. This is the scalar cousin of
`slerp` — use it for headings, wheel spin, or any angle you interpolate. Feeding the wrapped `diff` into a
lerp gives the shortest-arc blend.

### Orient from velocity
Build a motion-aligned orientation from `@v` for debris and sparks.
Run over: Points
```vex
// Build an orientation that rides the velocity direction -- motion-aligned instancing (debris,
// sparks, arrows). Aim Z down @v, keep a stable up, and pack to @orient. Falls back to identity
// where speed is ~0 so still points don't flip.
vector vel = v@v;
if (length(vel) > 1e-4) {
    vector aim = normalize(vel);
    vector up  = {0,1,0};
    p@orient = quaternion(maketransform(aim, up));
} else {
    p@orient = {0,0,0,1};
}
```
Aiming a frame down the velocity direction makes instanced copies (debris, sparks, arrows, fish) point
where they're heading. The speed guard matters: at near-zero velocity the direction is undefined, so
falling back to the identity quaternion `{0,0,0,1}` stops still points from snapping to a random
orientation. Swap `maketransform` for `dihedral` from a rest axis if you'd rather rotate a known model
axis onto `@v`.

---

## RBD & destruction

VEX in a destruction sim almost always runs in a **Geometry Wrangle inside a SOP Solver** (per-frame feedback on the piece and constraint geometry) or in an **Attribute Wrangle before the sim** (pre-authoring glue strength, clusters, stable names). The two geometries you touch: the *pieces* (points/packed prims, one per fractured chunk) and the *constraint network* (a set of 2-point polylines, each bridging two pieces, carrying `strength` / `constraint_name` / a solver-measured `force`). Break glue by driving a constraint's `strength` to 0; wake a piece by setting `i@active = 1`. All snippets below were verified in an Attribute Wrangle over a fractured-piece + constraint-network fixture (the identical VEX a Geometry Wrangle runs in the solver).

### Break a glue constraint when measured force beats its strength
The canonical conditional break — retire a constraint the frame its load exceeds what it can hold.
Run over: Primitives (constraint network)
```vex
// Constraint prims carry a solver-measured `force`; snap glue past its strength.
float f = f@force;
float s = f@strength;
if (s > 0.0 && f > s * chf("safety")) {
    f@strength = 0.0;          // 0 strength = broken to the RBD solver
    i@group_justbroke = 1;     // tag this frame's fresh breaks for debug
}
```
The RBD Bullet solver writes an accumulated `force` onto each glue constraint; comparing it to that constraint's own `strength` and zeroing `strength` on failure is what "break on threshold" means mechanically. The `safety` channel scales the trip point so you can dial fragility without re-fracturing. Do this in a SOP Solver so the zeroed strength feeds the next frame; the `justbroke` group is handy for coloring or emitting debris exactly where glue let go.

### Fatigue constraints: bleed strength down every frame
Progressive weakening so a structure sags and fails over time instead of snapping instantly.
Run over: Primitives (constraint network)
```vex
// Inside a SOP Solver this feeds back: strength erodes a little each frame.
float rate = chf("weaken_per_frame");   // e.g. 400
f@strength = max(f@strength - rate, 0.0);
if (f@strength <= 0.0) i@group_fatigued = 1;
```
Because a SOP Solver reads its own previous-frame output, subtracting a fixed `rate` each step integrates into a linear decay of holding strength. `max(..., 0.0)` keeps strength from going negative (which some solvers read as "unbreakable"). Multiply `rate` by a per-constraint mask or by proximity to a load point to make some seams fatigue faster than others.

### Wake a piece static -> dynamic when a trigger crosses
Activate a resting chunk once an incoming signal (impact, painted value, proximity) passes a threshold.
Run over: Points (pieces)
```vex
// Flip a resting piece to active once an incoming trigger passes threshold.
if (!i@active && f@trigger > chf("wake_level")) {
    i@active = 1;
    i@group_woke = 1;
}
```
`i@active` is the RBD flag that moves a piece from the static (animated/held) set into the dynamic solve. Gating on `!i@active` makes the transition one-way — once awake it stays awake — and the `woke` group marks the frame of transition for secondary effects. The `trigger` attribute can be anything you author upstream: a transferred impact impulse, a distance field, or a hand-painted mask.

### Distance-delayed activation as a shock front expands
Wake pieces in a spreading ring from an impact point rather than all at once.
Run over: Points (pieces)
```vex
// Each piece wakes when the impact wave (units/frame) reaches its centroid.
vector impact = chv("impact_pos");
float speed = max(chf("wave_speed"), 1e-3);
float wake  = distance(@P, impact) / speed;   // frame this piece should wake
i@active = (@Frame >= wake) ? 1 : i@active;
```
Dividing the distance from the impact by a wave speed gives, per piece, the frame at which the front arrives; comparing that to `@Frame` staggers activation into an expanding shell. The ternary preserves any earlier activation (a piece already awake stays awake). Clamp `speed` away from zero so a piece sitting exactly on the impact point doesn't divide by nothing.

### Compare an attribute across a constraint's two endpoints
Constraint-side logic: read both pieces a constraint bridges and act on the pair.
Run over: Primitives (constraint network)
```vex
// A constraint prim is a 2-point polyline bridging two pieces; inspect both ends.
int pts[] = primpoints(0, @primnum);
if (len(pts) >= 2) {
    int ca = point(0, "cluster", pts[0]);
    int cb = point(0, "cluster", pts[1]);
    i@intercluster = (ca != cb);   // this constraint spans two glue clusters
}
```
`primpoints` returns the point numbers of the polyline's two ends, and `point(0, "cluster", pt)` fetches each connected piece's cluster id. Constraints whose ends differ are the seams *between* glued clusters — exactly the ones you want to break first, or assign a weaker glue type, to shatter along cluster boundaries. This two-point comparison is the general pattern for any constraint-network measurement (rest length change, relative velocity, differing materials).

### Pre-sim: ramp glue strength by distance from an epicenter
Author directed fragility before the solve so cracks radiate from a chosen point.
Run over: Primitives (constraint network)
```vex
// Weakest glue at the impact epicenter, strong far away -> directed shatter.
vector ep = chv("epicenter");
float r = max(chf("falloff"), 1e-3);
int pts[] = primpoints(0, @primnum);
vector c = (point(0, "P", pts[0]) + point(0, "P", pts[1])) * 0.5;  // constraint midpoint
float d = distance(c, ep);
f@strength = fit(clamp(d, 0.0, r), 0.0, r, chf("min_str"), chf("max_str"));
```
Averaging the two endpoint positions gives the constraint's midpoint, and `fit` remaps its distance-from-epicenter into a strength band — soft near the hit, strong beyond the falloff radius. Clamping the distance to `r` before the fit flattens strength to `max_str` everywhere outside the blast. This runs once as authoring (before the sim); combine it with the threshold-break idiom so the weakened seams are the ones that give way.

### Glue-cluster id from a quantized centroid
Cheap spatial clustering when you want glue islands without a Connectivity node.
Run over: Points (pieces)
```vex
// Bucket piece centroids into a grid to form clusters you can group/glue on.
float cell = max(chf("cluster_size"), 1e-3);
int cx = int(floor(@P.x / cell));
int cz = int(floor(@P.z / cell));
i@cluster = cx * 131071 + cz;   // fold two lattice coords into one stable id
i@group_cluster0 = (i@cluster == 0);
```
Flooring each coordinate by a cell size snaps nearby pieces to the same integer lattice cell; folding the two lattice indices with a large prime multiplier packs them into one collision-resistant cluster id. Cluster ids drive per-island glue strength, staged activation, or intra- vs inter-cluster constraint typing. For irregular chunk shapes prefer a real Connectivity/`@class`, but this hash is instant and fully deterministic.

### Kick + spin pieces the instant they are freed
Add outward linear and angular velocity on the frame a piece becomes dynamic.
Run over: Points (pieces)
```vex
// On the transition to active, add outward linear + angular velocity.
if (i@active && !i@was_active) {
    vector dir = normalize(@P - chv("impact_pos"));
    v@v += dir * chf("kick") + curlnoise(@P * 0.5) * chf("jitter");
    v@w += set(0.0, chf("spin"), 0.0);   // angular velocity about up
    i@was_active = 1;
}
```
The `i@active && !i@was_active` edge fires exactly once per piece — the frame it wakes — after which `was_active` latches it off. `v@v` is linear velocity and `v@w` is angular velocity (radians/sec about each axis) for RBD points; the curl-noise term adds incoherent jitter so freed pieces don't all launch identically. Keep `kick` modest — large injected velocities fight the solver and read as an explosion rather than a collapse.

### Debug-color pieces by how hard they were hit this frame
Turn a measured impulse into viewport color so you can read the impact map at a glance.
Run over: Points (pieces)
```vex
// Map a measured impulse to a ramp so hot hits read at a glance.
float k = fit(f@impulse, 0.0, chf("max_impulse"), 0.0, 1.0);
@Cd = set(chramp("impact_r", k), chramp("impact_g", k), chramp("impact_b", k));
```
Normalizing `impulse` into 0..1 with `fit` gives a lookup coordinate, and three separate ramp channels build an RGB gradient you can art-direct on the node. Debug coloring is one of the strongest reasons to reach for a wrangle in destruction — no typed tool can tint by an arbitrary solver-measured attribute. Swap `impulse` for `f@force`, relative velocity, or constraint count to visualize whatever you're tuning.

### Retire settled pieces below a speed for N held frames
Put slow pieces to sleep to cut solver cost, but only after they stay slow.
Run over: Points (pieces)
```vex
// Slow pieces accrue sleep frames; past a hold they drop back to static.
float sp = length(v@v);
if (i@active && sp < chf("sleep_speed")) {
    i@sleep_frames += 1;
    if (i@sleep_frames > chi("sleep_hold")) { i@active = 0; i@group_asleep = 1; }
} else {
    i@sleep_frames = 0;
}
```
A single-frame speed test is jittery, so this accumulates consecutive slow frames in `sleep_frames` and only deactivates after a hold count — a debounced sleep. Resetting the counter whenever the piece speeds back up prevents a briefly-slow chunk from freezing mid-tumble. Deactivating (`i@active = 0`) hands the piece back to the static set; the solver then skips it, which is a large speed-up on big shatters that mostly come to rest.

### Stamp a stable @id / @name at fracture time
Give every piece a permanent identity so caching, instancing, and lookups survive renumbering.
Run over: Points (pieces)
```vex
// Do this ONCE pre-sim (ptnum is stable here) so caching + instancing survive.
i@id = @ptnum;
s@name = sprintf("piece_%06d", i@id);
```
`@ptnum` is stable *at authoring time* but the solver and downstream ops can renumber points, so you capture identity into a persistent `@id` and a zero-padded string `@name` before the sim. `sprintf` with `%06d` produces sortable names (`piece_000007`) that match cleanly for transform-copy back onto high-res geometry and for per-piece instancing. The rule: assign identity once, up front — never re-derive it from `ptnum` inside the solve.

### Retire constraints whose both pieces have slept
Constraint-side counterpart to piece sleeping — stop simulating glue between two static chunks.
Run over: Primitives (constraint network)
```vex
// Deactivate-on-rest, constraint side: skip work once both ends are static.
int pts[] = primpoints(0, @primnum);
int a = point(0, "active", pts[0]);
int b = point(0, "active", pts[1]);
if (!a && !b) i@group_retired = 1;
```
Reading the `active` flag of each endpoint piece tells you whether a constraint still connects anything moving; if both ends are asleep the constraint can be grouped out of the solve. Pair this with the piece-sleep idiom so pieces and their glue retire together, keeping the active constraint set small as a collapse settles. Grouping (rather than deleting) keeps the network intact for re-waking if a late impact arrives.

---

## Pyro & smoke

Pyro VEX runs in a **Gas Field Wrangle** inside the pyro/smoke DOP network — once per voxel, with `@P` as the voxel's world position and each simulation field bound by name (`f@density`, `f@temperature`, `f@fuel`, `v@vel`). You read and write those fields in place to shape the sim: add emission, inject buoyancy, agitate velocity, dissipate, or author a shading field. The snippets below were verified in a Volume Wrangle over named `density`/`temperature`/`fuel`/`vel`/`source`/`mask`/`emission` volumes — a Volume Wrangle binds volumes by name with exactly the same `@field` syntax and per-voxel `@P` a Gas Field Wrangle uses, so the VEX ports over unchanged.

### Emit density + heat from a source field
Feed new smoke and temperature into the sim wherever an emission source is present.
Run over: Volumes (fields)
```vex
// Where the source field fires, raise density toward a target and inject heat.
float src = f@source;
if (src > chf("emit_thresh")) {
    f@density = max(f@density, src * chf("emit_amount"));
    f@temperature = max(f@temperature, chf("emit_temp"));
}
```
Testing the `source` field per voxel and taking `max` against existing density adds emission without erasing smoke already there (a plain assignment would flicker as the source moves). Injecting `temperature` alongside density is what makes emitted smoke rise on its own via buoyancy. Rasterize your emitter geometry into a `source` field upstream, or drive it from a `mask` field (see below) for painted control.

### Buoyancy: push hot voxels up through the velocity field
The core "smoke rises" force — add upward velocity proportional to temperature.
Run over: Volumes (fields)
```vex
// Hotter gas rises; add upward velocity proportional to temperature.
float t = f@temperature;
v@vel += set(0.0, 1.0, 0.0) * t * chf("buoyancy");
```
Writing straight into `v@vel` adds a body force before the solver's projection step, so hot regions gain lift while the divergence-free solve preserves overall volume. Scaling by `temperature` makes only the hot core buoyant; cool dissipated smoke stops climbing. The built-in Pyro solver has its own buoyancy, so use this when you want an art-directed override or a non-vertical "hot flows toward" direction.

### Fuel -> heat combustion shaping
Convert stored fuel into heat and soot where the field is hot enough to ignite.
Run over: Volumes (fields)
```vex
// Burn fuel where it is hot enough; release heat and a little soot density.
float ignite = chf("ignite_temp");
if (f@temperature > ignite && f@fuel > 0.0) {
    float burn = min(f@fuel, chf("burn_rate"));
    f@fuel -= burn;
    f@temperature += burn * chf("heat_per_fuel");
    f@density += burn * chf("soot");
}
```
Gating combustion on both an ignition temperature and remaining fuel gives a self-sustaining reaction: heat triggers burning, burning releases more heat. `min(fuel, burn_rate)` caps consumption per step so fuel depletes smoothly rather than all at once. The small `soot` term seeds visible smoke from the burn — drop it to zero for a cleaner flame, raise it for a dirty, sooty fire.

### Density-gated curl turbulence
Add fine swirling detail to the velocity, but only inside the smoke.
Run over: Volumes (fields)
```vex
// Only smoke-filled voxels get agitated; curl noise keeps it divergence-free.
float amt = fit01(f@density, 0.0, chf("dmax")) * chf("turb");
vector n = curlnoise(@P * chf("freq") + set(0.0, @Time * chf("evolve"), 0.0));
v@vel += n * amt;
```
`curlnoise` is divergence-free, so adding it to velocity introduces swirl without creating the sources/sinks that plain noise would (which the pressure solve would just fight). Weighting by `fit01(density)` confines the agitation to where there is smoke, leaving empty voxels calm. Offsetting the noise input by `@Time` on one axis animates the field so the turbulence evolves rather than sitting frozen in space.

### Confinement-style swirl about the plume axis
A cheap rotational boost that curls the whole plume around a vertical axis.
Run over: Volumes (fields)
```vex
// Cheap vorticity boost: rotate gas around the up axis, strongest in the dense core.
vector radial = @P - chv("center");
radial.y = 0.0;
vector swirl = cross(set(0.0, 1.0, 0.0), radial);
v@vel += normalize(swirl) * f@density * chf("swirl");  // normalize(0)=0 at the axis
```
The cross product of the up axis with the horizontal offset from a center line yields a tangential (circulating) direction at every voxel; adding it rotates the plume. Scaling by `density` keeps the rotation concentrated in the visible column. VEX's `normalize` of a zero vector returns zero, so the exact axis is handled without a guard — but this is a stylized swirl, not true vorticity confinement, which needs the curl of the velocity field itself.

### Dissipate thin smoke and cull wisps to zero
Fade density over time and hard-clip faint smoke so it doesn't linger forever.
Run over: Volumes (fields)
```vex
// Constant burn-off, then snap anything below a floor to exactly zero.
float d = f@density - chf("dissipate");
if (d < chf("cull_below")) d = 0.0;
f@density = max(d, 0.0);
```
A constant subtraction per step gives linear dissipation, while the `cull_below` clamp zeroes near-empty voxels so the field stays sparse and cheap (thin residual smoke is both a look problem and a performance one). The final `max` guards against negative density. For a softer look use multiplicative decay (`d *= chf("keep")`) instead of a flat subtraction.

### Shade heat: emission ramp gated by smoke
Author a scalar emission field from temperature for the shader to read.
Run over: Volumes (fields)
```vex
// Build a scalar emission field from temperature, masked by how much smoke is here.
float t = fit(f@temperature, chf("tlo"), chf("thi"), 0.0, 1.0);
f@emission = chramp("heat", t) * f@density;
```
Remapping temperature into 0..1 and running it through a ramp lets you sculpt the fire's brightness falloff independently of the sim. Multiplying by `density` ties emission to visible smoke so you don't glow in empty voxels. For colored fire, write a vector `Cd`/`emission` field instead and drive three ramp channels (or a color ramp) — here a single scalar keeps the example focused; the shading field must already exist in the sim for the solver to advect it.

### Per-voxel wind + drifting gusts
Add a uniform wind plus evolving gusts straight into the velocity field.
Run over: Volumes (fields)
```vex
// Uniform wind plus a slow-evolving curl-noise gust authored straight into vel.
vector wind = chv("wind_dir") * chf("wind_speed");
vector gust = curlnoise(@P * chf("gust_freq") + set(0.0, @Time * chf("gust_evolve"), 0.0));
v@vel += wind + gust * chf("gust");
```
The constant `wind` term biases the entire field in one direction, while the curl-noise `gust` adds large-scale, time-evolving variation so the wind feels alive rather than a dead uniform push. A low `gust_freq` gives broad rolling gusts; raise it for choppier air. Because both terms are added to velocity as a body force, the solver still enforces incompressibility on the result.

### Gate emission by a painted/derived mask field
Restrict where a source is allowed to emit using a second field.
Run over: Volumes (fields)
```vex
// Multiply the source by a mask so only painted regions actually emit.
f@source *= fit01(f@mask, chf("mlo"), chf("mhi"));
```
Multiplying the `source` field by a remapped `mask` scales emission down to zero outside the masked region and up to full inside it, giving art-directable control over an otherwise uniform emitter. `fit01(mask, mlo, mhi)` lets you set a soft threshold and feather on a grayscale mask. The mask can come from a rasterized paint, an occlusion/curvature bake, or another sim's output transferred into field space.

### Clamp fields to keep the solver stable
Cap density, temperature, and speed so a hot cell can't blow up the sim.
Run over: Volumes (fields)
```vex
// Cap density, temperature and speed so a hot cell cannot blow up the sim.
f@density = clamp(f@density, 0.0, chf("dmax"));
f@temperature = clamp(f@temperature, 0.0, chf("tmax"));
float sp = length(v@vel);
float cap = chf("vmax");
if (cap > 0.0 && sp > cap) v@vel *= cap / sp;   // clamp speed, keep direction
```
Runaway feedback (heat -> buoyancy -> more turbulence) can spike a single voxel's values until the timestep goes unstable; clamping the fields to sane maxima is a robust safety net. Scaling velocity by `cap / sp` limits speed while preserving direction — a plain component clamp would skew the flow. Place this near the end of the microsolver chain so it catches whatever the forces above produced.

---

## FLIP fluids

FLIP VEX splits between the **particles** (a Geometry Wrangle / POP Wrangle on the FLIP object's points, where `@v` is velocity, `@force` accumulates external forces, and `@id` is the stable per-particle id) and the **fields** (a Gas Field Wrangle on the pressure/velocity volumes). The particle side is where you seed whitewater, add region forces, clamp speed, and stamp source attributes; do not `removepoint` inside the solve — group instead and let a POP Kill remove them cleanly. The particle snippets below were verified in an Attribute Wrangle over a scattered point fixture carrying `@v`/`@id`/`@age`; the containment and paint-transfer idioms read a second input (a collision SDF and a source mesh) exactly as the wrangle's inputs 1+ provide.

### Seed whitewater weight from particle speed
Store a 0..1 emission weight from speed to drive downstream whitewater/foam seeding.
Run over: Points (FLIP particles)
```vex
// Fast particles are whitewater candidates; store a 0..1 seed weight + preview color.
float sp = length(@v);
f@speed = sp;
f@whitewater = fit(sp, chf("lo"), chf("hi"), 0.0, 1.0);
@Cd = set(f@whitewater, f@whitewater, 1.0);
```
`length(@v)` is the per-particle speed; remapping it between a low and high threshold gives a normalized weight the whitewater source can use to decide where foam and spray are born. Writing `@Cd` alongside gives an instant viewport preview of the seeding map so you can tune `lo`/`hi` by eye. Real whitewater also weights by curvature and vorticity — speed is the cheapest, most reliable first pass.

### Group dead particles by age or region
Tag expired particles for removal without deleting inside the solve.
Run over: Points (FLIP particles)
```vex
// Tag for a downstream POP Kill instead of removepoint inside the FLIP solve.
if (@age > chf("maxage") || @P.y < chf("floor")) i@group_dead = 1;
```
Building a `dead` group and letting a POP Kill (or a downstream Blast) do the removal is safer than `removepoint` mid-solve, which can fight the solver's own point management. Combining an age test with a spatial cutoff catches both old particles and any that escape below the tank floor. Add a speed or out-of-bounds test to the same condition to sweep up strays.

### Add a custom force inside an axis-aligned box
Apply an extra force only to particles within a box region.
Run over: Points (FLIP particles)
```vex
// Push particles that fall inside a box region (e.g. an updraft chimney).
vector mn = chv("box_min");
vector mx = chv("box_max");
if (@P.x > mn.x && @P.y > mn.y && @P.z > mn.z &&
    @P.x < mx.x && @P.y < mx.y && @P.z < mx.z) {
    @force += chv("push");
}
```
Testing `@P` component-by-component against a min/max corner is the fastest inside-box check; particles that pass get an added `@force` the solver integrates into velocity. Accumulating into `@force` (rather than setting `@v` directly) plays nicely with gravity and collisions, which also write force. Swap the box test for an SDF sign test to confine the force to any shape.

### Curl-noise agitation on the particle velocity
Break up flat, sheety motion with divergence-free swirl.
Run over: Points (FLIP particles)
```vex
// Divergence-free swirl breaks up flat sheets without adding net volume.
vector c = curlnoise(@P * chf("freq") + set(0.0, @Time * chf("evolve"), 0.0));
@v += c * chf("amp");
```
`curlnoise` produces a divergence-free field, so nudging velocity with it adds turbulent swirl without artificially inflating or collapsing the fluid volume. Animating the noise input by `@Time` keeps the agitation moving instead of stamping a static pattern into the flow. Keep `amp` small and layered under the real sim forces — this is a detail garnish, not a primary driver.

### Clamp maximum particle speed
Cap runaway velocities that would destabilize the pressure solve.
Run over: Points (FLIP particles)
```vex
// A runaway particle destabilizes the pressure solve; cap speed, keep heading.
float sp = length(@v);
float cap = chf("maxspeed");
if (cap > 0.0 && sp > cap) @v *= cap / sp;
```
A few particles moving far faster than the rest force tiny substeps and can spray artifacts; scaling velocity by `cap / sp` limits magnitude while preserving direction. This is gentler than a per-axis clamp, which would bend the particle's heading. Run it after your force wrangles so it catches whatever accumulated velocity they produced.

### Surface-tension-like cohesion from a neighbour pull
Pull each particle toward its local neighbourhood centroid for a beadier fluid.
Run over: Points (FLIP particles)
```vex
// Pull each particle toward its neighbourhood centroid -> tighter, beadier fluid.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
if (pcnumfound(h) > 0) {
    vector cen = pcfilter(h, "P");
    @v += (cen - @P) * chf("cohesion");
}
```
`pcopen` finds nearby particles within `radius`, `pcfilter` averages their positions into a local centroid, and steering toward it mimics cohesion — droplets tighten and blobs hold together. Guarding on `pcnumfound(h) > 0` avoids pulling toward a garbage centroid when a particle is isolated. This is a stylized cohesion, not physical surface tension; keep `cohesion` low or fast fluid will clump unnaturally.

### Rise or sink by a per-particle material id
Two-phase behavior — one material floats, the other sinks.
Run over: Points (FLIP particles)
```vex
// Two-phase trick: light material floats, everything else sinks.
float b = (i@mtl == chi("light_id")) ? chf("rise") : -chf("sink");
@force += set(0.0, b, 0.0);
```
Branching on a per-particle material id lets you drive buoyancy differently per phase — a positive vertical force for the light material, a negative one for the heavy — approximating oil-over-water separation without a true multiphase solver. Adding to `@force` keeps it composable with gravity and collision response. Carry `mtl` from the source geometry so it's stable for each particle's life.

### Stamp velocity + attributes onto freshly sourced particles
Seed launch velocity, reset age, and assign a stable variant at the source.
Run over: Points (FLIP particles)
```vex
// At the source, seed launch velocity, reset age, and pick a stable variant.
if (i@group_source) {
    @v = chv("emit_vel") + curlnoise(@P * 2.0) * chf("jitter");
    f@age = 0.0;
    i@variant = int(rand(i@id) * chi("nvariant"));
}
```
Restricting the writes to a `source` group means only newly emitted particles get initialized, leaving the established fluid untouched. Seeding `@v` with a base emit velocity plus curl-noise jitter gives lively, non-uniform launches, and deriving `variant` from `rand(i@id)` makes the per-particle random pick stable for that particle's whole life (id-seeded, not ptnum-seeded). Resetting `@age` starts each particle's life clock at birth.

### Push particles back inside a collision SDF
Keep particles contained by shoving any that breach a collision level set back inward.
Run over: Points (FLIP particles); second input = collision SDF
```vex
// Sample the collision level set (input 1); if we breach it, shove out along its gradient.
float d = volumesample(1, "collision", @P);   // SDF < 0 inside the solid
if (d < chf("margin")) {
    vector n = volumegradient(1, "collision", @P);
    @v += normalize(n) * chf("pushback");
}
```
`volumesample` reads the signed distance at the particle from a collision field wired into input 1; a value below a small `margin` means the particle has penetrated (or is about to). `volumegradient` gives the direction of increasing distance — pointing out of the solid — so pushing velocity along it resolves the breach. This is a belt-and-braces containment on top of the solver's own collisions, useful for thin or fast-moving obstacles particles tunnel through.

### Carry a paint mask from source geo onto particles
Transfer a color/mask from a reference surface onto the fluid for downstream shading.
Run over: Points (FLIP particles); second input = source mesh with Cd
```vex
// Nearest point on the source surface (input 1) gives a uv to sample its Cd.
int prim = -1;
vector uv = 0.0;
float d = xyzdist(1, @P, prim, uv);
if (prim >= 0) v@paint = primuv(1, "Cd", prim, uv);
```
`xyzdist` finds the closest primitive and its parametric `uv` on the input-1 surface, and `primuv` samples any attribute there — here `Cd` — giving a smooth interpolated value rather than a nearest-point snap. Guarding on `prim >= 0` skips particles with no surface in range. Do this once near the source (or bake it) so each particle carries its paint for the rest of the sim, feeding shading, foam tint, or region-based behavior later.

---

## Particles (POP wrangles)

POP wrangles run inside a particle simulation, once per particle per substep. Input 0 is the live
particle geometry, so `pcopen(0, ...)` sees the other particles this frame. The solver integrates what
you write: add to `@force` and it becomes acceleration (scaled by `1/@mass`); write `@v` directly and
you override velocity for the substep. Time comes in as `@Time` (seconds), `@Frame`, and `@TimeInc`
(substep length) — multiply rate-based terms by `@TimeInc` so they stay stable when substeps change.
Use `@id` (stable) rather than `@ptnum` (renumbers as particles are born and die) whenever you seed
per-particle randomness.

### Accumulate a custom force
Pull particles toward a point with an inverse-square attraction, added to the solver's force budget.
Run over: Points (particles)
```vex
vector goal   = chv("goal");
vector dir    = goal - @P;
float  d      = max(length(dir), 1e-3);
@force += normalize(dir) * chf("strength") / (d*d);
```
`@force` accumulates — several wrangles (or POP Force nodes) can each add their contribution and the
solver sums them, so always use `+=`, not `=`. Clamping the distance with `max(..., 1e-3)` avoids a
divide-by-zero singularity at the goal. For a constant pull instead of inverse-square, drop the `/(d*d)`
and just add `normalize(dir) * strength`.

### Age-driven fade and resize
Shrink, recolor, and fade a particle over its lifespan using normalized age.
Run over: Points (particles)
```vex
float t   = fit01(@nage, 0, 1);
@pscale   = fit(t, 0, 1, chf("born_size"), chf("die_size"));
@Cd       = chramp("life_color", t);
@Alpha    = 1.0 - smooth(chf("fade_start"), 1.0, t);
```
`@nage` is `@age / @life` — it runs 0 at birth to 1 at death, which is exactly the parameter you want
for a ramp lookup, so you never have to know a particle's absolute lifespan. Driving `@Cd` through
`chramp` gives an art-directable palette over life; `smooth` gives a soft fade-out that only starts once
`t` passes `fade_start`. If particles never die (infinite life), `@nage` stays 0 — gate on `@age`
instead.

### Group particles by condition
Tag particles that are slow or near the ground so a later node can treat them differently.
Run over: Points (particles)
```vex
float sp        = length(@v);
i@group_slow    = sp < chf("slow_speed");
i@group_ground  = @P.y < chf("ground_y");
```
`i@group_name = boolean;` is the fast way to build a POP group inside a wrangle — nonzero means member.
Downstream POP nodes have an "Activation" / group field where you type `slow` to act only on those
particles (e.g. a POP Wind that only pushes stalled particles). Because wrangles run in parallel, this
membership reflects the state at the start of the wrangle, not other particles' edits.

### Arrival steering toward a goal
Seek a target but ease off as you approach, so particles settle instead of overshooting.
Run over: Points (particles)
```vex
vector goal    = chv("goal");
vector to      = goal - @P;
float  d       = length(to);
float  arrive  = fit(d, 0, chf("slow_radius"), 0, chf("max_speed"));
vector desired = (d > 1e-4) ? normalize(to) * arrive : {0,0,0};
@force += (desired - @v) * chf("gain");
```
The desired speed ramps from 0 at the goal up to `max_speed` once you are `slow_radius` away — that
linear falloff is the "arrival" behavior. Steering as `(desired - @v) * gain` is a proportional
controller: it applies force proportional to the velocity error, which damps the approach. Higher `gain`
snaps harder toward the goal; too high and it oscillates.

### Flocking trio: separation, alignment, cohesion
The classic boids reduction — one point-cloud pass over the neighbours yields all three urges.
Run over: Points (particles)
```vex
int    h = pcopen(0, "P", @P, chf("radius"), chi("maxn"));
vector sep = 0, ali = 0, coh = 0;
int    n = 0;
while (pciterate(h)) {
    int nb;  pcimport(h, "point.number", nb);
    if (nb == @ptnum) continue;
    vector op, ov;
    pcimport(h, "P", op);
    pcimport(h, "v", ov);
    sep += @P - op;   // steer away from each neighbour
    ali += ov;        // match neighbours' heading
    coh += op;        // accumulate neighbour positions for a centroid
    n++;
}
if (n > 0) {
    coh = coh / n - @P;
    @force += normalize(sep) * chf("sep")
            + normalize(ali) * chf("ali")
            + normalize(coh) * chf("coh");
}
```
`pcopen` opens a neighbourhood of up to `maxn` points within `radius`; the manual `pciterate` /
`pcimport` loop lets you accumulate three different quantities in one pass instead of calling `pcfilter`
three times. Importing `point.number` and skipping `nb == @ptnum` excludes the particle from its own
flock, which otherwise biases every term toward itself. The three weights are the whole feel of the
sim — separation usually dominates to prevent clumping.

### Kill by condition
Remove particles that have aged out or left the working volume.
Run over: Points (particles)
```vex
if (@age > chf("max_age") || @P.y < chf("kill_below")) {
    removepoint(0, @ptnum);
}
```
`removepoint(0, @ptnum)` deletes the current particle from input 0 immediately. The softer,
solver-friendly alternative is `i@dead = 1;` — the POP Solver reaps particles flagged `dead` at the end
of the step, which plays nicer with sub-steps and caching than deleting mid-solve. Reach for a POP Kill
node when the condition is simple; reach for this wrangle when the test needs custom logic.

### Wander / curl drift
Add organic, swirling drift with a divergence-free noise field that evolves over time.
Run over: Points (particles)
```vex
vector np = @P * chf("freq") + set(0, 0, @Time * chf("evolve"));
vector w  = curlnoise(np);
@force += w * chf("amp");
```
`curlnoise` returns a divergence-free vector field, so particles swirl and fold without collapsing into
sinks or exploding out of sources the way raw `vnoise` would. Offsetting the sample point by `@Time`
along one axis animates the field, so a static particle still feels a changing breeze. Scale the input
by `freq` for pattern size and the output by `amp` for strength.

### Speed limit and drag
Bleed off velocity and cap the maximum speed to keep a sim from blowing up.
Run over: Points (particles)
```vex
@v *= (1.0 - chf("drag") * @TimeInc);
float sp = length(@v);
float mx = chf("max_speed");
if (sp > mx) @v *= mx / sp;
```
Multiplying `drag` by `@TimeInc` makes the damping frame-rate independent — the same `drag` value
removes the same fraction of speed per second no matter how many substeps run. The speed clamp rescales
the velocity vector to length `mx` only when it exceeds it, preserving direction. Writing `@v` directly
overrides the integrated velocity for this substep, so put this after your force wrangles.

### Birth jitter by stable id
Give each particle a persistent random scale, tint, and variant index seeded once at birth.
Run over: Points (particles)
```vex
@pscale   *= fit(rand(@id*2.3 + 11.7), 0, 1, chf("min_scale"), chf("max_scale"));
i@variant  = int(rand(@id*7.1) * chi("num_variants"));
@Cd        = chramp("birth_tint", rand(@id*3.7));
```
`rand(@id)` is deterministic per particle and stable across the whole sim, so the same particle keeps the
same look every frame — critical for instancing and caching. Multiplying `@id` by different constants
before `rand` decorrelates the scale, variant, and tint draws so they don't move in lockstep. Gate this
with a birth group (or run it in a POP Source's attribute wrangle) so it fires once, not every frame.

### Collision bounce tweak
Reflect and dampen velocity on impact using the collision attributes.
Run over: Points (particles)
```vex
if (i@hitnum > 0) {
    vector n = v@hitnormal;
    if (length(n) > 1e-4) {
        @v = reflect(@v, normalize(n)) * chf("bounce");
    }
}
```
A POP Collision Detect node upstream writes `@hitnum`, `@hitpos`, and `@hitnormal` when a particle
touches a collider — this wrangle reads those to author a custom response instead of the built-in one.
`reflect(@v, n)` mirrors the velocity about the surface normal, and the `bounce` multiplier controls
restitution (0 = stick, 1 = perfectly elastic). Guarding `length(n) > 1e-4` skips particles that
recorded a hit count but no valid normal.

### Emit / trail bookkeeping
Write per-particle flags a downstream POP Source reads to birth trails or sub-particles.
Run over: Points (particles)
```vex
i@emit      = (@nage > chf("emit_start")) && (length(@v) > chf("emit_speed"));
f@emit_rate = fit(length(@v), 0, chf("vmax"), 0, chf("max_rate")) * i@emit;
```
Rather than birthing particles from the wrangle, you author intent: `emit` marks which particles should
spawn children, and `emit_rate` scales that by speed. A second POP network (or a POP Source set to birth
from points, using `emit` as a group and `emit_rate` as the impulse count) consumes these — keeping the
decision logic in VEX and the actual birthing in the node it belongs to. This pattern drives sparks,
smoke wisps, and debris trails off fast-moving particles.

---

## Vellum (constraint authoring)

Most Vellum art direction happens by writing attributes, not by tuning solver globals. Two contexts
matter. **Pre-sim**, a SOP Attribute Wrangle on the cloth/rope points or on the Vellum Constraints output
authors `@stiffness`, `@mass`, `@restlength`, and pin groups before the solve. **In-solver**, a Geometry
Wrangle (or a SOP Solver operating on Constraint Geometry) edits those same attributes per frame — that
is where tearing and time-varying stiffness live. Constraint geometry is a set of 2-point polylines: each
constraint primitive connects two simulated points, its length target is `@restlength`, and its type is
tagged in `s@constraint_name`. Per-point `@mass` scales inertia (heavier = harder to move); `@pscale`
sets the collision thickness radius.

### Pin an edge to a group
Tag a row of points so a Vellum Pin constraint can hold them in place.
Run over: Points (cloth)
```vex
// pre-sim: tag the top row so a Vellum Pin-to-Target constraint can grab group "pinned".
i@group_pinned = @P.z > chf("pin_z");
```
Pinning in Vellum is a two-step idea: a wrangle builds the group, and a Vellum Constraints node set to
"Pin to Target" (or "Attach to Geometry") references that group name to freeze those points. Building the
group in VEX lets you pin by any measured condition — a painted mask, a distance, a normal direction —
not just a hand-drawn selection. Nonzero membership means pinned.

### Stiffness from a mask
Modulate constraint stiffness across the mesh from a painted or measured 0..1 mask.
Run over: Primitives (constraints)
```vex
// on constraint prims: modulate stiffness by a painted/measured mask 0..1.
f@stiffness = fit01(f@mask, chf("soft"), chf("stiff"));
```
Vellum stores stiffness per constraint primitive, so this runs over the Constraint Geometry, not the
cloth. `fit01` remaps the mask so mask 0 gives `soft` and mask 1 gives `stiff`, letting you paint stiff
seams into a soft sheet. Distinct constraint types carry their own attributes — `stretchstiffness` and
`bendstiffness` — if you need to target one behavior independently.

### Release pins over time
Fade constraint stiffness to zero between two frames so a held object drops.
Run over: Primitives (constraints)
```vex
// in-solver constraint update: fade constraint stiffness between two frames.
float t = fit(@Frame, chf("start_frame"), chf("end_frame"), 1.0, 0.0);
f@stiffness *= clamp(t, 0, 1);
```
Run inside the Vellum solver (Geometry Wrangle on the constraint stream) so `@Frame` advances the fade
each step. `fit` produces 1 before `start_frame` and 0 after `end_frame`; the `clamp` guards the
extrapolated tails so stiffness never goes negative or above its authored value. Multiplying (`*=`)
rather than assigning preserves any per-constraint stiffness variation you authored pre-sim.

### Tear on stretch
Sever a constraint once it stretches past a ratio of its rest length.
Run over: Primitives (constraints)
```vex
// sever a constraint prim once it stretches past a ratio of its rest length.
int    p0 = primpoint(0, @primnum, 0);
int    p1 = primpoint(0, @primnum, 1);
vector a  = point(0, "P", p0);
vector b  = point(0, "P", p1);
float  cur  = distance(a, b);
float  rest = f@restlength;
if (rest > 1e-6 && cur > rest * chf("tear_ratio")) {
    removeprim(0, @primnum, 0);
}
```
Tearing means deleting constraint primitives: with the constraint gone, the two points fly apart. Read
the primitive's two endpoints with `primpoint`, compare their current separation to the stored
`@restlength`, and `removeprim` when the ratio crosses `tear_ratio` (e.g. 1.5 = tears at 50% stretch).
Note the typed `vector a = point(...)` reads — `point()` returns an ambiguous type, and passing it
straight into `distance()` errors with "ambiguous call"; bind to a `vector` first. Run this in a SOP
Solver inside the Vellum solver so tears persist frame to frame.

### Author rest length for slack or pre-tension
Set each constraint's target length from the current geometry, scaled to add slack or tension.
Run over: Primitives (constraints)
```vex
// pre-tension / slack: set rest length from current geometry scaled by a factor.
int    p0 = primpoint(0, @primnum, 0);
int    p1 = primpoint(0, @primnum, 1);
vector a  = point(0, "P", p0);
vector b  = point(0, "P", p1);
f@restlength = distance(a, b) * chf("slack");
```
`@restlength` is the length a distance constraint tries to hold. Setting it to the measured length times
`slack` lets you pre-tension (`slack` < 1, so the constraint pulls the points together and the sheet
shrinks taut) or introduce slack (`slack` > 1, so rope and cloth sag). This is the VEX equivalent of the
Vellum Constraints "rest length scale" but per-constraint and driveable by any attribute.

### Mass and thickness from an attribute
Make some points heavier and set their self-collision radius.
Run over: Points (cloth)
```vex
// heavier where the mask is high; thickness drives self-collision radius.
f@mass   = fit01(f@density_mask, chf("min_mass"), chf("max_mass"));
@pscale  = chf("thickness");
```
Vellum reads `@mass` per point: higher mass resists forces and constraints more, so a weighted hem or a
loaded pocket sags realistically. `@pscale` sets the per-point collision thickness — the radius Vellum
keeps clear during self- and object-collision — so thin cloth wants a small value and chunky rope a
larger one. Both are ordinary point attributes you can paint, measure, or compute.

### Wind and pressure force
Add steady wind plus turbulent gusts inside the solver, scaled by mass.
Run over: Points (DOP geometry)
```vex
// in-solver Geometry Wrangle: steady wind + turbulent gust, scaled by mass for a mass-consistent push.
vector wind = chv("wind_dir") * chf("wind_speed");
vector gust = curlnoise(@P * chf("freq") + @Time * chf("evolve")) * chf("gust");
@force += (wind + gust) * f@mass;
```
Inside the Vellum solver, `@force` accumulates external forces before integration. Combining a constant
`wind` with an evolving `curlnoise` gust gives motion that reads as air rather than a uniform shove.
Multiplying by `@mass` makes the resulting acceleration uniform regardless of per-point mass (F = ma), so
heavy and light points drift together — drop the `* @mass` if you instead want light points to flutter
more.

### Selective stiffness by constraint name
Set different stiffness for bend versus stretch constraints in one pass.
Run over: Primitives (constraints)
```vex
// selective stiffness: Vellum tags each constraint prim by type in s@constraint_name.
if (s@constraint_name == "bend")         f@stiffness = chf("bend_stiff");
else if (s@constraint_name == "stretch") f@stiffness = chf("stretch_stiff");
```
When Vellum builds cloth it names each constraint primitive by its role in `s@constraint_name`
(`stretch`, `bend`, and so on). Branching on that name lets you make a sheet that resists stretching but
folds easily (high stretch, low bend) — the difference between paper and silk — from a single wrangle.
Inspect the actual names on your constraint geometry in the spreadsheet; they depend on the constraint
type you built.

### Attach to a moving collider
Weld points that sit within a distance of a collider into an attach group.
Run over: Points (cloth), collider in input 1
```vex
// weld cloth points that sit within a distance of the moving collider (input 1).
int   near = nearpoint(1, @P);
float d    = distance(@P, point(1, "P", near));
i@group_attached = d < chf("weld_dist");
```
`nearpoint(1, @P)` returns the closest point on the collider in input 1, and its distance gates
membership in the `attached` group. A Vellum Constraints node set to "Attach to Geometry" then welds
those points to the collider so they follow it while the rest of the cloth simulates freely — think a
flag's grommets on a moving pole. Widen `weld_dist` to catch more points; keep it tight to attach only a
seam.

### Debug constraint strain
Color each constraint by how far it is stretched or compressed for art direction.
Run over: Primitives (constraints)
```vex
// visualize per-constraint strain: + stretched, - compressed.
int    p0 = primpoint(0, @primnum, 0);
int    p1 = primpoint(0, @primnum, 1);
vector a  = point(0, "P", p0);
vector b  = point(0, "P", p1);
float  cur    = distance(a, b);
float  rest   = max(f@restlength, 1e-4);
float  strain = (cur - rest) / rest;
@Cd = chramp("strain_ramp", fit(strain, -chf("range"), chf("range"), 0, 1));
```
Strain is the signed fractional length change: positive where a constraint is stretched, negative where
compressed. Mapping it through a ramp centered on 0 (blue-white-red is conventional) instantly shows
where a garment is under tension and where it bunches — the places likely to tear or pinch. This is a
read-only diagnostic; drop it before your final cache, or leave it on a bypassed branch.

---

## Crowds (agent wrangles)

Crowd agents are packed **primitives**: each agent primitive carries a skeleton, a catalog of animation
clips, and the currently active clip mix. The 65-function agent VEX API reads and writes that state.
Because agents are primitives, the clip and transform functions run in a wrangle set to **Run Over
Primitives**, indexing with `@primnum`; per-agent look attributes like `@pscale` and `@Cd` live on the
agent's point, so those idioms run over Points. Two function families dominate: the `agentclip*` readers
(`agentclipcatalog`, `agentclipnames`, `agentcliptimes`, `agentcliplength`) and the `setagentclip*`
writers (`setagentclipnames`, `setagentclipweights`, `setagentcliptimes`), whose first argument is the
geometry handle `0` (the current, writable geometry). Seed per-agent variation from `@id` so it stays
stable as agents are added or reordered.

### Play a single clip
Set one clip from the agent's catalog as the sole active animation.
Run over: Primitives (agents)
```vex
string cat[] = agentclipcatalog(0, @primnum);
if (len(cat) > 0) {
    setagentclipnames(0, @primnum, array(cat[0]));
    setagentclipweights(0, @primnum, array(1.0));
    setagentcliptimes(0, @primnum, array(0.0));
}
```
`agentclipcatalog` lists every clip baked into the agent definition; the `setagentclip*` trio then makes
one of them the active state. The three writers work as parallel arrays — names, weights, and times index
together — so a single active clip is three one-element arrays. Guarding on `len(cat) > 0` keeps agents
with an empty catalog from erroring.

### Desync clip phase
Offset each agent's clip start by a random amount so a crowd doesn't march in lockstep.
Run over: Primitives (agents)
```vex
string active[] = agentclipnames(0, @primnum);
if (len(active) > 0) {
    float len0  = agentcliplength(0, @primnum, active[0]);
    float phase = rand(@id) * len0;
    setagentcliptimes(0, @primnum, array(phase));
}
```
Identical clip times are what make a synthetic crowd read as fake — every agent hits the same footfall on
the same frame. `agentcliplength` gives the active clip's duration, and seeding the offset with
`rand(@id)` spreads agents uniformly across the cycle while staying stable frame to frame.
`agentclipnames` returns the *currently active* clips (versus `agentclipcatalog`, which returns all
available ones).

### Blend two clips
Cross-fade between two catalog clips with a single blend weight.
Run over: Primitives (agents)
```vex
string cat[] = agentclipcatalog(0, @primnum);
if (len(cat) >= 2) {
    float w = chf("blend");   // 0 = first clip, 1 = second
    setagentclipnames(0, @primnum,  array(cat[0], cat[1]));
    setagentclipweights(0, @primnum, array(1.0 - w, w));
    setagentcliptimes(0, @primnum,   array(@Time, @Time));
}
```
Two active clips with complementary weights is how you blend a walk into a run, or a neutral pose into a
wave. The weights need not sum to 1 in general, but for a clean cross-fade `1-w` and `w` keep the overall
influence constant. Feeding both clips the same time (`@Time`) keeps their phases aligned; give them
separate times if the cycles have different lengths.

### Advance clip time manually
Step every active clip forward yourself for custom playback rate control.
Run over: Primitives (agents)
```vex
float times[] = agentcliptimes(0, @primnum);
foreach (int i; float t; times) {
    times[i] = t + @TimeInc * chf("playrate");
}
setagentcliptimes(0, @primnum, times);
```
Reading the current `agentcliptimes` array, nudging every entry, and writing it back lets you drive
playback speed per agent — a `playrate` above 1 speeds the animation up, below 1 slows it, 0 freezes a
pose. Scaling by `@TimeInc` keeps the advance consistent under substeps. The `foreach (int i; float t;
times)` form binds both the index and value so you can edit the array in place.

### Read a bone transform
Fetch a named joint's world matrix — for attaching props or driving secondary rigs.
Run over: Primitives (agents)
```vex
int j = agentrigfind(0, @primnum, chs("joint"));   // e.g. "head"
if (j >= 0) {
    matrix xf = agentworldtransform(0, @primnum, j);
    v@attach_P = cracktransform(0, 0, 0, {0,0,0}, xf);
}
```
`agentrigfind` resolves a joint name to its transform index (returning -1 if the name is absent, which
the guard handles), and `agentworldtransform` gives that joint's full world-space matrix.
`cracktransform(0, ...)` extracts just the translation — pull the rotation with the rotate mode (`1`) if
you need to orient an attached prop. This is the read side you pair with a copy-to-points to stick hats,
weapons, or backpacks onto a crowd.

### Per-agent look variation
Give each agent a stable random scale, tint, and variant index.
Run over: Points (agents)
```vex
@pscale   = fit(rand(@id*1.7), 0, 1, chf("min_scale"), chf("max_scale"));
@Cd       = chramp("tint", rand(@id*4.3));
i@variant = int(rand(@id*9.1) * chi("variants"));
```
Look variation lives on the agent *point*, so this runs over Points. Seeding every draw from `@id` (with
different multipliers to decorrelate them) guarantees an agent keeps the same height, color, and outfit
index for the whole shot. A downstream switch or material can read `@variant` to swap meshes or textures,
turning one agent definition into a varied crowd.

### Terrain adaptation
Project agents onto the ground and capture the surface normal for uprighting.
Run over: Points (agents), terrain in input 1
```vex
vector hitP, hitUV;
int pr = intersect(1, @P + {0,10,0}, set(0,-1,0)*100.0, hitP, hitUV);
if (pr >= 0) {
    @P    = hitP;
    v@N   = primuv(1, "N", pr, hitUV);
    v@up  = normalize(v@N);
}
```
Ray-casting straight down from above each agent (start lifted by +10, direction `(0,-1,0)` scaled long
enough to reach the ground) drops it exactly onto uneven terrain in input 1. `intersect` returns the hit
primitive and fills `hitP`/`hitUV`; sampling the terrain's `N` at that uv gives the slope so you can set
`@up` and keep agents standing perpendicular to hills. The crowd solver and the agent's orientation then
use `@up` to bank the pose.

### Group agents by team
Split a crowd into teams by region for branching behavior.
Run over: Points (agents)
```vex
i@team        = (@P.x < chf("split_x")) ? 0 : 1;
i@group_teamA = i@team == 0;
@Cd = (i@team == 0) ? chv("colorA") : chv("colorB");
```
A simple positional test assigns a `@team` id and a matching group; downstream trigger and steering logic
can then branch on team — team A seeks one goal, team B another. Coloring by team makes the split
readable in the viewport while you tune the boundary. Swap the `@P.x` test for a bounding-box, noise, or
`@id`-modulo test to shape more interesting factions.

### Steer toward a goal
Author a flat heading and velocity aimed at a target.
Run over: Points (agents)
```vex
vector goal = chv("goal");
vector to   = goal - @P;
to.y = 0;
@v = normalize(to) * chf("speed");
f@heading = atan2(@v.x, @v.z);
```
Zeroing the y-component keeps the steering horizontal so agents don't try to walk up into the air toward
an elevated goal. `@v` gives the crowd solver a target velocity, and `heading` (from `atan2` of the
horizontal velocity) is the facing angle many crowd setups consume to turn the agent's body. This is a
naive direct-seek; combine it with the avoidance nudge below for something that navigates around
neighbours.

### Neighbour avoidance nudge
Push each agent away from crowding neighbours with an inverse-distance repulsion.
Run over: Points (agents)
```vex
int    h = pcopen(0, "P", @P, chf("radius"), chi("maxn"));
vector push = 0;
int    n = 0;
while (pciterate(h)) {
    int nb;  pcimport(h, "point.number", nb);
    if (nb == @ptnum) continue;
    vector op;  pcimport(h, "P", op);
    vector d = @P - op;  d.y = 0;
    float  L = length(d);
    if (L > 1e-4) push += normalize(d) / L;
    n++;
}
if (n > 0) @v += push * chf("avoid");
```
The point-cloud loop sums a repulsion from each neighbour, weighted by `1/L` so close agents push much
harder than distant ones — that inverse falloff is what prevents inter-penetration without a hard
collision. Excluding self (`nb == @ptnum`) and flattening to the ground plane (`d.y = 0`) keeps the nudge
horizontal and stable. Add this to a goal-seek velocity so agents flow toward a target while parting
around each other; `avoid` sets how strongly personal space wins over the goal.

---

## Copy, instancing & orient

Copy-to-Points reads a stack of *instance attributes* off the template points to place, orient, and scale
each copy — and the order they are resolved matters. The precedence, highest first: a full `3@transform`
(or `4@transform`) matrix overrides everything; otherwise `p@orient` (a quaternion) sets rotation; only if
`orient` is absent does the `v@N` + `v@up` pair build the frame (N is the primary/`+Z` axis, `up` resolves
the roll). On top of whichever of those applied, `@pscale` (uniform) or `v@scale` (per-axis) scales,
`p@rot` adds an extra quaternion spin, and `v@trans`/`v@pivot` shift the copy. The everyday task is
building `p@orient` cleanly: `maketransform(zaxis, yaxis)` makes a matrix3 from two axes (note **zaxis
first**), and `quaternion(matrix3)` converts it to the vector4 quaternion `orient` wants. A gotcha the
base type-table hides: use the `p@` prefix (vector4) for quaternion attributes like `orient` and `rot` —
`u@` does *not* bind a vector4.

### Orient copies to a curve tangent
Build a per-point `orient` whose Z axis runs along a curve, for ribbons, rings, or geo swept by copy.
Run over: Points (curve)
```vex
// tangent from neighbour points on a polyline -> orient quaternion (Z down the curve).
int prev = max(@ptnum - 1, 0);
int next = min(@ptnum + 1, @numpt - 1);
vector tang = normalize(point(0, "P", next) - point(0, "P", prev));
vector up   = chv("up");                 // reference up, e.g. {0,1,0}
matrix3 m   = maketransform(tang, up);   // zaxis = tangent, yaxis = up
p@orient    = quaternion(m);
```
A central-difference of the neighbouring point positions gives a smooth tangent; clamping `prev`/`next`
to the endpoints keeps the first and last points valid. `maketransform(tang, up)` orthonormalizes the two
axes into a rotation matrix (the `up` only needs to be roughly correct — it is projected perpendicular to
the tangent), and `quaternion()` packs it for `orient`. If the curve doubles back parallel to `up` the
frame flips; feed a per-point up or use a minimal-twist frame (see *twist along a spine*) for those cases.

### Build orient from N and up
The workhorse: turn a surface normal plus a world up into a copy orientation.
Run over: Points
```vex
// build orient so copies sit on the surface: Z = up-ish tangent, but here align Z to N.
vector up = chv("up");
matrix3 m = maketransform(@N, up);       // zaxis = surface normal, yaxis = world up
p@orient  = quaternion(m);
```
This is the same two-axis construction, using the point normal as the primary axis so copies stand off the
surface. Whatever mesh axis you want pointing along `@N` depends on how the instanced geo is modelled —
`maketransform` always maps the first argument to +Z, so model the copy pointing down +Z (or rotate it
first). Writing `orient` rather than leaving bare `N`+`up` on the points makes the result explicit and
immune to Copy-to-Points' own up-vector guessing.

### The instance-attribute stack
Author several instance attributes at once and see how they layer.
Run over: Points
```vex
// the copy-to-points instance attribute stack (authored on the template points):
v@N      = normalize(@N);                // primary axis if no orient
v@up     = chv("up");                    // secondary axis, resolves N's roll
@pscale  = fit01(f@mask, 0.5, 1.5);      // uniform per-copy scale
p@orient = quaternion(maketransform(@N, v@up));   // orient WINS over N/up if present
p@rot    = quaternion(radians(ch("spin")), {0,1,0}); // extra spin quaternion, applied after orient
v@trans  = {0,0,0};                      // post-transform translate offset
```
All of these live on the template points and are consumed by the Copy-to-Points node. Because `orient` is
present here it takes over rotation and the `N`/`up` pair is ignored for the frame (they are still handy
as documentation, and some tools read `N` for other purposes). `pscale` scales uniformly after
orientation; `rot` is a *separate* quaternion multiplied on top of `orient` (use it for a spin you want to
keep conceptually distinct); `trans` nudges the final position. Reach for `v@scale` instead of `@pscale`
when you need non-uniform scale.

### Random spin about the normal
Give surface-aligned copies a per-point twist so identical instances don't read as a grid.
Run over: Points
```vex
// start from a surface-aligned orient, then add a per-point random twist about N.
vector up = chv("up");
p@orient  = quaternion(maketransform(@N, up));
float ang = rand(@id * 3.13) * radians(ch("max_deg"));
vector4 spin = quaternion(ang, normalize(@N));
p@orient  = qmultiply(spin, p@orient);   // pre-multiply: spin in the copy's own frame
```
`quaternion(angle, axis)` builds a rotation of `angle` radians about `axis`; `qmultiply` composes it with
the base orientation. Seeding the angle from `rand(@id)` keeps each copy's twist stable across frames and
caches, which matters if the copies are later cached or motion-blurred. Order matters: pre-multiplying
(`spin * orient`) rotates about the axis in world space here because `spin`'s axis is the world-space `@N`;
swap the operands to spin in the copy's local frame instead.

### Align to a surface with random yaw
Scatter-on-surface look: stand copies on the normal but rotate each one a random amount around it.
Run over: Points
```vex
// scatter-on-surface look: Z to the surface normal, random yaw so copies don't line up.
vector n  = normalize(@N);
float  yaw = rand(@id * 7.7) * 2 * $PI;
vector up  = normalize(cross(n, set(cos(yaw), 0, sin(yaw))));
p@orient   = quaternion(maketransform(n, up));
```
Instead of spinning a fixed frame, this *builds* a random up vector per point: a random horizontal
direction crossed with the normal yields an up that is guaranteed perpendicular to `n` yet randomly
oriented around it. The result is copies that hug the surface with no visible alignment — ideal for
scattering rocks, debris, or foliage cards. `$PI` is the built-in constant; `rand(@id)` keeps the yaw
deterministic per point.

### Read a packed transform intrinsic
Pull the position and rotation back out of packed copies for measuring, retargeting, or debugging.
Run over: Primitives (packed)
```vex
// read a packed copy's full transform intrinsic and pull out where it sits.
matrix xf = primintrinsic(0, "packedfulltransform", @primnum);
v@copy_P  = cracktransform(0, 0, 0, {0,0,0}, xf);   // translation
v@copy_R  = cracktransform(0, 0, 1, {0,0,0}, xf);   // euler rotation (deg)
```
Packed primitives store their placement in the `packedfulltransform` intrinsic — a full 4×4 matrix that
includes any transform baked in by Copy-to-Points. `cracktransform` decomposes a matrix into a component:
mode `0` returns translation, `1` returns euler rotation in degrees, `2` returns scale. This is how you
recover per-copy data after packing, e.g. to write positions to a point cloud or to sort copies by height.
The `packedlocaltransform` intrinsic gives the transform *without* the point placement if you need only
the internal offset.

### Convert a packed transform to orient
Re-instance packed copies through the `orient` pipeline by extracting a clean rotation quaternion.
Run over: Primitives (packed)
```vex
// convert a packed prim's rotation into an @orient quaternion for re-instancing.
matrix xf  = primintrinsic(0, "packedfulltransform", @primnum);
vector rot = cracktransform(0, 0, 1, {0,0,0}, xf);   // euler rotation (deg), scale-free
p@orient   = eulertoquaternion(radians(rot), 0);      // 0 = XYZ order
```
Going straight from the 4×4 to a quaternion risks folding scale into the rotation, which yields a
distorted `orient`. Decomposing with `cracktransform` to euler *degrees* discards translation and scale
cleanly, and `eulertoquaternion(radians(rot), 0)` rebuilds a pure rotation quaternion (the `0` selects XYZ
rotation order — match it to how the transform was authored). Now the copies can be unpacked to their
points and re-copied through a standard `orient` workflow.

### Stick geo to a deforming surface
Capture points against a rest surface so a later pass can ride the deformed version (a manual Point Deform).
Run over: Points (rest surface in input 1)
```vex
// capture each point against a rest surface (input 1): store prim, uv and normal offset.
int prim; vector uv;
float d   = xyzdist(1, @P, prim, uv);
vector sp = primuv(1, "P", prim, uv);
vector sn = normalize(primuv(1, "N", prim, uv));
i@caprim   = prim;
v@capuv    = uv;
f@capoff   = dot(@P - sp, sn);       // signed height above the surface
// deform pass (prose): read the DEFORMED surface at caprim/capuv, push out by capoff along its N.
```
`xyzdist` finds the closest point on the rest surface and hands back the primitive and its parametric
`uv`; `primuv` then samples any attribute at that exact spot. Storing `caprim`/`capuv` plus the signed
normal offset `capoff` records where each point lives *relative to the surface*, not in world space. A
second wrangle wired to the deformed surface reads the same `caprim`/`capuv`, samples the new `P` and `N`,
and sets `@P = sampledP + capoff * sampledN` — the points now follow the deformation. This is the core of
Point Deform and of sticking scattered detail onto animated geo.

### Non-uniform per-copy scale
Squash and stretch copies independently per axis, or bake scale into a full transform.
Run over: Points
```vex
// per-axis scale via a vector pscale, plus a full 3x3 for shear/stretch instancing.
v@scale = set(fit01(f@mask,0.5,2.0), 1.0, fit01(noise(@P*0.7),0.5,2.0));
// or bake scale straight into a transform the copy uses instead of orient/pscale:
matrix3 m = ident();
scale(m, v@scale);
3@transform = m;
```
`v@scale` is the per-axis counterpart to the scalar `@pscale`; Copy-to-Points multiplies the copy's X/Y/Z
by its components, so you can flatten or elongate instances from a mask or noise. If you need shear or a
combination of rotation and non-uniform scale that a quaternion can't express, author the full `3@transform`
matrix instead — it sits at the top of the precedence stack and replaces `orient`/`pscale`/`N`+`up`
entirely. `scale(m, v)` multiplies the matrix in place; compose it with a rotation matrix for a complete
per-copy transform.

### Look-at aiming
Point every copy at a shared target — billboards facing camera, eyes, turrets tracking a goal.
Run over: Points
```vex
// aim every copy's Z axis at a shared target position (billboards, eyes, turrets).
vector target = chv("target");
vector up     = chv("up");
matrix3 m     = lookat(@P, target, up);   // rotation aiming +Z from @P toward target
p@orient      = quaternion(m);
```
`lookat(from, to, up)` returns a matrix3 whose +Z axis points from `from` toward `to`, with `up`
stabilizing the roll — exactly the frame you want for aimed copies. Feeding it each point's own `@P` as
`from` makes every copy turn to face the target individually. For camera-facing billboards, pass the
camera position as the target; drive `target` from a moving null to make a field of copies track it. As
always, model the instanced geo facing +Z so it aims correctly.

### Pick a variant by index
Choose one of several source shapes per copy, deterministically, and tag which was chosen.
Run over: Points
```vex
// pick one of N variants deterministically, and name a piece to instance by string.
int nv     = chi("num_variants");
i@variant  = int(rand(@id * 2.71) * nv) % nv;
s@instance = sprintf("/obj/library/var_%d", i@variant);   // path a Copy-to-Points can pick
@Cd        = chramp("variant_tint", float(i@variant) / max(nv - 1, 1));
```
`i@variant` is the conventional integer index a Copy-to-Points (in "Piece Attribute" mode) reads to pick
which packed source to stamp on each point. Seeding it with `rand(@id)` gives a stable, repeatable
distribution; the `% nv` guards the rare `rand`-returns-1.0 case from overflowing the count. The
`s@instance` string attribute is the alternative selection path — Copy-to-Points and the older Instance
workflow can read a full node/file path per point, letting you mix entirely different assets.

### Twist copies along a spine
Rotate copies progressively down a curve for drills, vines, DNA, or candy-cane stripes.
Run over: Points (curve)
```vex
// progressive twist down a curve: orient from tangent, then roll by arc fraction.
int prev = max(@ptnum - 1, 0);
int next = min(@ptnum + 1, @numpt - 1);
vector tang = normalize(point(0,"P",next) - point(0,"P",prev));
float  u    = float(@ptnum) / max(@numpt - 1, 1);
matrix3 m   = maketransform(tang, chv("up"));
vector4 q   = quaternion(m);
vector4 roll = quaternion(u * radians(ch("total_twist")), tang);
p@orient    = qmultiply(roll, q);
```
The base frame comes from the tangent as before; the twist is an extra rotation about that tangent whose
angle scales with `u`, the fraction of the way along the curve. So the first point has no roll and the last
has the full `total_twist` — a linear spiral. `u` here is the point-index fraction, which is only true
arc-length if the curve is evenly resampled; compute a real arc-length parameter for uneven curves.
Multiplying `roll * q` applies the twist about the (world-space) tangent, which is what a spine twist wants.

---

## Procedural noise (fractal, worley, curl)

The base noise section covers the raw generators; this one is about *shaping* them into production detail.
Three ideas do most of the work. **Layering**: one octave of `noise()` is bland, so sum several at rising
frequency and falling amplitude (fBm) for natural, multi-scale detail. **Type**: value/Perlin noise
(`noise`), cellular/Worley (`wnoise`) for cells and cracks, and divergence-free `curlnoise` for flow each
have a distinct signature you reach for deliberately. **Shaping**: raw noise is a mushy 0..1 blob — `fit`,
`pow`, `chramp`, and quantization turn it into masks, bands, or crisp thresholds. Two habits keep results
stable: seed per-element randomness from a stable `@id` (never `nrandom`, which changes every call), and
sample in a rest space (`v@rest`) so a pattern rides deformation instead of swimming through it.

### fBm by hand
Sum octaves of noise for natural detail you fully control — the basis of most procedural texture.
Run over: Points
```vex
// fractional Brownian motion: sum octaves, each higher frequency + lower amplitude.
float freq = chf("freq"), amp = chf("amp");
float gain = chf("gain"), lac = chf("lacunarity");
int   oct  = chi("octaves");
float sum = 0, a = amp;
vector pp = @P * freq;
for (int i = 0; i < oct; i++) {
    sum += a * (noise(pp) - 0.5) * 2.0;   // signed octave
    pp  *= lac;                            // frequency *= lacunarity
    a   *= gain;                           // amplitude *= gain
}
f@fbm = sum;
```
Each pass adds a finer, quieter layer of noise. `lacunarity` (typically ~2.0) sets how much the frequency
jumps per octave and `gain` (typically ~0.5) how fast amplitude decays — together they control the
roughness. Recentring each octave to signed range `(noise-0.5)*2` keeps the sum balanced around zero so it
reads as displacement rather than a one-sided bias. Four to six octaves is usually plenty; more just adds
sub-pixel detail you won't see.

### Billowy turbulence
Sum the *absolute* value of signed octaves for puffy, cloud- and smoke-like structure.
Run over: Points
```vex
// turbulence: sum of ABSOLUTE signed octaves -> billowy, cloud-like, always positive.
float freq = chf("freq");
int   oct  = chi("octaves");
float sum = 0, a = 1.0;
vector pp = @P * freq;
for (int i = 0; i < oct; i++) {
    sum += a * abs((noise(pp) - 0.5) * 2.0);
    pp  *= 2.0;
    a   *= 0.5;
}
f@turb = sum;
```
The only change from fBm is the `abs()`: folding each octave at zero creates creases wherever the signed
noise crosses zero, and stacking them yields the billowy, cauliflower texture of clouds and smoke. Because
every term is positive the result is always ≥ 0, so it maps naturally to density. This is the classic
"turbulence" of procedural texturing; feed it into a `chramp` to carve cloud edges.

### Ridged noise
Invert folded noise for sharp mountain ridges and vein-like crests.
Run over: Points
```vex
// ridged multifractal: invert the folded absolute noise to get sharp crests.
float freq = chf("freq");
int   oct  = chi("octaves");
float sum = 0, a = 1.0;
vector pp = @P * freq;
for (int i = 0; i < oct; i++) {
    float n = 1.0 - abs((noise(pp) - 0.5) * 2.0);  // fold -> ridge at 1
    sum += a * n * n;                               // square sharpens the crest
    pp  *= 2.0;
    a   *= 0.5;
}
f@ridge = sum;
```
Where turbulence sums the folded noise, ridged noise *inverts* it (`1 - abs(...)`), so the creases become
peaks: the value spikes to 1 exactly where the noise crosses zero. Squaring each octave sharpens those
crests into thin ridges, giving the eroded-mountain and dried-riverbed look. Use it as a heightfield offset
or a mask for veins and cracks; combine with fBm for a base-plus-ridges terrain.

### Worley / cellular cells and cracks
Cellular noise for stone, cracked mud, scales, or a Voronoi-edge mask.
Run over: Points
```vex
// cellular / Worley pattern: f1 = nearest feature dist, f2 = second -> cracks = f2-f1.
int   seed = chi("seed");
float f1, f2;
wnoise(@P * chf("freq"), seed, f1, f2);
f@cell   = f1;                 // rounded cell bumps
f@crack  = f2 - f1;            // thin borders between cells (Voronoi edges)
i@cellid = seed;               // stable id of the owning cell
```
`wnoise` scatters feature points through space and returns the distance to the nearest (`f1`) and second
nearest (`f2`) via output parameters. `f1` alone gives rounded cell interiors (0 at each feature, rising
outward); `f2 - f1` is near zero along the equidistant borders between cells, drawing the thin Voronoi
cracks used for stone and dried mud. The `seed` output identifies which cell a point belongs to — perfect
for a per-cell random color or a shatter id.

### Curl-noise flow displacement
Advect points along a divergence-free field for wispy, swirling, volume-preserving motion.
Run over: Points
```vex
// divergence-free flow: advect points a little along an evolving curl field.
vector4 pp = set(@P.x, @P.y, @P.z, @Time * chf("evolve")) * chf("freq");
vector flow = curlnoise(pp);
v@flow = flow;
@P += flow * chf("amp");
```
`curlnoise` is the curl of a noise field, so it is divergence-free: points swirl and fold without piling
into sinks or tearing apart the way raw vector noise would. Passing the 4D `vector4` overload with `@Time`
in the fourth slot evolves the field over time, so a static point still drifts on a changing current. Store
the raw `flow` if a downstream step needs the velocity; scale the displacement by a small `amp` and apply
it repeatedly (over frames, in a solver) for a proper advection.

### 4D animated noise
Animate a 3D pattern smoothly by using time as a fourth coordinate — no sliding artifacts.
Run over: Points
```vex
// animate a 3D pattern by feeding time as the 4th coordinate (no visible sliding).
vector4 pp = set(@P.x, @P.y, @P.z, @Time) ;
float n = noise(pp * chf("freq"));
f@n4 = fit01(n, 0, 1);
```
The naive way to animate noise — adding time to one spatial axis — makes the pattern visibly slide in that
direction. Feeding time as an independent fourth dimension instead lets the whole field morph in place, the
way clouds boil rather than scroll. `noise()` has a `vector4` overload for exactly this; scale the whole
4-vector by `freq` (or give time its own rate) to control how fast it churns versus how fine it is.

### Remap and add contrast
Raw noise sits in a soft mid-range; stretch, gamma, and ramp it into a usable signal.
Run over: Points
```vex
// raw noise is mushy 0..1; fit + a gamma/contrast shove + ramp make it usable.
float n = noise(@P * chf("freq"));
n = fit(n, chf("lo"), chf("hi"), 0, 1);       // stretch the useful band to 0..1
n = clamp(n, 0, 1);
n = pow(n, chf("contrast"));                  // >1 darkens, <1 lifts
@Cd = chramp("palette", n);
f@shaped = n;
```
`noise` rarely uses its full 0..1 range, so `fit(n, lo, hi, 0, 1)` picks the band you care about and
expands it (clamp guards the tails). `pow(n, contrast)` is a gamma curve — above 1 pushes values toward
black, below 1 toward white — which sharpens or softens the mask cheaply. Finishing through `chramp` lets
an artist reshape or recolor the result on the node without touching the code, the single most useful habit
in procedural work.

### Flow noise
A smoothly rotating noise field — swirling, non-repeating detail that value noise can't give.
Run over: Points
```vex
// flow noise: a smoothly ROTATING gradient field - good for swirling, non-repeating detail.
float n = flownoise(@P * chf("freq"), @Time * chf("flow"));
f@flown = fit(n, -0.5, 0.5, 0, 1);
```
`flownoise` rotates the underlying gradients by the `flow` argument, so animating that argument makes the
texture swirl in place rather than translate — a cheaper cousin of curl-noise for scalar detail like moving
clouds or flowing water surfaces. The output is signed (roughly -0.5..0.5), so `fit` it into 0..1 before
using it as a mask. Drive `flow` from `@Time` for animation, or from an attribute for spatially varying
swirl.

### Domain warping
Distort noise by *another* noise for organic, marbled, liquid-looking swirls.
Run over: Points
```vex
// domain warping: offset the sample position by ANOTHER noise for organic, marbled swirl.
float warp = chf("warp");
vector q = set(noise(@P*chf("freq") + 11.3),
               noise(@P*chf("freq") + 47.1),
               noise(@P*chf("freq") + 93.7)) - 0.5;
float n = noise((@P + q * warp) * chf("freq"));
f@warped = fit01(n, 0, 1);
```
Instead of sampling noise at `@P`, you sample it at `@P` *pushed around* by a second noise vector `q`. That
displacement of the input domain bends the pattern's contours into swirls and folds — the marble, magma,
and fingerprint look that flat noise never produces. The three offset constants decorrelate the X/Y/Z of
`q` so the warp isn't a uniform slide. Warp strength (`warp`) is the whole effect; feed the warped result
back in for a second pass to intensify it.

### Seeded deterministic variation
Give each element a stable random value — repeatable across frames, caches, and machines.
Run over: Points
```vex
// deterministic per-element randomness: rand() is repeatable from a seed; nrandom is NOT.
float r  = rand(@id * 1.7);          // stable: same @id -> same value every cook
i@variant = int(rand(@id * 5.3) * chi("variants"));
float rv  = fit(rand(set(@id, 2, 9)), 0, 1, chf("lo"), chf("hi"));
f@rval    = rv;
```
`rand()` (and `random()`) are hash functions: the same seed always yields the same value, which is exactly
what you want for per-element variation that must survive caching and re-cooking. Multiplying `@id` by
different constants decorrelates independent draws so scale, variant, and tint don't move in lockstep;
seeding from a `vector` (`set(@id,2,9)`) is a quick way to get a differently-decorrelated stream. Never use
`nrandom` here — it returns a fresh value every call and will flicker frame to frame.

### Random direction on a sphere
An unbiased random unit vector — for scatter kicks, jitter, or random axes.
Run over: Points
```vex
// an evenly-distributed random direction on the unit sphere (jitter, scatter kicks).
vector2 u = set(rand(@id*1.1), rand(@id*9.4));
v@dir = sample_direction_uniform(u);   // unit vector, no pole bias
```
Normalizing three independent randoms clusters directions toward the cube's corners; `sample_direction_uniform`
maps two 0..1 inputs to a genuinely even distribution over the sphere with no pole pinching. Feed it two
decorrelated `rand()` streams seeded from `@id` so the direction is stable per point. Use it for scatter
push-off directions, random spin axes, or seeding velocities.

### Rest-space noise
Sample noise in rest position so the pattern sticks to the surface as it deforms.
Run over: Points
```vex
// sample noise in REST space so the pattern sticks to the surface as it deforms.
vector sp = hasattrib(0, "point", "rest") ? v@rest : @P;
f@restmask = fit01(noise(sp * chf("freq")), 0, 1);
```
If you sample noise at the live `@P`, the pattern is fixed in world space and the geometry swims through it
as it animates. Sampling at a captured rest position (`v@rest`, written before deformation) locks the
pattern to the surface so it deforms *with* the mesh — essential for displacement, masks, and textures on
anything that moves. Guarding with `hasattrib` falls back to `@P` when no rest exists, so the wrangle is
safe on static geo too.

### Stepped / quantized noise
Snap continuous noise into flat bands for terraces or cell-shaded looks.
Run over: Points
```vex
// quantize continuous noise into flat bands for terraces / cell-shaded looks.
float n = noise(@P * chf("freq"));
int   steps = chi("steps");
f@bands = rint(n * steps) / float(steps);   // snap to nearest of `steps` levels
```
Multiplying by `steps`, rounding with `rint`, then dividing back collapses the smooth gradient into
`steps` discrete plateaus — the sedimentary terraces of eroded rock or the posterized banding of a toon
shade. More `steps` means finer bands; `floor` instead of `rint` biases every band downward if you prefer
hard risers. Combine with a small amount of the original noise added back for softened, imperfect steps.

### Anti-aliased threshold
Soften a hard noise cutoff into a controllable-width edge instead of a jagged binary mask.
Run over: Points
```vex
// soft-edged threshold: a smoothstep of half-width w instead of a hard n>t cut.
float n = noise(@P * chf("freq"));
float t = chf("threshold");
float w = chf("softness");
f@aa = smooth(t - w, t + w, n);   // 0 below t-w, 1 above t+w, ramp between
```
A raw `n > t` test produces a crunchy, aliased boundary; `smooth(t-w, t+w, n)` replaces the step with a
smoothstep ramp of half-width `w`, giving a soft transition you can feather. Widen `w` for a gradual blend
(dissolves, wet-map edges), narrow it toward a crisp but still smooth line. This is the geometry-attribute
analogue of the anti-aliased edges you'd get from `fwidth` in a shader, but with the width under explicit
artistic control.

---

## Point clouds & proximity

Point-cloud functions let one point read its neighbours without a dedicated node — the basis of blurring,
density, curvature, and flocking done in a single wrangle. The pattern is always the same: `pcopen(input,
"P", @P, radius, maxpts)` returns a handle to the points within `radius` (capped at `maxpts`), and you then
either `pcfilter(handle, "attr")` for a quick distance-weighted average, or loop with `while
(pciterate(handle))` + `pcimport` to accumulate anything custom. Two lighter tools cover single-target
queries: `nearpoint`/`nearpoints` return point *numbers* to read with `point()`, and `xyzdist`/`minpos`
snap to the nearest spot on a *surface* (not just its points). Always exclude the query point from its own
neighbourhood (`if (nb == @ptnum) continue;`) when the cloud is the same geometry you are running over —
otherwise every result is biased toward itself.

### Blur an attribute over neighbours
Smooth any attribute by averaging it over the nearest N points — a node-free blur.
Run over: Points
```vex
// average an attribute over the N nearest points -> a one-wrangle blur.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
@Cd  = pcfilter(h, "Cd");        // distance-weighted mean of neighbour Cd
f@smask = pcfilter(h, "mask");
```
`pcfilter` returns the distance-weighted mean of a named attribute over the open handle — closer neighbours
count more — which is exactly an attribute blur. Larger `radius` or `maxpts` widens the smoothing; run the
wrangle several times for a stronger blur. Because `pcopen` on input 0 includes the point itself, its own
value is part of the average, which is fine for smoothing (see *self-exclude* when it is not).

### Custom neighbour reduction
When `pcfilter`'s weighting isn't what you want, iterate and accumulate by hand.
Run over: Points
```vex
// custom neighbour reduction: falloff-weighted average done by hand (pcfilter can't).
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
float acc = 0, wsum = 0;
while (pciterate(h)) {
    float d; pcimport(h, "point.distance", d);
    float m; pcimport(h, "mask", m);
    float w = pow(1.0 - d / chf("radius"), 2);   // squared linear falloff
    acc  += m * w;
    wsum += w;
}
f@wavg = wsum > 0 ? acc / wsum : f@mask;
```
The `pciterate` loop visits each neighbour once; `pcimport` pulls named channels off the current neighbour,
including the special `point.distance` and `point.number`. Here a squared linear falloff weights close
points far more strongly than `pcfilter`'s built-in weighting, and normalizing by `wsum` keeps the result
in the attribute's range. This manual form is the escape hatch for any reduction — medians, maxima,
conditional sums — that `pcfilter` can't express.

### Nearest point and its attribute
Grab the single closest point in another input and read one of its values.
Run over: Points (reference cloud in input 1)
```vex
// nearest single point in another input + read one of its attributes.
int   pt = nearpoint(1, @P);
vector c = point(1, "Cd", pt);
float  m = point(1, "mask", pt);
@Cd      = c;
f@nmask  = m;
```
`nearpoint(1, @P)` returns the *number* of the closest point in input 1, which `point()` then reads any
attribute from. This is the cheapest proximity query — one point, one lookup — for snapping a value off a
reference cloud (nearest color, nearest id, nearest temperature). Add a `maxdist` argument to return -1
when nothing is close enough, and guard the `point()` call against that -1.

### Points within a radius
Get every neighbour inside a radius as an array and blur with an explicit weight.
Run over: Points
```vex
// all points within a radius as an array, then a manual inverse-distance blur.
int nb[] = nearpoints(0, @P, chf("radius"), chi("maxpts"));
float acc = 0, wsum = 0;
foreach (int pt; nb) {
    if (pt == @ptnum) continue;
    float d = distance(@P, point(0, "P", pt));
    float w = 1.0 / (d + 1e-3);
    acc  += point(0, "mask", pt) * w;
    wsum += w;
}
f@rblur = wsum > 0 ? acc / wsum : f@mask;
i@ncount = len(nb);
```
`nearpoints` returns an array of point numbers instead of a `pcopen` handle — handy when you want to index
the neighbours directly, sort them, or reuse the list. Here an inverse-distance weight (`1/(d+eps)`) makes
the blur fall off sharply with distance; the `+1e-3` avoids a divide-by-zero when a point coincides with a
neighbour. `len(nb)` doubles as a neighbour count. Skipping `pt == @ptnum` excludes the point from its own
blur.

### Distance to the nearest surface
Measure how far each point is from a surface and where the closest spot is.
Run over: Points (surface in input 1)
```vex
// distance to the nearest surface + the exact closest point on it (input 1).
int prim; vector uv;
float d  = xyzdist(1, @P, prim, uv);
vector sp = primuv(1, "P", prim, uv);
f@surfd  = d;
v@surfp  = sp;
```
Unlike `nearpoint`, which only finds vertices, `xyzdist` finds the closest point *on the surface itself* —
anywhere across a primitive's face — returning the distance plus the primitive number and its parametric
`uv`. Feeding that `prim`/`uv` into `primuv` samples the exact surface position (or any other attribute) at
the closest spot. The distance `f@surfd` makes a clean falloff mask around geometry; `v@surfp` is the snap
target for projecting points onto the surface.

### Neighbour count as density
Count how many points fall in a radius to estimate local density for masks.
Run over: Points
```vex
// count neighbours in a radius as a cheap density estimate for masks.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
int  n = pcnumfound(h) - 1;                        // minus self
float area = $PI * chf("radius") * chf("radius");
i@ncount  = n;
f@density = n / area;
```
`pcnumfound` reports how many points the handle actually captured; subtracting one removes the query point
itself. Dividing by the search disc's area turns the raw count into a comparable density (points per unit
area) rather than a radius-dependent number. Watch the `maxpts` cap — if the true neighbour count exceeds
it, the count saturates and under-reports dense regions, so set `maxpts` generously when measuring density.

### Curvature from normal variance
A cheap surface-roughness proxy: how much do neighbouring normals disagree?
Run over: Points
```vex
// curvature/roughness proxy: 1 - length(mean neighbour normal). Flat->0, bumpy->1.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
vector navg = pcfilter(h, "N");
f@curv = 1.0 - length(navg);
```
When neighbouring normals all point the same way (flat region) their average is near unit length, so
`1 - length` is ~0; where the surface bends, the normals cancel and the average shrinks, driving the value
toward 1. It is not true differential curvature, but it is a fast, robust roughness mask for edge wear,
dirt, or scatter density. Requires point normals upstream; widen the radius to measure curvature at a
coarser scale.

### Relax an attribute
Nudge each value toward its neighbour mean by a controllable amount — Laplacian smoothing.
Run over: Points
```vex
// Laplacian-style relax: nudge each value toward its neighbour mean by `amount`.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
float mean = pcfilter(h, "mask");
f@relax = lerp(f@mask, mean, chf("amount"));
```
Instead of replacing a value with the neighbour average outright, `lerp(current, mean, amount)` moves it
only partway — `amount` of 0 leaves it unchanged, 1 is a full blur. That partial step is Laplacian
relaxation; iterating it over frames or passes smooths a field gently without the overshoot of a single
hard blur. Use it to relax jittery masks, soften noise, or ease attribute discontinuities before a
downstream op.

### Gather a separation force
Sum inverse-distance pushes away from close neighbours — the separation half of flocking.
Run over: Points
```vex
// flocking separation: sum inverse-distance pushes away from close neighbours.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
vector push = 0;
while (pciterate(h)) {
    int nb; pcimport(h, "point.number", nb);
    if (nb == @ptnum) continue;
    vector op; pcimport(h, "P", op);
    vector d = @P - op;
    float  L = length(d);
    if (L > 1e-4) push += normalize(d) / L;
}
v@sep = push * chf("strength");
```
Each neighbour contributes a push directed away from it, scaled by `1/L` so the nearest points dominate —
that inverse falloff is what keeps elements from overlapping without a hard collision. Excluding self and
guarding tiny distances keeps the sum finite. Store it as a force or velocity nudge; combine with alignment
and cohesion (average neighbour velocity and centroid) for full boids, or use it alone to de-clump a
scatter.

### Manual attribute transfer
Transfer an attribute from another input by proximity — a hand-built Attribute Transfer with your own falloff.
Run over: Points (source in input 1)
```vex
// manual attribute transfer from input 1, radius-weighted (a hand-built Attribute Transfer).
int h = pcopen(1, "P", @P, chf("radius"), chi("maxpts"));
if (pcnumfound(h) > 0) {
    @Cd = pcfilter(h, "Cd");
    f@xfer = pcfilter(h, "mask");
} else {
    f@xfer = 0;
}
```
Opening the point cloud on *input 1* pulls neighbours from the source geometry, so `pcfilter` averages the
source's attributes onto the current point — the same job as an Attribute Transfer SOP but with the radius,
cap, and weighting fully in your hands. Guarding on `pcnumfound > 0` gives points with no nearby source a
defined fallback instead of a stale value. Swap `pcfilter` for a manual loop to weight by something other
than distance (normal agreement, id match).

### Snap points onto a surface
Project a cloud onto the nearest spot of a surface for conforming or shrink-wrapping.
Run over: Points (surface in input 1)
```vex
// snap points onto the nearest spot of a surface (input 1) - project a cloud to geo.
vector sp = minpos(1, @P);
f@snapdist = distance(@P, sp);
@P = lerp(@P, sp, chf("snap"));    // snap=1 sits exactly on the surface
```
`minpos` returns the nearest position *on* the geometry in input 1 — across faces, not just at points — in
one call, which is the quick way to project or shrink-wrap a cloud. Lerping from the original `@P` toward
that target by `snap` lets you conform fully (`snap`=1) or only pull points partway; `f@snapdist` records
how far each moved for masking. For the primitive and uv of the hit as well, use `xyzdist`+`primuv`
instead.

### Exclude self from a blur
Blur over neighbours only, so an isolated point isn't just smoothed to its own value.
Run over: Points
```vex
// blur over neighbours while EXCLUDING the query point from its own neighbourhood.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
float acc = 0; int cnt = 0;
while (pciterate(h)) {
    int nb; pcimport(h, "point.number", nb);
    if (nb == @ptnum) continue;    // skip self so a lone point isn't just itself
    float m; pcimport(h, "mask", m);
    acc += m; cnt++;
}
f@selfblur = cnt > 0 ? acc / cnt : f@mask;
```
`pcopen` on the same geometry you're running over always includes the query point, which for a plain
average is harmless but wrong for anything that should reflect *only* the surroundings — a point-relative
difference, a "how different am I from my neighbours" measure, or a fill where the point's own value is
suspect. Testing `point.number` against `@ptnum` and skipping it removes that bias; the `cnt > 0` fallback
handles a point with no neighbours in range. This self-exclude guard is the single most common point-cloud
bug.

---

## Modeling by attribute

The everyday "measure something, then let the measurement drive an op" wrangles. These run in an **Attribute Wrangle** over the class you are measuring — Primitives for area/perimeter, Points for curvature/thickness/displacement, Vertices for edge work, Detail for per-piece reductions. The pattern is always the same two halves: compute a value into an attribute or group, then feed that attribute into a downstream typed node (Polyextrude, Blast, Fuse, Scatter) or into a second wrangle. All snippets below were verified in an Attribute Wrangle over a noisy normalled grid, a closed polymesh (ray/normal idioms), and a two-piece connectivity fixture.

### Group primitives by measured area
Tag slivers and oversized faces so a cleanup node can act on them.
Run over: Primitives
```vex
// Per-prim surface area drives a cleanup/selection decision.
f@area = primintrinsic(0, "measuredarea", @primnum);
if (f@area < chf("min_area")) i@group_tiny = 1;   // slivers to fuse/dissolve
```
`primintrinsic(0, "measuredarea", @primnum)` reads the polygon's true area straight off the primitive intrinsic — no manual triangulation — and `measuredperimeter` is its edge-length sibling. Writing `i@group_tiny` builds a primitive group in one line that a downstream Fuse or Dissolve can consume. Use this to catch decimation artifacts, degenerate faces, or to weight a Scatter by face size.

### Per-primitive perimeter by summing edge lengths
Ring-walk a face to get its perimeter and a compactness ratio for degeneracy detection.
Run over: Primitives
```vex
// Walk the prim's point ring and accumulate edge lengths (closed loop).
int pts[] = primpoints(0, @primnum);
int n = len(pts);
float per = 0.0;
for (int i = 0; i < n; i++) {
    vector a = point(0, "P", pts[i]);
    vector b = point(0, "P", pts[(i + 1) % n]);
    per += distance(a, b);
}
f@perimeter = per;
// compactness: area-to-perimeter, low = stringy/degenerate prims
f@compact = (per > 0.0) ? primintrinsic(0,"measuredarea",@primnum) / (per*per) : 0.0;
```
`primpoints` returns the ordered point ring of the face; the modulo close (`(i+1) % n`) wraps the last edge back to the first so the loop is closed. Dividing area by perimeter-squared gives a scale-independent compactness score — near `1/(4π)` for a circle, tiny for stringy or needle prims — which is a robust degeneracy flag. If you only need the number, the `measuredperimeter` intrinsic is the shortcut; the loop is here because the same ring-walk generalizes to any per-edge measurement.

### Signed convex/concave curvature from neighbour offset
A signed edge-wear/cavity mask: positive on ridges, negative in valleys.
Run over: Points
```vex
// Mean neighbour position vs @P, projected on @N: + = convex ridge, - = concave valley.
int nb[] = neighbours(0, @ptnum);
int n = len(nb);
if (n > 0) {
    vector avg = {0,0,0};
    foreach (int p; nb) avg += point(0, "P", p);
    avg /= float(n);
    f@curv = dot(@P - avg, @N) * chf("gain");   // signed
    f@wear = fit(f@curv, 0.0, chf("edge"), 0.0, 1.0);  // convex-edge mask 0..1
}
```
`neighbours(0, @ptnum)` returns the connected points; their average is the local surface centroid, and the vector from that centroid to `@P` projected onto `@N` is a cheap discrete mean-curvature. The sign is the whole point — convex edges (for chipping/wear) read positive, concave cavities (for dirt/occlusion) read negative — which a symmetric normal-variance proxy cannot give you. Requires valid `@N`; add a Normal SOP upstream or the projection collapses to zero.

### Per-point shell thickness by an inward ray
Measure wall thickness by shooting a ray back into the solid along -N.
Run over: Points
```vex
// Fire a ray back into the mesh along -N; the first self-hit distance is wall thickness.
vector hitP, hitUV;
vector start = @P - @N * 1e-3;              // nudge inside to avoid self-hit at origin
int pr = intersect(0, start, -@N * chf("maxdist"), hitP, hitUV);
f@thickness = (pr >= 0) ? distance(@P, hitP) : chf("maxdist");
if (f@thickness < chf("thin")) i@group_thin = 1;   // shell too thin -> reinforce
```
`intersect(0, origin, direction, hitP, hitUV)` casts a ray against input 0 itself and returns the hit primitive (or `-1` for a miss), writing the hit position into `hitP`. Nudging the start point slightly inside along `-N` avoids the ray immediately striking the face it launched from. This is the standard way to find thin walls before a shell/erosion pass, or to detect self-penetration; flip the ray direction to measure clearance to the *outside* instead.

### Flip inward-facing prims outward from the centroid
Fix inconsistent winding by comparing each face normal to the outward direction.
Run over: Primitives
```vex
// Compare each face normal to the outward direction (face center - object center).
vector oc = getbbox_center(0);
int pts[] = primpoints(0, @primnum);
vector fc = {0,0,0};
foreach (int p; pts) fc += point(0, "P", p);
fc /= float(len(pts));
vector fn = prim_normal(0, @primnum, 0.5, 0.5);
if (dot(fn, normalize(fc - oc)) < 0.0) {
    setprimintrinsic(0, "revert", @primnum, 1);   // reverse winding of this prim
    i@group_flipped = 1;
}
```
`prim_normal(0, prim, u, v)` gives the geometric normal at the face center without needing a point-normal attribute; comparing it to the outward direction (face center minus object center) tells you if the face is inside-out. `setprimintrinsic(0, "revert", @primnum, 1)` flips that primitive's vertex order in place, which is the winding-only fix the Reverse SOP applies globally. The centroid test assumes a roughly convex, closed shape — for complex concave meshes, seed the outward reference from a ray or a known-good normal instead.

### Controlled push along N with a ramp falloff
Displace inside a mask with an artist-shaped falloff instead of a hard on/off.
Run over: Points
```vex
// Displace only inside a mask, shaped by a ramp so the push feathers off smoothly.
float m = clamp(f@wear, 0.0, 1.0);            // 0..1 mask authored upstream
float amt = chramp("falloff", m) * chf("height");
@P += @N * amt;
```
`chramp("falloff", m)` remaps the 0..1 mask through a ramp parameter on the wrangle, so the user sculpts the displacement profile with a curve rather than by editing VEX. Multiplying by `@N` keeps the push surface-aligned. Keep the ramp anchored at 0 on the left so masked-out regions stay put; drive `f@wear` from the signed-curvature idiom above for edge-only growth.

### Stable per-primitive seed + variant pick
A recook-stable random seed for shatter/variation that does not shift when topology changes.
Run over: Primitives
```vex
// A hashed, topology-independent seed so shatter/variation stays put across recooks.
i@id = @primnum;
float r = rand(i@id * 2 + 17);
f@rand = r;
i@variant = int(r * chi("nvariant"));         // pick one of N looks
f@rot = r * 360.0;                            // per-piece spin, degrees
```
`rand(seed)` is a deterministic hash — the same integer always yields the same float — so baking the seed into `@id` early keeps per-piece randomness locked even after the point/prim numbering later changes. `int(r * chi("nvariant"))` buckets the float into N discrete variants for copy-stamping different meshes. Prefer a real stable `@id` over raw `@primnum` if a Fuse or Sort sits between here and the sim.

### Point valence for pole and boundary detection
Classify poles and open-boundary points from their connected-edge count.
Run over: Points
```vex
// neighbourcount = connected-edge count; open-boundary points differ from interior.
int v = neighbourcount(0, @ptnum);
i@valence = v;
if (v <= chi("bound_max")) i@group_boundary = 1;   // e.g. <=3 on an open edge
if (v >= chi("pole_min"))  i@group_pole = 1;        // e.g. >=6 star pole
```
`neighbourcount(0, @ptnum)` returns how many points share an edge with this one — its valence. On a clean quad grid interior points have valence 4; open borders drop to 2–3 and extraordinary poles rise to 5+, so simple thresholds isolate each. Boundary and pole groups feed cleanup, selective bevels, or subdivision-artifact hunting.

### Flag short edges per vertex for cleanup
Mark short edges for a targeted Fuse/Dissolve without collapsing the whole mesh.
Run over: Vertices
```vex
// Each vertex owns the edge to the next vertex in its primitive; measure it.
int pr = vertexprim(0, @vtxnum);
int pv[] = primvertices(0, pr);
int local = vertexprimindex(0, @vtxnum);
int nvtx = pv[(local + 1) % len(pv)];
vector a = point(0, "P", vertexpoint(0, @vtxnum));
vector b = point(0, "P", vertexpoint(0, nvtx));
f@edgelen = distance(a, b);
if (f@edgelen < chf("min_edge")) i@group_shortedge = 1;
```
Running over vertices makes each half-edge its own element: `vertexprimindex` gives the vertex's position within its primitive, and stepping `(local+1) % len` finds the next vertex around the face. `vertexpoint` converts each vertex to its point so `distance` measures the world edge length. Vertex groups convert cleanly to edge groups downstream; use this to drive an adaptive Fuse threshold or to catch decimation slivers before subdivision.

### Per-connectivity-piece centroid + size (detail reduction)
One detail pass that computes a bounding box per connected piece into indexed arrays.
Run over: Detail (only once)
```vex
// One pass over a two-piece mesh: accumulate a bbox per @class into arrays.
int np = npoints(0);
vector cmin[]; vector cmax[]; vector csum[]; int ccount[];
for (int i = 0; i < np; i++) {
    int cl = point(0, "class", i);
    vector p = point(0, "P", i);
    while (len(ccount) <= cl) { append(cmin, 1e18); append(cmax, -1e18);
                                append(csum, {0,0,0}); append(ccount, 0); }
    cmin[cl] = min(cmin[cl], p);
    cmax[cl] = max(cmax[cl], p);
    csum[cl] += p;
    ccount[cl] += 1;
}
for (int c = 0; c < len(ccount); c++) {
    if (ccount[c] > 0) {
        setdetailattrib(0, sprintf("centroid%d", c), csum[c] / float(ccount[c]), "set");
        setdetailattrib(0, sprintf("size%d", c), cmax[c] - cmin[c], "set");
    }
}
i@npieces = len(ccount);
```
A Detail wrangle runs once, so it is the safe place to accumulate across all elements — parallel point wrangles cannot reduce like this. Indexing the arrays by `@class` (from a Connectivity SOP) grows them on demand with the `while(len <= cl)` guard, so you never assume a piece count. The result is a compact per-piece summary you can read back with `detail()` for placement, labelling, or per-cluster instancing. For a single value per element instead, promote with an Attribute Promote node — this hand-rolled version is for when you need several stats at once.

### Delete primitives where a measured mask crosses
Attribute-driven culling — remove faces whose averaged mask exceeds a cut.
Run over: Primitives
```vex
// Attribute-driven removal: cull prims whose averaged point mask exceeds a cut.
int pts[] = primpoints(0, @primnum);
float m = 0.0;
foreach (int p; pts) m += point(0, "wear", p);
m /= float(len(pts));
if (m > chf("cut")) removeprim(0, @primnum, 1);   // 1 = also delete orphaned points
```
`removeprim(0, @primnum, 1)` deletes the current face and, with the trailing `1`, also removes points left with no other prim — the manual equivalent of a Blast by group with "Delete Non-Selected" off. Averaging a point mask up to the primitive avoids ragged single-point deletions. This is a Blast you can shape with arbitrary logic; for non-destructive workflows write the group instead and Blast downstream so the decision stays editable.

### UV-free triplanar procedural mask from @P
Wrap a noise pattern around geometry with no UVs by blending three axis projections.
Run over: Points
```vex
// Blend three axis-plane noises by |N| so a pattern wraps geometry without UVs.
float sc = chf("scale");
vector w = pow(abs(@N), chf("sharp"));          // projection weights
w /= max(w.x + w.y + w.z, 1e-6);
float nx = noise(set(@P.y, @P.z, 0) * sc);      // project on YZ
float ny = noise(set(@P.x, @P.z, 0) * sc);      // project on XZ
float nz = noise(set(@P.x, @P.y, 0) * sc);      // project on XY
f@mask = nx * w.x + ny * w.y + nz * w.z;
```
Each face-aligned projection samples 2D noise on one coordinate plane; weighting them by `pow(abs(@N), sharp)` picks whichever projection faces most squarely and cross-fades at 45° edges. Normalizing the weights keeps the blend energy-preserving, and `sharp` tightens or softens the seam between projections. This is the geometry-side twin of a triplanar shader — perfect for procedural dirt, damage, or scatter masks on un-UV'd scan data.

### Author a tangent-basis matrix3 for anisotropy
Build an orthonormal surface frame (tangent, bitangent, normal) for anisotropic looks or combing.
Run over: Points
```vex
// Build an orthonormal frame (tangent, bitangent, N) from a neighbour edge.
int nb[] = neighbours(0, @ptnum);
if (len(nb) > 0) {
    vector edge = point(0, "P", nb[0]) - @P;
    vector t = normalize(edge - @N * dot(edge, @N));   // tangent in the surface plane
    vector b = cross(@N, t);
    3@frame = set(t.x,t.y,t.z, b.x,b.y,b.z, @N.x,@N.y,@N.z);
    v@tangentu = t;                                    // e.g. hair/anisotropy direction
}
```
Projecting a neighbour edge onto the tangent plane (`edge - N*dot(edge,N)`) removes its normal component, giving a surface-lying tangent; `cross(N, t)` completes a right-handed basis. Packing the three axes into a `matrix3` gives a per-point frame you can hand to anisotropic shading, hair grooming, or oriented copies. The frame's twist follows `nb[0]`, so for smoothly varying combing seed the tangent from a rest direction or a guide curve rather than an arbitrary neighbour.

### Extrude/peak height driven by a measured attribute
Variable extrusion — push points along N by an amount read from an attribute.
Run over: Points
```vex
// Push each point along N by an amount read from an attribute -> variable extrude.
float amt = fit(f@wear, chf("lo"), chf("hi"), 0.0, chf("max_peak"));
@P += @N * amt;
f@peak = amt;                                   // keep the amount for downstream use
```
`fit` remaps the driving attribute's working range into a displacement height, so a measured value (curvature, occlusion, a painted mask) becomes a per-point extrude amount. Storing the amount back as `f@peak` lets a later node taper, color, or reverse the push. This is the wrangle behind "peak by attribute"; feed it into a Polyextrude's Local Control attribute instead of moving `@P` directly when you need real side walls rather than a soft peak.

### Resample an attribute from a reference surface
Steal any attribute from a second surface by its nearest point — a manual attribute transfer.
Run over: Points
```vex
// Nearest point on input-1's surface gives a prim+uv to sample any of its attributes.
int pr = -1; vector uv = 0;
float d = xyzdist(1, @P, pr, uv);
if (pr >= 0) {
    @Cd   = primuv(1, "Cd", pr, uv);
    f@ref_wear = primuv(1, "wear", pr, uv);
    f@refdist = d;
}
```
`xyzdist(1, @P, pr, uv)` finds the closest point on input 1's surface and writes back which primitive it landed on plus the parametric `uv` there; `primuv(1, attr, pr, uv)` then samples any attribute at that exact spot. Because it interpolates across the face, the result is smooth even when the two meshes have different resolutions — unlike a point-to-point copy. This is Attribute Transfer with full control: gate by `d` to limit range, or sample several attributes in one pass.

---

## UV & texture

UV work in VEX turns on one fact: **UVs almost always live on vertices, not points**, so that a shared point can carry different UVs on either side of a seam. That means most of these run in a **Vertex** Attribute Wrangle (`v@uv` per vertex), while per-island measurement and rescaling run over **Primitives**. Read the owning point with `vertexpoint`, the owning primitive with `vertexprim`. All snippets were verified over a grid carrying a vertex `uv`, a second uv-bearing grid on input 1 for transfer, and a shipped texture map for the `texture()` lookup.

### Planar UV from the bounding box (@P -> 0..1)
The simplest projection: map world position across the bbox into 0..1 UV space.
Run over: Vertices
```vex
// Project onto a chosen axis pair; relbbox maps world @P into 0..1 across the bbox.
int pt = vertexpoint(0, @vtxnum);
vector rel = relbbox(0, point(0, "P", pt));
v@uv = set(rel.x, rel.z, 0.0) * chf("tile");    // top-down XZ projection
```
`relbbox(0, P)` returns the position as a 0..1 fraction across the geometry's bounding box, so picking two of its components gives an instant planar layout — here the XZ pair for a top-down projection. Writing `v@uv` on the vertex class is what lets seams split later. Multiply by `tile` to repeat the texture; swap which components you read to project down a different axis.

### Carry a point value onto the vertex uv (class gotcha)
Convert any point-space quantity into a vertex UV, respecting the point-vs-vertex split.
Run over: Vertices
```vex
// uv lives on VERTICES so seams can split; read the owning point, write the vertex.
int pt = vertexpoint(0, @vtxnum);
vector p = point(0, "P", pt);
float ang = atan2(p.z, p.x);                    // any point-space value...
v@uv = set(fit(ang, -PI, PI, 0, 1), fit(p.y, -1, 1, 0, 1), 0.0);  // ...becomes a vertex uv
```
`vertexpoint(0, @vtxnum)` bridges the two domains — you read from the point but write to the vertex, which is the correct place for UVs. This example turns an angle into a wrap coordinate, but the structure is general: compute anything in point space, land it on the vertex. If you author `uv` as a *point* attribute instead, every seam UV will be averaged into a smear — that is the single most common UV mistake in VEX.

### Cylindrical UV projection around Y
Wrap a label or pipe texture by angle around the up axis, height along V.
Run over: Vertices
```vex
// Angle about the up axis -> u; height -> v. Classic label/pipe wrap.
int pt = vertexpoint(0, @vtxnum);
vector rel = relbbox(0, point(0, "P", pt)) - 0.5;
float u = atan2(rel.z, rel.x) / (2.0 * PI) + 0.5;
float v = relbbox(0, point(0, "P", pt)).y;
v@uv = set(u * chf("wrap"), v, 0.0);
```
Centering on the bbox (`relbbox - 0.5`) puts the rotation axis through the middle, and `atan2(z, x)` returns the angle in `-π..π`, which the `/(2π)+0.5` maps to a clean 0..1 wrap. Height comes straight from the vertical bbox fraction. Expect a visible seam at the ±π wrap line — place it at the back of the object, and duplicate seam vertices if a texture must tile perfectly across it.

### Spherical UV projection from the centroid
Equirectangular (lat/long) UVs from the direction to each point.
Run over: Vertices
```vex
// Longitude/latitude of the direction from center -> equirectangular uv.
int pt = vertexpoint(0, @vtxnum);
vector dir = normalize(point(0, "P", pt) - getbbox_center(0));
float u = atan2(dir.z, dir.x) / (2.0 * PI) + 0.5;
float v = acos(clamp(dir.y, -1, 1)) / PI;
v@uv = set(u, v, 0.0);
```
The direction from the bounding-box center to each point is the surface direction on a sphere; its longitude (`atan2`) and latitude (`acos` of the up-component) are exactly equirectangular UVs. Clamping the argument to `acos` guards against tiny floating-point overshoots past ±1 that would return NaN. Poles pinch (all longitudes collapse) — acceptable for planets and skydomes, less so for a face, where a planar or manual layout serves better.

### Texel density: uv area vs 3D area per prim
Spot stretched or wasteful UV islands by comparing UV area to world area.
Run over: Primitives
```vex
// Shoelace uv area / world area -> spot stretched (low) or wasted (high) islands.
int vt[] = primvertices(0, @primnum);
int n = len(vt);
float uva = 0.0;
for (int i = 0; i < n; i++) {
    vector a = vertex(0, "uv", vt[i]);
    vector b = vertex(0, "uv", vt[(i + 1) % n]);
    uva += a.x * b.y - b.x * a.y;               // signed shoelace term
}
uva = abs(uva) * 0.5;
float area = primintrinsic(0, "measuredarea", @primnum);
f@uvarea = uva;
f@texel = (area > 0.0) ? sqrt(uva / area) : 0.0;   // linear texels per world unit
```
The shoelace formula sums signed cross terms of consecutive UV corners to get the 2D island area of the face; `abs(...)*0.5` makes it orientation-independent. Dividing by the world area (from the `measuredarea` intrinsic) and taking the square root converts the area ratio into a *linear* texel density, which is the number you actually want uniform across a model. Color by `f@texel` to eyeball stretching; a flipped (negative pre-abs) area also flags mirrored UVs if you keep the sign.

### Per-prim uv stretch ratio (first edge)
A quick per-face distortion readout from one UV edge vs its world edge.
Run over: Primitives
```vex
// Ratio of a uv edge length to its world edge length; 1.0 = undistorted.
int vt[] = primvertices(0, @primnum);
vector pa = point(0, "P", vertexpoint(0, vt[0]));
vector pb = point(0, "P", vertexpoint(0, vt[1]));
vector ua = vertex(0, "uv", vt[0]);
vector ub = vertex(0, "uv", vt[1]);
float world = distance(pa, pb);
float uvd   = distance(ua, ub);
f@stretch = (world > 0.0) ? uvd / world : 0.0;
if (abs(f@stretch - chf("target")) > chf("tol")) i@group_distorted = 1;
```
Comparing one UV edge's length to the same edge in 3D gives a cheap stretch factor — 1.0 (after scaling `target` to your texel budget) means the UV and the surface agree. Grouping faces that stray beyond `tol` isolates the islands a re-layout should touch. It samples a single edge for speed; average all edges of the face for a rotation-robust measure, or use the texel-density idiom above when you need true areal distortion.

### Rotate a uv island about its center by a per-island id
Randomly rotate whole islands to break up repetition, keyed on the island name.
Run over: Vertices
```vex
// Per-island rotation (island id from the owning prim name) around the uv center.
int pr = vertexprim(0, @vtxnum);
string nm = prim(0, "name", pr);
float seed = random_shash(nm);                  // stable 0..1 hash of the island name
float ang = seed * 2.0 * PI * chf("amount");
vector c = chv("center");                       // e.g. {0.5,0.5,0}
vector uv = v@uv - c;
float ca = cos(ang), sa = sin(ang);
v@uv = set(uv.x * ca - uv.y * sa, uv.x * sa + uv.y * ca, 0.0) + c;
```
`random_shash(nm)` hashes the island's name string to a stable 0..1 value, so every vertex of one island gets the identical rotation and the island stays intact. Subtracting the pivot `c`, applying the 2D rotation matrix, then adding `c` back rotates about a chosen center rather than the UV origin. Because the seed is name-based it survives re-cooking; drive `amount` down for subtle variation or to a full turn for aggressive de-tiling.

### Pack a random per-piece uv offset for variation
Shift each island by a hashed offset so a tiled texture stops looking tiled.
Run over: Vertices
```vex
// Shift each island by a hashed 0..1 offset so tiled textures de-tile per piece.
int pr = vertexprim(0, @vtxnum);
string nm = prim(0, "name", pr);
float h = random_shash(nm);                     // one stable hash per island name
vector off = set(rand(h), rand(h + 13.7), 0.0); // two decorrelated 0..1 offsets
v@uv += off * chf("jitter");
```
One name hash feeds two `rand` calls with different offsets to get a decorrelated 2D shift per island, so texture detail lands at a different spot on each piece — the classic fix for obvious repetition on scattered rocks, bricks, or foliage cards. Keeping the offset name-keyed means every vertex of a piece moves together and the result is deterministic. Pair it with a per-piece rotation (previous idiom) for maximum variety from a single texture.

### Rescale each prim's uv island to fill 0..1
Unitize a face's UVs into the unit square — handy per-tile or per-decal layouts.
Run over: Primitives
```vex
// Gather the prim's own uvs, find their bbox, remap to unit square, write back.
int vt[] = primvertices(0, @primnum);
vector mn = 1e18, mx = -1e18;
foreach (int v; vt) { vector uv = vertex(0,"uv",v); mn = min(mn,uv); mx = max(mx,uv); }
vector sz = max(mx - mn, 1e-6);
foreach (int v; vt) {
    vector uv = vertex(0, "uv", v);
    vector nu = (uv - mn) / sz;
    setvertexattrib(0, "uv", -1, v, nu);        // -1 prim = linear vertex index
}
i@unitized = 1;
```
A Primitive wrangle can touch all of a face's vertices, so two passes — find the UV bbox, then remap — normalize each island independently into 0..1. `setvertexattrib(0, "uv", -1, v, nu)` writes back by *linear* vertex index (the `-1` says "not prim-relative"), which is the correct signature when `v` came from `primvertices`. Guarding `sz` against zero avoids a divide-by-zero on degenerate islands; drop the write for any face you want left alone.

### UDIM tile number from a uv coordinate
Compute the UDIM tile each vertex falls into for multi-tile texturing.
Run over: Vertices
```vex
// 10-column UDIM convention: 1001 + floor(u) + 10*floor(v).
int tu = int(floor(v@uv.x));
int tv = int(floor(v@uv.y));
i@udim = 1001 + tu + 10 * tv;
```
UDIM numbers the tile at integer UV cell `(tu, tv)` as `1001 + tu + 10*tv`, so flooring the UV components recovers the tile a vertex lives in. This is the lookup for routing faces to per-tile textures or for validating that an island sits inside a single tile. Promote it to primitives (min/max per face) to catch islands that straddle a tile boundary, which break most texture pipelines.

### Sample a texture map in VEX to drive an attribute
Read an image in VEX and turn its value into geometry data (displacement, mask, density).
Run over: Points
```vex
// Read a map at the point uv and turn its luminance into a displacement mask.
vector uv = point(0, "uv", @ptnum);             // promote/attach a point uv first
vector c = texture(chs("map"), uv.x, uv.y);
f@lum = dot(c, {0.2126, 0.7152, 0.0722});
f@disp = f@lum * chf("amp");
```
`texture(filename, s, t)` samples an image at UV `(s, t)` and returns its color; `chs("map")` exposes the file path as a string parameter on the wrangle. The Rec-709 luminance dot turns color into a single drivable scalar for displacement, masking, or scatter density. Note this reads a *point* UV for a per-point displacement — promote vertex UVs to points first, and remember the sample is CPU texture I/O, so cache the result rather than re-sampling every cook.

### Transfer uv from a reference surface by proximity
Borrow a good UV layout from another surface by nearest-point sampling.
Run over: Points
```vex
// Nearest point on input-1 gives a prim+uv; sample its uv to steal the layout.
int pr = -1; vector p = 0;
float d = xyzdist(1, @P, pr, p);
if (pr >= 0) v@uv = primuv(1, "uv", pr, p);
```
`xyzdist(1, @P, pr, p)` locates the closest point on the reference surface (input 1) and reports its primitive and parametric coordinate; `primuv(1, "uv", pr, p)` then reads the reference UV right there. This projects a proven UV set onto a re-meshed, decimated, or simulated version of the same shape without re-unwrapping. It works best when the two surfaces are close; large gaps grab whatever face happens to be nearest, so clamp by `d` when the meshes diverge.

---

## Terrain & heightfields

Heightfields are **2D volumes**: the terrain lives in a scalar layer called `height` whose voxel *value* is the elevation, and masks live in a `mask` layer. That is the mental model that trips people up — inside a **Volume Wrangle** run over Volumes, `@P` is the voxel's world position but the ground height is `f@height`, **not** `@P.y` (which is ~0 across a flat 2D field). Slope, therefore, is the horizontal gradient of the `height` field, not a surface normal. All snippets were verified in a Volume Wrangle over a real `heightfield` + `heightfield_noise` fixture carrying `height`, `mask`, and extra `base`/`zone` layers.

> H21 gotcha: a Volume Wrangle reads and writes layers that **already exist** — it does not create a new named layer on write. Add the layer first (HeightField Layer / Copy Layer, or a HeightField Mask node) before a wrangle writes to it. Some HeightField operators also expect *native* volumes rather than VDBs; convert if a mask op silently no-ops.

### Slope mask from the height gradient (not N.y)
The correct terrain slope: magnitude of the horizontal elevation gradient.
Run over: Volumes
```vex
// A heightfield stores elevation as the voxel VALUE; slope is the horizontal
// gradient magnitude of that field, not a surface normal.
vector g = volumegradient(0, "height", @P);
float slope = length(set(g.x, 0.0, g.z));       // rise over run
f@mask = fit(slope, chf("lo"), chf("hi"), 0.0, 1.0);   // 0 flat .. 1 steep
```
`volumegradient(0, "height", @P)` returns the spatial gradient of the elevation field; dropping the vertical component leaves the horizontal rise-over-run, whose length is the true slope. This is more robust than converting to geometry and reading `@N.y`, and it stays in heightfield space where the rest of the terrain tools live. Feed `f@mask` to a HeightField Erode, a material blend, or the scatter idiom below.

### Mask an elevation band
Select a horizontal slice of terrain — snow line, shore, tree line — with soft edges.
Run over: Volumes
```vex
// Select a horizontal slice of terrain (snow line, shore band, tree line).
float h = f@height;                             // elevation, NOT @P.y
float lo = chf("low"), hi = chf("high"), feather = chf("feather");
f@mask = smooth(lo - feather, lo, h) * (1.0 - smooth(hi, hi + feather, h));
```
Reading elevation from `f@height` (never `@P.y`) is the crux; the two nested `smooth` calls build a soft-edged band that ramps up at `low` and back down at `high`. Multiplying the rising and falling smoothsteps gives a plateau of 1 between them with feathered shoulders set by `feather`. Widen the feather for gradual biome transitions, or stack two bands for a striated look.

### Terrain curvature from a Laplacian of height
Convex ridges vs concave gullies from the second difference of elevation.
Run over: Volumes
```vex
// Second difference of elevation: convex ridges >0, concave gullies <0.
float vs = chf("step");                         // ~ one voxel in world units
float hc = volumesample(0, "height", @P);
float hx = volumesample(0, "height", @P + set(vs,0,0)) + volumesample(0,"height",@P - set(vs,0,0));
float hz = volumesample(0, "height", @P + set(0,0,vs)) + volumesample(0,"height",@P - set(0,0,vs));
f@curv = (hx + hz - 4.0 * hc) / (vs * vs);
f@mask = fit(f@curv, -chf("range"), chf("range"), 0.0, 1.0);
```
Sampling the `height` field at neighbouring positions and forming `(sum of neighbours − 4·center)` is a discrete Laplacian — the second derivative of elevation. Positive values mark convex ridge lines (good for exposed-rock and snow-shedding masks), negative values mark concave channels (where debris and moisture collect). Set `step` to roughly one voxel; larger steps smooth the curvature and pick up broader landforms.

### Blend two elevation layers by a mask
Cross-fade a flat base and a detailed relief so plains and mountains coexist.
Run over: Volumes
```vex
// height = lerp(base, detail, mask): flat plain where mask=0, full relief where mask=1.
float m = fit01(noise(@P * chf("freq")), chf("mlo"), chf("mhi"));
f@height = lerp(f@base, f@height, clamp(m, 0.0, 1.0));
```
With two elevation layers present, `lerp(base, height, m)` interpolates the ground between them per voxel — here a noise mask lets mountains (the detailed `height`) rise only where `m` is high, fading to a flat `base` elsewhere. The `base` layer must already exist (create it with a Copy Layer); the wrangle only reads and writes existing layers. Swap the noise mask for a painted or slope-derived one to art-direct exactly where relief appears.

### Concavity-driven wetness/flow-accumulation proxy
A cheap wetness mask where terrain is both concave and shallow — where water would pool.
Run over: Volumes
```vex
// Water pools where terrain is concave and shallow: combine downhill gradient
// (low slope) with negative curvature into a cheap wetness mask.
vector g = volumegradient(0, "height", @P);
float slope = length(set(g.x, 0.0, g.z));
float vs = chf("step");
float lap = volumesample(0,"height",@P+set(vs,0,0)) + volumesample(0,"height",@P-set(vs,0,0))
          + volumesample(0,"height",@P+set(0,0,vs)) + volumesample(0,"height",@P-set(0,0,vs))
          - 4.0 * volumesample(0,"height",@P);
float concave = max(-lap, 0.0);
f@mask = fit(concave, 0, chf("cscale"), 0, 1) * (1.0 - fit(slope, 0, chf("smax"), 0, 1));
```
This combines two of the earlier measures: negative curvature (`-lap`, keeping only concave voxels) says "this is a hollow", and low slope says "water won't run straight off". Their product approximates flow accumulation without a true hydraulic solve — bright where basins and valley floors sit. It is a single-pass proxy, not real erosion; for genuine channels drive a HeightField Erode, but this mask is enough to seed moisture, sediment, or vegetation.

### Carve or raise height with a stamped falloff
Add a dome or crater at a world position, directly in heightfield space.
Run over: Volumes
```vex
// Add a smooth dome (or crater with negative amp) at a world position, in-place.
vector c = chv("center");
float r = max(chf("radius"), 1e-3);
float d = length(set(@P.x - c.x, 0.0, @P.z - c.z)) / r;
float fall = 1.0 - smooth(0.0, 1.0, d);         // 1 at center -> 0 at radius
f@height += chf("amp") * fall;
```
Horizontal distance from the stamp center, normalized by `radius`, feeds a smoothstep falloff that is 1 at the center and eases to 0 at the rim. Adding `amp * fall` to `f@height` raises a hill with positive `amp` or digs a crater with negative — all within native heightfield space, so downstream HeightField nodes keep working. Loop this over an array of points (from `chv` per stamp, or a second input) to place many features; combine with `max()` instead of `+=` to merge overlapping mesas cleanly.

### Scatter density from slope * altitude * noise
A layered planting mask — flat enough, right elevation, broken up by noise.
Run over: Volumes
```vex
// A layered planting mask: gentle slopes, mid elevations, broken up by noise.
vector g = volumegradient(0, "height", @P);
float slope = length(set(g.x, 0.0, g.z));
float flat = 1.0 - fit(slope, chf("smin"), chf("smax"), 0.0, 1.0);
float alt  = fit(f@height, chf("alo"), chf("ahi"), 0.0, 1.0)
           * (1.0 - fit(f@height, chf("ahi"), chf("atop"), 0.0, 1.0));
float brk  = fit01(noise(@P * chf("nfreq")), chf("nlo"), 1.0);
f@mask = clamp(flat * alt * brk, 0.0, 1.0);     // feed a HeightField Scatter density
```
Three factors multiply into one density: a flatness term (steep ground rejects trees), an altitude window (a rising then falling fit that peaks at mid elevation), and a noise term that breaks up hard edges into natural clumping. Because they multiply, a low score in any one factor vetoes placement — the AND-logic real ecosystems follow. Write it to the `mask` layer and point a HeightField Scatter's density at it; tune each fit to carve a specific biome.

### Terrace elevation into stepped plateaus
Quantize height into steps with a shaped riser for a mesa/paddy-field look.
Run over: Volumes
```vex
// Quantize height to steps, then blend risers back toward the ramp for soft edges.
float step = max(chf("step_h"), 1e-4);
float h = f@height;
float terr = floor(h / step) * step;
float frac = (h - terr) / step;                 // 0..1 up each riser
float shaped = terr + smooth(0.0, 1.0, frac) * step * chf("sharp");
f@height = lerp(h, shaped, chf("amount"));
```
`floor(h/step)*step` snaps elevation to discrete levels; keeping the fractional part `frac` and running it through a smoothstep lets you round the riser instead of leaving a razor step. `sharp` controls how hard the terrace edge is and `amount` cross-fades the whole effect back toward the original terrain, so you can dial from subtle geological banding to full rice-paddy steps. Vary `step` by region (multiply by a mask) for uneven strata.

### Classify terrain into zones by height + slope
Write an integer zone id — water, shore, upland, cliff, peak — for texturing or scatter routing.
Run over: Volumes
```vex
// Write an integer-ish zone id: water / shore / slope / cliff / peak.
vector g = volumegradient(0, "height", @P);
float slope = length(set(g.x, 0.0, g.z));
float h = f@height;
float z = 0.0;                                   // 0 = water/low
if (h > chf("shore"))                z = 1.0;    // beach / lowland
if (h > chf("shore") && slope > chf("steep")) z = 3.0;   // cliff face
else if (h > chf("upland"))          z = 2.0;    // upland
if (h > chf("peak"))                 z = 4.0;    // peak
f@zone = z;
```
Cascading `if` tests on elevation and slope bucket every voxel into a labelled zone stored in a `zone` layer (created upstream). The slope test promotes any steep-enough band to "cliff" regardless of height, which is how real rock faces cut across elevation bands. Read the zone back to drive per-zone materials, scatter sets, or color; keep the thresholds on channels so the classification stays tweakable without re-cooking noise.

### Domain-warp the terrain with noise
Push ridge lines into meandering, organic shapes by offsetting the sample position.
Run over: Volumes
```vex
// Offset the sample position by a low-frequency noise before re-sampling height
// -> ridges meander instead of running straight.
float amp = chf("warp");
vector off = (noise(@P * chf("wfreq") + set(19,7,23)) - 0.5) * 2.0 * amp;
off.y = 0.0;                                     // warp horizontally only
f@height = volumesample(0, "height", @P + off);
```
Instead of adding noise to the height, this warps *where* the height is read from: a low-frequency noise offsets the horizontal sample position, so straight ridges bend and features drift into a more natural layout. Zeroing `off.y` keeps the warp purely horizontal so elevations are not shifted vertically. Keep `wfreq` low and `warp` modest — large offsets sample far across the field and smear the terrain; layer a second finer warp for turbulence.

### Flatten terrain above a threshold into a mesa
Clamp everything above a ceiling toward a plateau, feathered into the slope.
Run over: Volumes
```vex
// Clamp anything above a ceiling toward a plateau height, feathered by a band.
float ceil = chf("ceiling");
float band = max(chf("band"), 1e-4);
float over = f@height - ceil;
float t = smooth(0.0, band, over);
f@height = lerp(f@height, ceil, t * chf("amount"));
```
`smooth(0, band, over)` ramps from 0 to 1 across a `band`-thick shoulder just above the ceiling, and the `lerp` pulls height toward the flat `ceiling` by that amount — so peaks below the ceiling are untouched and only the excess flattens. This makes buttes and mesas from noisy terrain, or levels a build site while keeping the surrounding hills. Invert the comparison (`ceil - f@height`) to fill valleys up to a waterline instead.

### Depth-to-water falloff mask from elevation
A shoreline gradient: full mask underwater, fading over the beach band.
Run over: Volumes
```vex
// A shoreline gradient: full mask below sea level, fading over a beach band.
float sea = chf("sea");
float band = max(chf("beach"), 1e-4);
f@mask = 1.0 - clamp((f@height - sea) / band, 0.0, 1.0);   // 1 underwater -> 0 inland
```
Subtracting sea level and dividing by a beach `band` gives a normalized height above water; `1 - clamp(...)` inverts it so the mask is 1 below sea level and fades to 0 by the top of the beach. Unlike a hard `height < sea` cut, the band gives a soft wet-sand transition to blend sand and grass materials or to fade foam. Feed it to a color blend or a HeightField Layer's opacity for an instant coastline.

---

## Attribute recipes

The fundamentals sheet covers *how* to bind an attribute (`@P`, `f@mask`, the type prefixes). This section is the production layer on top: moving attributes between classes, reducing them to a single value, transferring them across inputs, and the array / string / dictionary types you reach for once a scene gets real. Everything here runs in an **Attribute Wrangle**; the Run Over class is called out per idiom because it changes what `@ptnum` / `@primnum` / `@numpt` mean. A recurring rule: reading a missing attribute yields zero, and `push()` on the result of `point()` needs an explicit `float(...)` / `int(...)` cast because the untyped return is ambiguous. All snippets below were headless-cooked over a 100-point connected grid (plus a matching reference input) with zero node errors.

### Demote a point attribute to primitives by averaging
Collapse a per-point value to one value per face — the manual form of an Attribute Promote (point → prim, average).
Run over: Primitives
```vex
// Primitive: average a point attr over the prim's own points (point -> prim).
int pts[] = primpoints(0, @primnum);
float s = 0;
foreach (int p; pts) s += point(0, "heat", p);
f@heat = (len(pts) > 0) ? s / float(len(pts)) : 0.0;
```
`primpoints` returns the point numbers making up the current primitive; summing each point's `heat` and dividing by the count gives the face average. Doing it by hand (instead of an Attribute Promote node) lets you weight the average — by area, by a mask, by distance from the prim centroid — in the same pass. Swap the class to Detail and iterate all points for a point → detail promotion.

### Detail reduction: sum / min / max / mean over all points
Fold an attribute across the whole geometry into single global values you can read anywhere downstream.
Run over: Detail (once)
```vex
// Detail: fold a point attribute into single global stats in one pass.
int n = @numpt;
float s = 0, mn = 1e18, mx = -1e18;
for (int i = 0; i < n; i++) {
    float v = point(0, "heat", i);
    s += v; mn = min(mn, v); mx = max(mx, v);
}
f@heat_sum = s;
f@heat_min = (n > 0) ? mn : 0.0;
f@heat_max = (n > 0) ? mx : 0.0;
f@heat_avg = (n > 0) ? s / float(n) : 0.0;
```
A Detail wrangle runs exactly once, so a plain `for` loop over `@numpt` is the safe place to accumulate — point/prim wrangles run in parallel and cannot reduce like this. Seed `mn`/`mx` with large opposite sentinels so the first sample wins, and guard the divide when the geometry might be empty. Detail attributes written here are single shared values every later point wrangle can read with `detail(0, "heat_avg", 0)`.

### Proximity transfer from a second input with a falloff
Pull an attribute off nearby geometry (input 1) and blend it in by distance — a hand-built Attribute Transfer.
Run over: Points
```vex
// Point: pull Cd from the nearest reference point (input 1), weighted by distance.
int pt = nearpoint(1, @P, chf("maxdist"));
if (pt >= 0) {
    float w = 1.0 - smooth(0.0, chf("maxdist"), distance(@P, point(1, "P", pt)));
    @Cd = lerp(@Cd, point(1, "Cd", pt), w);
}
```
`nearpoint(1, @P, maxdist)` returns the closest point in input 1 within the radius, or `-1` if nothing is in range — always test that before dereferencing. `smooth` turns raw distance into a 0..1 falloff so far matches barely tint and near matches fully replace, and `lerp` applies it. Doing this in VEX (rather than the Attribute Transfer SOP) lets you shape the falloff curve and choose exactly which attributes ride along.

### Build, store and reduce an array attribute
Gather a variable-length set of values per element into an `f[]@` / `i[]@` array attribute, then fold it.
Run over: Points
```vex
// Point: gather neighbour heats into a float[] attribute, then reduce it.
float hs[];
foreach (int p; neighbours(0, @ptnum)) push(hs, float(point(0, "heat", p)));
f[]@heats = hs;                        // store the whole array on the point
float mx = -1e18;
foreach (float v; hs) mx = max(mx, v);
f@hmax = (len(hs) > 0) ? mx : 0.0;
i@valence = len(hs);
```
A local `float hs[]` grows with `push()`; binding it to `f[]@heats` stores a genuine array attribute (each point can hold a different length). Note the `float(point(...))` cast — `push()` cannot resolve the untyped `point()` return on its own and errors as ambiguous otherwise. `len()` reads the count back (here a valence), and a `foreach` reduces the array; arrays are how you carry per-element neighbour lists, capture indices, or multi-sample data forward.

### String attributes: sprintf, split, join, glob match
Author and parse string attributes — per-piece names, indexed labels, and tests against a pattern.
Run over: Points
```vex
// Point: name a piece, then parse the name back into fields.
s@label = sprintf("chunk_%03d_row%d", @ptnum, int(floor(@P.y)));
string parts[] = split(s@label, "_");
s@prefix = parts[0];
s@rejoin = join(parts, "|");
i@is_chunk = match("chunk_*", s@label);   // 1 if the glob matches
```
`sprintf` builds a formatted string (`%03d` zero-pads to width 3) — the workhorse for stable per-piece names that survive caching. `split` breaks a string into a `string[]` on a delimiter and `join` rebuilds it with a new one, so you can re-key names between conventions. `match` runs Houdini's glob syntax (`*`, `?`, `[..]`) and returns 1/0 — handy for grouping `piece_*` or filtering by a name prefix.

### Hand-rolled attribute blur (one Laplacian smoothing pass)
Relax a scalar toward its connected-neighbour average — a smoothing pass with no extra node.
Run over: Points
```vex
// Point: blend each value toward its connected-neighbour average.
int nb[] = neighbours(0, @ptnum);
if (len(nb) > 0) {
    float s = 0;
    foreach (int p; nb) s += point(0, "heat", p);
    f@heat = lerp(f@heat, s / float(len(nb)), chf("blur"));
}
```
`neighbours(0, @ptnum)` returns the point numbers directly connected by an edge; averaging their values and lerping toward it by `blur` (0..1) is one Laplacian smoothing step. Because point wrangles run in parallel, each point reads the *incoming* values — so one wrangle is one iteration; chain several (or wrap in a For-Each / Solver) for a stronger blur. This is the core move behind relaxing masks, velocities, or captured weights.

### Spatial gradient of a point attribute from its neighbours
Estimate the direction and rate a scalar changes across the surface, without a volume.
Run over: Points
```vex
// Point: least-squares-ish finite-difference gradient of `heat`.
vector g = 0;
foreach (int p; neighbours(0, @ptnum)) {
    vector d = point(0, "P", p) - @P;
    float dv = point(0, "heat", p) - f@heat;
    float l2 = dot(d, d);
    if (l2 > 1e-9) g += d * (dv / l2);
}
v@heat_grad = g;
```
Each neighbour contributes the value difference `dv` projected along the direction to it, weighted by `1/|d|^2` so nearer neighbours dominate — an inexpensive finite-difference gradient over an irregular mesh. Guarding `l2 > 1e-9` skips coincident points that would divide by zero. The resulting `v@heat_grad` points uphill in `heat` and its length is the local slope — use it to drive flow, orient copies, or seed erosion.

### Copy an attribute from another input and remap its range
Bring a value in from a reference input and refit it into a usable range or palette.
Run over: Points
```vex
// Point: read `temp` from input 1 by point number, fit to 0..1, ramp to a color.
float src = point(1, "temp", @ptnum);
f@t01 = fit(src, chf("inlo"), chf("inhi"), 0.0, 1.0);
@Cd = chramp("grade", f@t01);
```
`point(1, "temp", @ptnum)` reads by matching point number, which is exact when inputs share topology (see the `@id` idiom below when they do not). `fit` remaps the raw range you specify into 0..1, and `chramp` turns that into an art-directable color or falloff via a ramp parameter on the node. This "copy then remap" is the everyday way to normalize incoming data before it drives anything.

### Read an attribute only if it exists, else a typed default
Guard a read so a missing attribute falls back to a sensible default instead of silently reading zero.
Run over: Points
```vex
// Point: guard a read so a missing attribute falls back cleanly.
float m = haspointattrib(0, "mask") ? point(0, "mask", @ptnum) : chf("default_mask");
f@used_mask = m;
```
`haspointattrib(0, "mask")` returns 1/0 for whether the attribute is actually present on input 0 — the difference between "explicitly zero" and "never authored", which a bare `f@mask` read cannot tell you. The ternary supplies a channel-driven default when it is absent, so a wrangle behaves predictably whether or not an upstream node painted the mask. Parallel functions exist for the other classes (`hasprimattrib`, `hasvertexattrib`, `hasdetailattrib`).

### Copy across a topology change by stable @id (idtopoint)
Match elements between two geometries by an id attribute, immune to reordering or point-count changes.
Run over: Points
```vex
// Point: find the input-1 element whose @id matches mine, regardless of order.
int src = idtopoint(1, i@id);
if (src >= 0) @Cd = point(1, "Cd", src);
```
`idtopoint(1, id)` looks up the point in input 1 whose `id` attribute equals the argument and returns its point number (or `-1`). This is the correct transfer when a Sort, Fuse, fracture, or simulation has scrambled point numbers — `point(1, "Cd", @ptnum)` would grab the wrong element, but `@id` matching stays stable. `idtoprim` does the same for primitives; both require an `id` attribute to exist on the target input.

### Cast/convert types safely (int <-> float <-> vector)
Move a value cleanly between int, float and vector so a mismatched bind never truncates or errors.
Run over: Points
```vex
// Point: rounded float->int, int->float, pack scalars into a vector.
i@heat_i = int(rint(f@heat * 100.0));
f@id_f   = float(i@id);
v@packed = set(f@heat, 0.0, float(i@id));
```
`int(x)` truncates toward zero, so `rint()` first rounds to nearest when that is what you want (here turning a 0..1 heat into a 0..100 bucket). `float(i@id)` promotes an int for arithmetic that must stay fractional, and `set(a, b, c)` packs three scalars into a vector. Being explicit avoids the classic bug where an unprefixed `@x = 0.5` binds an int attribute and silently stores 0.

### Dictionary attribute: store and read back key/value metadata
Carry mixed-type, named metadata per element in a single `d@` dictionary attribute.
Run over: Points
```vex
// Point: a dict attribute holds mixed-type per-element metadata.
dict d = {};
d["heat"] = f@heat;
d["tag"]  = sprintf("p%d", @ptnum);
d@meta = d;
f@heat_copy = float(d@meta["heat"]);
```
A `dict` holds arbitrary string keys mapping to mixed value types (float, string, vector) — useful for per-piece bookkeeping that would otherwise need a dozen separate attributes. Assigning to `d@meta` stores it on the element; indexing `d@meta["heat"]` reads a value back, cast to the type you expect. Reading a missing key returns an empty/zero value, so guard or default when the schema is uncertain.

### Component access and swizzle on vector attributes
Read and write individual channels of a vector — including the color aliases — without rebuilding the whole vector.
Run over: Points
```vex
// Point: read/write individual components (.x/.y/.z, colour aliases .r/.g/.b).
@Cd = set(0, 0, 0);
@Cd.r = fit(@P.x, -5, 5, 0, 1);
@Cd.g = f@heat;
f@height = @P.y;
```
`.x/.y/.z` and the aliases `.r/.g/.b` (and `.a` on a vector4) address one channel of a vector for both reading and writing. Writing a single component leaves the others untouched, which is cleaner than `set(@Cd.r, newg, @Cd.b)`. `@P.y` reading the height is the same mechanism — component access is how most masks and per-axis logic get built.

### Tag an attribute's transform behaviour (typeinfo)
Declare how an attribute should respond to transforms so downstream Transform/Xform nodes treat it correctly.
Run over: Detail (once)
```vex
// Detail: mark a vector as non-transforming so xforms don't rotate it.
setattribtypeinfo(0, "point", "N", "vector");          // rotates with the geo
setattribtypeinfo(0, "point", "Cd", "nonarithmetic");  // never transformed
i@tagged = 1;
```
An attribute's *type info* tells Houdini whether to rotate/scale it when the geometry is transformed: `"point"` positions get fully transformed, `"vector"` and `"normal"` rotate, `"nonarithmetic"` (ids, colors, uvs treated as data) are left alone. `setattribtypeinfo(0, class, name, kind)` sets it — do it in a Detail wrangle since it is a per-attribute declaration, not per-element. Getting this wrong is why a custom `v@` direction sometimes fails to rotate with the object, or an `@id` vector gets scrambled by a Transform.

---

## Advanced groups & selection

The fundamentals sheet shows `i@group_x = expr;` and the `inpointgroup` test. This section is the working-TD layer: detecting mesh boundaries, growing and shrinking membership, selecting by measurement or connectivity, spatial and deterministic-random selection, and combining groups with boolean logic. Two mechanics recur: `i@group_name = <bool>` sets membership inline (fast, per element), while `setpointgroup(0, "name", ptnum, 1, "set")` sets it for *any* element — the form you need inside a Detail wrangle that decides membership for the whole geometry at once. All snippets were cooked over a connected grid carrying a `@class`, a measured `area`, a named `seed` group, and an SDF second input.

### Group boundary points via unshared (open) edges
Find the open border of a mesh — the edges that belong to only one face.
Run over: Points
```vex
// Point: a point is on a border if it owns any edge shared by < 2 faces.
int h0 = pointhedge(0, @ptnum);
int h = h0, bnd = 0;
while (h >= 0) {
    if (hedge_equivcount(0, h) < 2) { bnd = 1; break; }
    h = pointhedgenext(0, h);
    if (h == h0) break;
}
i@group_boundary = bnd;
```
Half-edges are the robust way to reason about connectivity: `pointhedge` gives a half-edge leaving this point, and `pointhedgenext` rotates through the others around it. `hedge_equivcount` counts how many half-edges share that edge — an interior edge on a manifold mesh has 2, a boundary edge has 1, so `< 2` flags the border. This is the general boundary test (open holes, mesh perimeter, crack edges) and beats guessing from `neighbourcount`, which fails on non-uniform meshes.

### Group by a measured / thresholded attribute
Select elements whose measured quantity (area, curvature, speed) crosses a threshold.
Run over: Primitives
```vex
// Primitive: membership from a measured quantity (here prim area) vs a threshold.
i@group_big = (f@area > chf("min_area"));
```
This is the canonical `i@group_ = <bool>` pattern applied to a *measured* attribute — here prim `area` from an upstream Measure SOP (or computed in VEX). Any comparison works: `> min`, a band `x > lo && x < hi`, or a sign test. Keeping the threshold on a `chf` channel means you dial the selection with a slider and see it update live, instead of re-editing code.

### Grow a group one ring outward through connected neighbours
Expand a selection by one edge-ring — the VEX form of Group Expand.
Run over: Points
```vex
// Point: add non-members that touch a member (chain wrangles for N rings).
int inside = inpointgroup(0, "seed", @ptnum);
if (!inside)
    foreach (int p; neighbours(0, @ptnum))
        if (inpointgroup(0, "seed", p)) { inside = 1; break; }
i@group_grown = inside;
```
A non-member joins if any edge-connected neighbour is already in `seed`, which dilates the group by exactly one ring per wrangle. Because it reads the incoming membership (parallel execution), you chain N wrangles — or wrap it in a For-Each Loop with N iterations — to grow N rings. Flip the logic (a member with a non-member neighbour drops out) to erode instead; both are shown here as a pair.

### Shrink (erode) a group: drop members touching a non-member
Peel the outer ring off a selection — the inverse of grow, for cleaning noisy masks.
Run over: Points
```vex
// Point: keep a member only if all its neighbours are also members.
if (inpointgroup(0, "seed", @ptnum)) {
    int keep = 1;
    foreach (int p; neighbours(0, @ptnum))
        if (!inpointgroup(0, "seed", p)) { keep = 0; break; }
    i@group_eroded = keep;
}
```
A member survives only if *every* neighbour is also a member, so any point on the group's boundary falls away — one erosion step. Pairing a few erode passes with the same number of grow passes is an open/close morphological filter that removes speckle and thin bridges from a selection. Note the write is inside the `if`, so non-members are simply never added to `eroded`.

### Group the largest connectivity class (@class clumping)
Keep only the biggest connected island of a mesh — isolate the main body, drop debris.
Run over: Detail (once)
```vex
// Detail: tally points per @class, then group the most-populous component.
int n = @numpt, counts[];
for (int i = 0; i < n; i++) {
    int c = point(0, "class", i);
    while (len(counts) <= c) push(counts, 0);
    counts[c] += 1;
}
int best = 0, bestn = -1;
foreach (int c; int cnt; counts) if (cnt > bestn) { bestn = cnt; best = c; }
for (int i = 0; i < n; i++)
    if (point(0, "class", i) == best) setpointgroup(0, "biggest", i, 1, "set");
```
Feed this a `@class` attribute from a Connectivity SOP (one integer per connected component). The first loop builds a histogram of points per class (growing the `counts` array as new class ids appear), the middle finds the most-populous class, and the last groups its points via `setpointgroup` — the Detail-wrangle way to decide membership for arbitrary elements. Swap "largest" for "smallest" or "classes over N points" to filter islands by size.

### Spatial group: members inside an axis-aligned box
Select everything inside a world-space box — the building block for radius and region selection.
Run over: Points
```vex
// Point: box test on @P (swap for radius or SDF sign, below).
vector mn = chv("bmin"), mx = chv("bmax");
i@group_inbox = (@P.x > mn.x && @P.y > mn.y && @P.z > mn.z &&
                 @P.x < mx.x && @P.y < mx.y && @P.z < mx.z);
```
A point is inside the box when all three components fall between the min and max corners — six comparisons, componentwise (VEX does not overload `<` for whole vectors, so spell them out). Swap the test for `length(@P - center) < r` to get a sphere, or sample an SDF (next idiom) for an arbitrary region. Driving the corners from `chv` channels lets you box-select interactively.

### Spatial group by SDF sign from a volume input
Select points inside an arbitrary solid using a signed-distance field in another input.
Run over: Points
```vex
// Point: inside a level set (surface < 0) sampled from input 1.
float d = volumesample(1, "surface", @P);
i@group_inside = (d < chf("iso"));
```
`volumesample(1, "surface", @P)` reads the SDF value at each point's position; by convention negative is inside the solid, positive outside, zero on the surface. Comparing to an `iso` channel (default 0) selects the interior — and a small positive or negative iso offsets the selection outward or inward like a shrink/grow with no topology work. This turns any shape (a VDB from geometry, an imported level set) into a selection volume.

### Deterministic random subset keyed on @id
Pick a stable pseudo-random fraction of elements that survives reordering and re-simulation.
Run over: Points
```vex
// Point: a stable ~frac selection that survives point reordering (seeded by @id).
i@group_pick = (rand(i@id * 2654435761) < chf("frac"));
```
Seeding `rand` with `@id` (not `@ptnum`) makes the selection reproducible even after a Sort, fracture, or sim renumbers points — the same ids always get picked. Multiplying by a large odd constant decorrelates neighbouring ids so the pattern looks random rather than striped. `frac` is the approximate fraction selected (0.25 ≈ a quarter); it is the go-to for thinning, per-instance variation, or seeding a subset of emitters.

### Select the top fraction by an attribute (single detail pass)
Grab the highest N% of elements by some value — e.g. the hottest, fastest, or largest.
Run over: Detail (once)
```vex
// Detail: sort all values, find the cutoff for the top `frac`, group above it.
int n = @numpt;
float vals[];
for (int i = 0; i < n; i++) push(vals, float(point(0, "heat", i)));
vals = sort(vals);
int k = clamp(int(floor((1.0 - chf("frac")) * float(n))), 0, max(n - 1, 0));
float cutoff = (n > 0) ? vals[k] : 0.0;
for (int i = 0; i < n; i++)
    if (point(0, "heat", i) >= cutoff) setpointgroup(0, "hottest", i, 1, "set");
```
Selecting the top percentile needs a global view, so it runs once in a Detail wrangle: collect every value, `sort()` ascending, then index the cutoff at `(1 - frac) * n` from the bottom. Any element at or above that cutoff joins the group via `setpointgroup`. Because it is threshold-based on the real distribution, it adapts frame to frame — the top 10% of speed stays "the top 10%" even as the sim's speeds change. (The `float(point(...))` cast is required for `push`.)

### Per-prim test of point-group membership (any / all)
Ask, per face, whether it touches a point group at all or lies entirely within it.
Run over: Primitives
```vex
// Primitive: does this face touch the "seed" point group, partly or wholly?
int pts[] = primpoints(0, @primnum), hits = 0;
foreach (int p; pts) hits += inpointgroup(0, "seed", p);
i@group_touch = (hits > 0);
i@group_full  = (hits == len(pts));
```
Counting how many of a primitive's points are in the `seed` point group lets you build two derived prim groups: `touch` (any point in — the boundary faces) and `full` (all points in — the interior faces). This point→prim group promotion is exactly what you need to blast, extrude, or material-assign whole faces based on a point selection. The same pattern with `>= len(pts) - 1` gives "almost fully inside" for softer edges.

### Combine groups with boolean logic in one wrangle
Derive union, intersection and difference groups from two source groups in a single pass.
Run over: Points
```vex
// Point: derive union / intersection / difference from two source groups.
int a = inpointgroup(0, "seed", @ptnum);
int b = (@P.x > chf("cut"));         // an on-the-fly group
i@group_either = a || b;
i@group_both   = a && b;
i@group_only_a = a && !b;
```
Once membership is just an int, set algebra is boolean algebra: `||` is union, `&&` is intersection, `a && !b` is difference, `!a` is invert. One of the operands can be a live condition (`@P.x > cut`) so you combine a stored group with an on-the-fly test without a second node. This replaces a chain of Group Combine SOPs and keeps the logic readable in one place.

---

## Volumes & VDB

A **Volume Wrangle** runs its snippet once per voxel, with `@P` set to that voxel's world-space center; it reads and writes fields by name (`f@density`, `v@vel`) exactly like a point wrangle reads attributes. The same VEX addresses both native Houdini volumes and VDBs — you sample any field by name and world position regardless of which primitive type or transform it lives on, which is why one wrangle works across a mixed volume input. Writes land in an *existing* field of that name at the current voxel, so the target volume must be present in the input (merge one in if you need a fresh output field). The `volumesample*` / `volumegradient` family is the read side; SDF sign and gradient are the two facts you lean on most. All snippets were cooked over a set of identical-layout native volumes (density, temperature, velocity, two analytic sphere SDFs, and writable targets), plus point-side sampling wrangles, with zero node errors.

### Sample a named scalar field at a position
Read any scalar field's value at an arbitrary point — the fundamental volume read.
Run over: Volumes
```vex
// Volume: read any field by name at this voxel centre (@P).
f@shaped = volumesample(0, "density", @P);
```
`volumesample(input, name, pos)` does a trilinearly-interpolated lookup of the named field at a world position — here the current voxel center, but it can be any position you compute. It works whether `density` is a native volume or a VDB, and returns 0 outside the field's active region. This one call underlies advection, masking, and cross-field logic; everything else in this section builds on it.

### Sample a vector field (volumesamplev)
Read a vector field — velocity, a gradient cache, a color volume — at a position.
Run over: Volumes
```vex
// Volume: vector fields come back with volumesamplev.
v@grad = volumesamplev(0, "vel", @P);
```
`volumesamplev` is the vector counterpart to `volumesample`, returning a `vector` for fields like `vel`. A native vector volume is stored as three scalar volumes (`vel.x/.y/.z`) but you address it by the base name and get the assembled vector back. Reach for it whenever you need to follow or react to a velocity/direction field inside a wrangle.

### Volume gradient -> direction toward the surface
Get the direction a field increases fastest — for an SDF, the way out of (or into) the surface.
Run over: Volumes
```vex
// Volume: the SDF gradient points outward; negate it to aim at the surface.
vector g = volumegradient(0, "surface", @P);
v@grad = -normalize(g);
```
`volumegradient` returns the spatial derivative of a scalar field (which way, and how steeply, it climbs) computed from neighbouring voxels. For a signed-distance field the gradient points *away* from the surface (toward increasing distance), so negating it gives the direction to the nearest surface — the basis for pushing points onto a collider or projecting to a level set. The raw gradient length encodes the rate of change; normalize when you only want direction.

### SDF sign test -> inside/outside mask
Turn a level set into a binary interior mask for culling, emission, or selection.
Run over: Volumes
```vex
// Volume: 1 inside the level set, 0 outside (drives culling / emission masks).
f@mask = (volumesample(0, "surface", @P) < chf("iso")) ? 1.0 : 0.0;
```
The defining property of an SDF is its sign: negative inside the solid, positive outside, zero on the surface. Testing `< iso` (default 0) writes a 1/0 interior mask, and a nonzero `iso` grows or shrinks the region like a cheap dilate/erode. Masks like this gate emission, delete exterior voxels, or become the density source for a shape.

### Surface normal from a normalized SDF gradient
Recover a smooth surface normal at any point from a level set — no polygons needed.
Run over: Volumes
```vex
// Volume: a level set's normalized gradient IS its surface normal.
v@grad = normalize(volumegradient(0, "surface", @P));
```
For a proper signed-distance field the gradient has unit length and points along the surface normal, so normalizing `volumegradient` gives the outward normal at that voxel — valid throughout the field, not just on the zero crossing. This is how you shade, bevel, or scatter-orient against a volumetric surface, and how collision responses know which way to push. If the field is not a clean SDF (a fog volume), the gradient still points up-density but is not a true normal.

### Shape density: remap + add volumetric noise detail
Contrast-shape a density field and break up its smoothness with position-space noise.
Run over: Volumes
```vex
// Volume: contrast the density then break it up with position-space noise.
float d = fit(f@density, chf("lo"), chf("hi"), 0.0, 1.0);
d *= 1.0 + noise(@P * chf("freq")) * chf("detail");
f@shaped = clamp(d, 0.0, 1.0);
```
`fit` stretches a chosen input band to 0..1, sharpening or softening the smoke's edge before you add detail. Multiplying by `1 + noise*detail` modulates density with world-space noise — because `noise` is sampled on `@P`, the pattern is locked to space and stays coherent as the field advects through it. Clamp at the end so shaping never pushes density negative or blows it past 1.

### Level-set booleans: union / intersect / subtract
CSG on shapes represented as SDFs — combine two solids with a single min/max.
Run over: Volumes
```vex
// Volume: SDF CSG - union=min, intersect=max, subtract=max(a,-b).
float a = volumesample(0, "surface", @P);
float b = volumesample(0, "surfaceB", @P);
f@out = min(a, b);   // union; swap the op for the other booleans
```
Because an SDF stores distance-to-surface, boolean geometry becomes arithmetic on those distances: `min(a,b)` keeps whichever surface is nearer (union of the solids), `max(a,b)` keeps the farther (intersection), and `max(a,-b)` subtracts B from A by flipping B's inside/outside. It is exact, resolution-independent, and free of the mesh-boolean fragility — the reason destruction and modeling pipelines carry shapes as level sets. The two input fields should share a transform (or be sampled by world position, as here) for a clean result.

### Sample volume fields onto points (volume -> point)
Read volumetric data onto geometry — bring density, velocity, or a mask out of a volume and onto points.
Run over: Points
```vex
// Point: read scalar + vector fields from a volume in input 1.
f@d  = volumesample(1, "density", @P);
v@vv = volumesamplev(1, "vel", @P);
```
The same sampling functions work in an ordinary Attribute Wrangle over points, reading the volume wired into input 1 — the standard way to drive scattered points, instances, or particles from a field. Each point looks up the field at its own `@P`; points outside the field's active region read 0. This is one half of the volume↔geometry bridge (the other half, below, writes points into a volume).

### Rasterize a point attribute into a volume (nearest point)
Bake a point attribute into a field by pulling each voxel from its nearest source point.
Run over: Volumes
```vex
// Volume: pull the nearest source point's attribute into each voxel (input 1).
int pt = nearpoint(1, @P);
f@mask = (pt >= 0) ? point(1, "charge", pt) : 0.0;
```
Running over voxels, `nearpoint(1, @P)` finds the closest source point (input 1) to each voxel center, and `point(1, "charge", pt)` copies its attribute in — a nearest-point rasterization straight into the field. It is coarser than a proper Volume Rasterize (no splatting or falloff) but trivially controllable, and ideal for stamping a per-point id, temperature, or mask into a volume the solver reads. Add a distance limit or blend several neighbours for smoother results.

### Voxel index <-> world position round-trip
Convert between a voxel's integer index and its world position — for addressing, banding, or neighbour math.
Run over: Volumes
```vex
// Volume: map @P to integer voxel index and back (banding / addressing).
vector idx = volumepostoindex(0, "density", @P);
vector w   = volumeindextopos(0, "density", idx);
f@out = idx.x;                 // e.g. stripe by the i index
```
`volumepostoindex` converts a world position into the field's (i, j, k) voxel index space, and `volumeindextopos` maps back — the two let you reason about a volume in integer grid coordinates regardless of its transform. Use the index for procedural banding, checkerboards, tiling, or to derive the positions of specific neighbour voxels. Rounding the index gives the containing voxel; the fractional part is the interpolation weight the samplers use internally.

### Reshape a level set: offset + emboss the surface
Grow/shrink a solid and carve relief into its surface by editing SDF distances directly.
Run over: Volumes
```vex
// Volume: positive offset erodes the solid; noise embosses relief onto it.
float s = volumesample(0, "surface", @P);
s += chf("offset");
s += noise(@P * chf("freq")) * chf("emboss");
f@shaped = s;
```
Adding a constant to an SDF moves the zero-crossing uniformly — a positive offset pushes the surface inward (erodes the solid), negative dilates it, giving a fast uniform peel/thicken. Adding position-space noise displaces the surface by the noise amount, embossing bumps and ridges without touching geometry. Keep `emboss` small relative to voxel size or the field stops being a valid distance function and normals get noisy; a VDB Renormalize afterward repairs it if you push hard.

### Semi-Lagrangian advection back-step setup
The core move of fluid advection — trace a voxel back along velocity and resample the field there.
Run over: Volumes
```vex
// Volume: trace back along velocity a step and resample density there.
vector vel  = volumesamplev(0, "vel", @P);
vector back = @P - vel * chf("dt");
f@shaped = volumesample(0, "density", back);
```
Advection asks "what value arrives here this step?"; the semi-Lagrangian answer is to walk backward along the velocity by one timestep and sample the field at that upstream position. `@P - vel*dt` is that back-traced point, and `volumesample` fetches the density there — unconditionally stable regardless of `dt`, which is why solvers use it. This is a teaching stand-in for the built-in advection; in practice you would sub-step or use higher-order back-tracing to cut smearing.

### Build an activation mask for a VDB Activate node
Mark the voxels worth simulating so a VDB Activate/dilate can grow the active region efficiently.
Run over: Volumes
```vex
// Volume: 1 where there is meaningful density -> feed a VDB Activate / dilate.
f@mask = (f@density > chf("thresh")) ? 1.0 : 0.0;
```
VDBs only store and compute where voxels are *active*, so keeping that region tight is what makes them fast. Writing a 1/0 mask wherever density is meaningful gives a downstream VDB Activate node the region to turn on (then dilate a few voxels for headroom ahead of motion). Thresholding is the simplest activation heuristic; gate on speed, temperature, or an SDF band instead when that better predicts where the sim needs room.

### Smoother C1 field read (cubic reconstruction)
Sample a field with cubic interpolation to avoid the faceted look of trilinear reads.
Run over: Volumes
```vex
// Volume: cubic sampling reduces trilinear voxel-stair on smooth fields.
f@shaped = volumecubicsample(0, "density", @P);
```
`volumesample` uses trilinear interpolation, which is fast but leaves visible voxel-grid creasing on smooth fields and low-resolution gradients. `volumecubicsample` reconstructs with a cubic kernel for a C1-continuous result — smoother values and smoother derivatives — at extra cost per lookup. Use it when the field feeds displacement, lighting, or anything where the trilinear stair-stepping would show; stick with the plain sampler in the hot path of a sim.

---

## Scene prep, utility & debug

The glue idioms: making an invisible field visible, stamping bookkeeping a downstream node or cache can key on, and catching bad data before it propagates. These run in a plain **Attribute Wrangle** (Points for per-element work, Detail for reductions and running counts) — no sim, no special context. The recurring move is to author a throwaway `@Cd`, a `s@name`, or a detail statistic purely so a human (or the next tool) can read the geometry at a glance. All snippets below were verified in an Attribute Wrangle over a scattered, normal-carrying grid fixture.

### Debug-color any scalar field through a ramp
Turn a hidden float attribute into viewport color so you can see its distribution at a glance.
Run over: Points
```vex
// Map any scalar field to a color ramp so you can eyeball its distribution.
float raw = f@mask;                       // the field you want to inspect
float t = fit(raw, chf("lo"), chf("hi"), 0.0, 1.0);
@Cd = chramp("debug", t);
```
`fit` normalizes the raw field into 0..1 against a low/high you set on the node, and `chramp` maps that through an editable ramp — so you can push contrast or recolor without re-pasting VEX. Point `lo`/`hi` at the field's actual range (use the min/max reduction below to find it) or the whole thing washes out to one color. Swap `f@mask` for any scalar — curvature, density, age, `@ptnum` — and you have a universal field inspector.

### View a vector attribute as color
The standard normal-as-color trick — encode a signed direction as RGB to sanity-check orientation.
Run over: Points
```vex
// Pack a signed unit vector into 0..1 RGB - the standard normal-as-color view.
vector n = normalize(@N);
@Cd = n * 0.5 + 0.5;                       // -1..1 -> 0..1 per component
```
A unit vector's components live in -1..1, but color channels clamp at 0..1, so `n * 0.5 + 0.5` remaps each component into the visible range: +X reads red-ish, +Y green-ish, +Z blue-ish. This instantly reveals flipped or zero normals (a black patch means a degenerate `@N`), and it works for any direction attribute — `@v`, a tangent, a gradient. Skip the `normalize` if you specifically want magnitude to darken the color.

### Grow debug polylines along a vector attribute
Draw a hair from each point so you can see a vector's direction *and* length, not just its color.
Run over: Points
```vex
// Draw a short line from each point along a vector so you can see direction + magnitude.
vector tip = @P + v@v * chf("scale");
int p2 = addpoint(0, tip);
addprim(0, "polyline", @ptnum, p2);
```
`addpoint` creates a tip offset along the vector, and `addprim` with `"polyline"` stitches the source point to that tip into a two-point line. The `scale` channel lets you exaggerate small vectors to visibility. Adding topology from a parallel point wrangle is safe — Houdini serializes the inserts, and the freshly-added tip points are not themselves iterated — but keep it as a *separate* visualization branch so you don't carry the debug lines into the real geometry stream.

### Stamp a readable label into a string attribute
Write a formatted per-element string so the geometry spreadsheet reads like a report.
Run over: Points
```vex
// Human-readable per-element label for the geometry spreadsheet.
s@info = sprintf("pt %d  h=%.2f  spd=%.3f", @ptnum, @P.y, length(v@v));
```
`sprintf` builds one string per element with `%d` for the index and `%.2f`/`%.3f` for fixed-precision floats, so a wall of raw columns collapses into one scannable line. This is the fastest way to correlate several attributes on the same row while debugging. Strings are heavier than numeric attributes, so treat `s@info` as a temporary inspection aid and delete it before caching or exporting.

### Running per-class index in a detail wrangle
Give each element a 0,1,2… index *within* its connectivity class or group — the serial counter a parallel wrangle can't do.
Run over: Detail
```vex
// Assign a per-class running index (0,1,2..) within each connectivity/class bucket.
int counts[];                              // grows on write; reads past end = 0
int n = npoints(0);
for (int i = 0; i < n; i++) {
    int c = point(0, "class", i);
    int idx = counts[c];
    setpointattrib(0, "classidx", i, idx, "set");
    counts[c] = idx + 1;
}
```
Counting "how many came before me in my group" is inherently order-dependent, so it must run in a **Detail** wrangle (one serial pass), never a per-point wrangle (parallel, no shared state). The `counts` array is used as a sparse tally keyed by class id — reading an unwritten slot returns 0, and writing past the end auto-grows the array — so each class gets its own independent running index. Reach for this to number pieces per cluster, rings per curve, or copies per source point.

### Reorder-stable id + name from a quantized position
Build an id that survives point reordering (and re-fracture) by hashing a snapped rest position.
Run over: Points
```vex
// Hash a snapped rest position into an id that survives point reordering; pair a name.
vector q = rint(@P * chf("quant"));        // snap to a lattice
i@id = int(random(q) * 2147483000.0);
s@name = sprintf("id_%d", i@id);
```
`@ptnum` is unstable — a Sort, a Fuse, or a sim reshuffle renumbers everything — so keying downstream matching or caching on it silently breaks. Snapping position to a lattice with `rint(@P * quant)` and hashing that with `random` yields an id tied to *where* a point is, not its index, so it stays put as long as the point doesn't move much. Raise `quant` for a finer lattice (more unique ids, less tolerance to motion); pair the id with a formatted `s@name` for string-based lookups.

### Flag out-of-range values into a group + warn
An assert for geometry: catch values outside an expected band, group the offenders, and log the first ones.
Run over: Points
```vex
// Assert a field stays in an expected band; group offenders and log the first ones.
float v = f@mask;
if (v < chf("lo") || v > chf("hi")) {
    i@group_outofrange = 1;
    warning("pt %d mask=%g out of [%g,%g]", @ptnum, v, chf("lo"), chf("hi"));
}
```
The `outofrange` group makes every offender selectable in the viewport, while `warning` prints a diagnostic to the node's message area without failing the cook — a safe, read-only inspection builtin (not to be confused with error, which stops the graph). Use it as a data tripwire between pipeline stages: if a mask should be 0..1 or a scale should be positive, flag the violations instead of letting a bad value silently poison a sim. Swap `warning` for `error` only when you genuinely want to halt the network.

### Solo one element for inspection
Isolate a single point by index so you can study it without the rest of the geometry in the way.
Run over: Points
```vex
// Group + highlight just the point index on the slider so you can study it alone.
if (@ptnum == chi("inspect")) {
    i@group_pick = 1;
    @Cd = {1, 1, 0};
}
```
Comparing `@ptnum` to an integer channel `chi("inspect")` lets you scrub a slider to walk one element at a time; the `pick` group drives a Blast or a viewport selection, and the yellow `@Cd` marks it. This is the manual counterpart to the geometry spreadsheet's row highlight — handy when you need to see *where* point 4021 actually sits. For prims or vertices, run over that class and compare `@primnum`/`@vtxnum` instead.

### One-pass min/max/avg reduction to detail attribs
Compute the range and mean of an attribute in a single serial pass and park them on detail attributes.
Run over: Detail
```vex
// Reduce a point attribute to detail min/max/mean in a single serial pass.
int n = npoints(0);
float mn = 1e18, mx = -1e18, sum = 0.0;
for (int i = 0; i < n; i++) {
    float v = point(0, "mask", i);
    mn = min(mn, v); mx = max(mx, v); sum += v;
}
f@mask_min = mn;
f@mask_max = mx;
f@mask_avg = (n > 0) ? sum / float(n) : 0.0;
```
A **Detail** wrangle runs exactly once, which is what a reduction needs — the loop walks every point with `point(0, "mask", i)`, tracking running min/max and a sum for the mean. Seeding `mn`/`mx` with large opposite sentinels guarantees the first real value wins the comparison, and the `n > 0` guard avoids a divide-by-zero on empty input. Feed `mask_min`/`mask_max` straight into the debug-color `lo`/`hi` above to auto-range a field, or into a Fit expression downstream.

### Author a deterministic multi-field sort key
Pack a primary bucket and a secondary value into one float so a downstream Sort is fully repeatable.
Run over: Points
```vex
// Pack a primary bucket + a secondary value so a downstream Sort is fully deterministic.
int bands = max(chi("bands"), 1);
int bucket = int(fit(@P.y, chf("ylo"), chf("yhi"), 0, bands - 1));
f@sortkey = float(bucket) * 1000.0 + length(@P);
```
Sorting on floating-point position directly can flip near-equal elements run to run; encoding a coarse integer `bucket` in the high digits and a tie-breaker (`length(@P)`) in the low digits makes the order total and stable. Multiply the bucket by a factor comfortably larger than the secondary term's range so the buckets never overlap. Feed `sortkey` to a Sort SOP set to "By Attribute" for deterministic, layered ordering — essential when caching or matching topology across frames.

### Scrub nan/inf, clamp, fix degenerate normals
Sanitize values before they poison a sim or an export — the defensive pass you run at pipeline seams.
Run over: Points
```vex
// Sanitize values before they poison a sim or an export.
if (!isfinite(f@mask)) f@mask = 0.0;       // catches both nan and inf
f@mask = clamp(f@mask, 0.0, 1.0);
if (length(@N) < 1e-6) @N = {0, 1, 0};     // replace a zero-length normal
else @N = normalize(@N);
```
`isfinite` returns false for both NaN and infinity — the poison values a bad divide or a failed solve produces — so this replaces them with a safe default before they spread. The `clamp` keeps a mask in-band, and the zero-length check swaps a degenerate normal (which reads as `{0,0,0}` and breaks displacement, copy-to-points, and lighting) for a sane up-vector. Run this right before any node that assumes clean input; a single NaN entering a sim can blow up the whole frame.

### Split a vector into spreadsheet-friendly scalars
Break a vector into named float columns so the geometry spreadsheet and CSV export are readable.
Run over: Points
```vex
// Break vectors into named float columns for the spreadsheet / CSV export.
f@Px = @P.x;  f@Py = @P.y;  f@Pz = @P.z;
f@speed = length(v@v);
```
The spreadsheet shows a vector as one packed cell, which is awkward to scan or diff; promoting each component to its own float attribute gives sortable, filterable columns. Deriving a scalar like `length(@v)` at the same time gives you a single number to sort or threshold on. This is also the shape most CSV/point-cloud exporters want — flat named scalars rather than compound types — so it doubles as an export-prep step.

## Solver & time feedback

VEX inside a **SOP Solver** is where geometry remembers. The solver loops its own output back as the input each frame, so reading an attribute returns *last frame's* value and writing it hands the result to the next frame — that single fact underlies every idiom here (accumulate, age, latch, diffuse, integrate). A handful need no solver at all, only `@Time`/`@Frame`. Because a SOP Solver can't be single-frame-cooked headlessly, each snippet below was verified in the SOP **Attribute Wrangle** that compiles and runs the identical VEX: input 0 stands in for the solver's looped/previous-frame geometry (pre-seeded with the accumulator, age, `lastP`, etc. that the snippet reads back), and where a snippet reads an explicit Prev_Frame wire it uses input 1. Drop these into the Attribute Wrangle inside a SOP Solver; the tunables and attribute names carry over unchanged.

### Accumulate a value over frames in a SOP Solver
The canonical feedback pattern — build a running total that grows every frame.
Run over: Points
```vex
// Inside a SOP Solver, input 0 IS last frame's geometry, so += integrates over time.
f@accum += f@rate * @TimeInc;              // deposit charge/heat/wear each step
```
The `+=` works *only* because the SOP Solver feeds last frame's geometry back in — outside a solver there's nothing to add to and `f@accum` resets to `rate * TimeInc` every cook. Scaling by `@TimeInc` (seconds per step) rather than a bare constant makes the integration frame-rate and substep independent: the total after one second is the same whether you ran 24 or 240 steps. This is the substrate for wear, charge build-up, exposure — anything that grows with time.

### Trigger-once latch that holds after firing
Set a flag the first frame a condition is true and keep it set forever after.
Run over: Points
```vex
// Set a flag the first frame a condition holds, then never clear it.
if (!i@fired && f@signal > chf("thresh")) {
    i@fired = 1;
    f@fire_time = @Time;                   // remember WHEN it fired
}
```
Gating on `!i@fired` makes the transition strictly one-way — once the signal crosses the threshold the flag latches and the block never runs again, even if the signal later drops. Because the solver preserves `i@fired` across frames, this is a genuine memory cell, not a per-frame test. Recording `@Time` at the moment of firing lets downstream steps compute "time since triggered" for staggered secondary effects (a delayed puff, a fade, a color pulse).

### Per-element age + normalized life
Track how long each element has existed, in frames and in seconds, and normalize it for fades.
Run over: Points
```vex
// Count frames alive and track seconds; normalize against a lifespan for fades.
i@fcount += 1;
f@age += @TimeInc;                         // seconds, sub-step safe
float life = chf("lifespan");
f@nage = (life > 0.0) ? f@age / life : 0.0;   // 0..1 normalized age
```
`i@fcount` counts solver steps while `f@age` accumulates real seconds via `@TimeInc`, so the two answer different questions (steps taken vs. time elapsed). Dividing age by a `lifespan` yields `nage`, a 0..1 progress value perfect for driving a `chramp` fade, a shrink, or a kill test — mirroring the built-in `@nage` that POP systems provide. The `life > 0` guard keeps a zero lifespan from producing infinity.

### Read an explicit Prev_Frame input and step
When you wire Prev_Frame as its own input, read last frame's value from it and take an integration step.
Run over: Points
```vex
// When you wire Prev_Frame into input 1 explicitly, read last frame's value from it.
float prev = point(1, "height", @ptnum);
f@height = prev + f@dhdt * @TimeInc;       // forward Euler integration step
```
Inside a SOP Solver you can wire the Prev_Frame node into a *second* input and read it explicitly with `point(1, ...)`, which is clearer than relying on the implicit input-0 loop when a snippet also reads other geometry. `prev + rate * @TimeInc` is a forward-Euler step — the simplest numerical integrator — advancing `height` by its rate of change each frame. This pattern generalizes to any quantity with a known derivative: temperature, a filling level, a spreading front.

### Keyframe-free motion driven by @Time
Animate geometry purely from `@Time` — a traveling wave with no keyframes and no solver.
Run over: Points
```vex
// Pure @Time animation - a traveling sine wave, no keyframes, no solver required.
float k = max(chf("wavelength"), 1e-3);
@P.y += sin(@P.x / k - @Time * chf("speed")) * chf("amp");
```
Feeding `@Time` into the phase of a `sin` makes the pattern march along X as the timeline plays — position in space sets the wave shape, time shifts it. This is stateless: every frame is computed from scratch, so it's scrubbable and needs no solver (unlike the accumulate/age idioms above). Guarding `wavelength` away from zero avoids a divide blow-up; add a second `sin` at a different frequency for a less mechanical, ocean-like ripple.

### Diffuse a mask toward neighbours each frame
Blur an attribute a little every frame via feedback, so a mask heals, erodes, or spreads smoothly.
Run over: Points
```vex
// Each frame nudge the mask toward its neighbourhood average -> gradual healing/erosion.
int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
float avg = pcfilter(h, "mask");
f@mask = lerp(f@mask, avg, chf("rate"));   // rate 0..1 = heal speed per frame
```
`pcopen`/`pcfilter` average the mask over each point's neighbourhood, and `lerp` moves the current value a fraction (`rate`) toward that average — one smoothing step. Because the solver feeds the result back, repeating it frame after frame is an iterative diffusion: sharp edges soften and holes fill in over time, at a speed you dial with `rate`. A single-frame blur node can't do this; the gradual, time-based spread is the whole point of running it in a solver.

### Spread infection/wetness from neighbours over frames
Contagion: a point flips "on" once a close neighbour is already "on", advancing a front each frame.
Run over: Points
```vex
// Contagion: a dry point turns wet if any close neighbour is already wet.
if (f@wet < 1.0) {
    int h = pcopen(0, "P", @P, chf("radius"), chi("maxpts"));
    int found = pcnumfound(h);
    for (int i = 0; i < found; i++) {
        pciterate(h);
        float nw = 0.0;
        pcimport(h, "wet", nw);
        if (nw > chf("infect_thresh")) {
            f@wet = min(f@wet + chf("gain"), 1.0);
            break;
        }
    }
}
```
The manual `pciterate`/`pcimport` loop walks each neighbour so you can act on the *first* wet one and `break` — cheaper than averaging when you only need existence. Once any neighbour is wet, `f@wet` climbs by `gain` (capped at 1) and the solver carries it forward, so wetness marches outward one ring of neighbours per frame from the initial seeds. Skipping already-saturated points (`f@wet < 1.0`) keeps the front moving instead of re-processing settled area — the classic infection/spread pattern for rust, moss, or fire.

### Velocity from a frame-to-frame position delta
Derive velocity by remembering last frame's position and differencing it against the current one.
Run over: Points
```vex
// Derive velocity from how far a point moved since last frame, then remember P.
vector last = v@lastP;
@v = (@P - last) / max(@TimeInc, 1e-6);
v@lastP = @P;                              // store for next frame's delta
```
When geometry is animated or deformed without an existing `@v`, differencing position across frames reconstructs it: `(current - last) / dt` is the definition of velocity. Storing `@P` into `v@lastP` *after* the difference is essential — it becomes the "last" for the next frame, closing the feedback loop. Dividing by `@TimeInc` (not by 1) yields true units-per-second, so the `@v` reads correctly into trails, motion blur, or as a source for a sim.

### Bake a per-point wake frame, then activate
Store a staggered activation frame once, then flip each element on when the timeline reaches it.
Run over: Points
```vex
// On the start frame, bake a staggered wake frame; then flip active on arrival.
if (@Frame <= chi("start")) {
    f@wake_frame = float(chi("start")) + rand(@ptnum) * chf("spread");
}
i@active = (@Frame >= f@wake_frame) ? 1 : 0;
```
Baking `wake_frame` only on the start frame freezes a per-point random offset (`rand(@ptnum) * spread`) that the solver then preserves, so activation de-syncs into a natural stagger instead of a hard all-at-once switch. Each frame the simple `@Frame >= wake_frame` test turns elements on as the timeline crosses their baked time. Swap `rand(@ptnum)` for a distance-from-impact or a painted value to drive the stagger by space or art direction rather than pure noise.

### Scale rates by @TimeInc for substep stability
Make any per-frame rate substep-correct by expressing it per second, so it doesn't drift when the solver substeps.
Run over: Points
```vex
// Rates must scale by @TimeInc (seconds this step), not per-frame, or they drift
// when the solver substeps. @TimeInc is the portable, substep-correct dt.
f@filled = clamp(f@filled + chf("fill_per_sec") * @TimeInc, 0.0, 1.0);
```
If you add a flat amount per cook, doubling the substep count doubles how much you add per frame — the behavior changes with a setting that should be invisible. Multiplying by `@TimeInc` (the seconds represented by *this* step) makes the total per real second constant no matter how finely the solver subdivides. `@TimeInc` is the portable dt available in both SOP and DOP contexts; DOP substep solvers additionally expose `@SimFrame` (the fractional substep index) when you need to know *which* substep you're on, but for stable rates `@TimeInc` is all you need.

---

## Quick index

- Contexts / run-over → `@ptnum` `@numpt` `@primnum` `@vtxnum` `@elemnum` `@Time` `@Frame`
- Types → `f@ i@ v@ u@ p@ 2@ 3@ 4@ s@` (numeric prefix = N×N matrix; no `9@`/`16@`)
- Remap → `fit fit01 fit11 clamp lerp smooth chramp`
- Channels → `ch chf chv chramp`
- Noise → `noise wnoise flownoise anoise curlnoise rand random`
- Lookups → `point prim vertex detail setpointattrib setprimattrib addpoint addprim removepoint nearpoint nearpoints xyzdist primuv pcopen pcfilter intersect`
- Groups → `i@group_x inpointgroup setpointgroup`
- Cookbook domains (`topic=<key>`) → kinefx · curves · matrix · rbd · pyro · flip · pops · vellum · crowds · orient · noise2 · pointclouds · modeling · uv · heightfield · attribs · groups_adv · vdb · sceneprep · solver
