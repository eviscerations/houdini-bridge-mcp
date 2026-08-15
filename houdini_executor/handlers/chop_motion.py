"""CHOP procedural-motion / channel-math lane — data-only handlers. The generator +
operator CHOP toolbox that sits alongside the KineFX constraint CHOPs (chop_anim_1.py): build a
motion source (wave/noise/waveform/constant/spline/pulse/channel) in a chopnet, then shape it with
channel-math operators (math/function/filter/limit/lag/cycle/blend/merge/warp/resample/... ) wired
in the SAME chopnet. Params + menu tokens verified against live H21.0.671 via hython probe;
every endpoint is proven by a headless CHOP cook (track/sample
readback), the CHOP analogue of prims/points.

ARCHETYPES (per the probe):
  * GENERATORS (chop_wave, chop_waveform, chop_noise, chop_constant, chop_spline, chop_pulse,
    chop_channel) create a fresh /obj chopnet (or reuse an existing `chopnet`) and build the node
    inside it with NO input — they cook standalone.
  * OPERATORS (everything else, incl. chop_oscillator which REQUIRES an input) use
    child_after(params["input"], "<type>", name) to build in the SAME chopnet as the input CHOP,
    wired to input 0. Extra CHOP inputs (input1..input3) are sibling CHOPs in the same chopnet wired
    by DIRECT node.setInput(index, resolve_node(path)) — NEVER object_merge/bridge (that is SOP-only
    and must not be used for CHOP inputs).

SECURITY (data-only, no-file / no-code guarantee): NO handler here exposes any filesystem path, and
NO handler exposes any code / expression / callback parameter.
  * The universal hidden VEX tab every CHOP carries (vex_align / vex_name / vex_start/end/rate /
    vex_edit / vex_reload / vex_num_threads / vex_precision) is a verified false positive and is
    NEVER set or exposed (left at default) on every node.
  * The `wave` (and `oscillator`) `wavetype` menu carries an `expr` option that, when picked, unlocks
    an HScript-expression string parm (`exprs`). The menu token is exposed (harmless — with no
    expression string it produces a flat wave), but the expression string parm `exprs` is NEVER
    exposed on any node.
  * The confirmed code CHOPs (channelwrangle / vopchop / vex / express / logic) and file/media CHOPs
    (file / fbx / rop_channel / image / phoneme) are OUT OF SCOPE and not wrapped here.
  * The `export` / `unload` / `timeslice` / `gcolor` writeback+cook+cosmetic parms are deliberately
    NOT exposed. In-scope string params are channel NAMES / channel-name PATTERNS only (never
    filesystem paths, never code).
"""

import hou
from houdini_executor.server import clamp, child_after, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra, doc):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)  ms=string-menu(tokens)
       v=vector[min,max,len]."""
    for key, parm, kind, extra, _doc in spec:
        if key not in params:
            continue
        v = params[key]
        if kind == "f":
            _try_set(node, parm, clamp(float(v), extra[0], extra[1]))
        elif kind == "i":
            _try_set(node, parm, int(clamp(int(v), extra[0], extra[1])))
        elif kind == "b":
            _try_set(node, parm, bool(v))
        elif kind == "s":
            _try_set(node, parm, str(v))
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)
        elif kind == "v":
            lo, hi, _ln = extra
            _try_set_tuple(node, parm, [clamp(float(x), lo, hi) for x in v])


def _fresh_chopnet(name):
    """Create a fresh /obj chopnet (the CHOP-network container). Fails on name collision."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("chopnet", name) if name else obj.createNode("chopnet")


def _gen_net(params):
    """Container for a GENERATOR CHOP: reuse the `chopnet` path if given (so several generators + an
    operator chain can share one network), else create a fresh chopnet from `name`."""
    if params.get("chopnet"):
        net = resolve_node(params["chopnet"])
        if net.childTypeCategory() != hou.chopNodeTypeCategory():
            raise ValueError("chopnet is not a CHOP network: %s" % params["chopnet"])
        return net
    return _fresh_chopnet(params.get("name"))


def _chop_input(node, path, index):
    """Wire a sibling CHOP (same chopnet) into `node`'s input `index` by direct setInput. CHOP inputs
    are same-network — the SOP object_merge bridge does NOT apply here."""
    node.setInput(index, resolve_node(path))


def _wire_extra(node, params, count):
    """Wire optional extra inputs input1..input<count> (siblings in the same chopnet)."""
    for i in range(1, count + 1):
        key = "input%d" % i
        if params.get(key):
            _chop_input(node, params[key], i)


def _cooked(n):
    """Cook the CHOP and report track/sample counts + errors (the CHOP analogue of prims/points).
    A CHOP graph is built incrementally — a node still missing a required input (blend/composite/
    lookup/warp/copy need a 2nd channel) legitimately fails to cook. Both `n.cook()` AND `n.tracks()`
    lazily cook and can raise hou.OperationFailed, so BOTH are guarded: on failure we return
    cooked:false + the node's error text rather than crashing the caller (mirrors _finish_op)."""
    try:
        n.cook(force=True)
    except hou.OperationFailed:
        pass  # surface the error text below rather than raising
    try:
        tracks = n.tracks()
        ntracks = len(tracks)
        samples = len(tracks[0].allSamples()) if tracks else 0
    except hou.OperationFailed:
        ntracks, samples = 0, 0
    try:
        errs = list(n.errors())
    except Exception:  # noqa: BLE001
        errs = []
    return {
        "node": n.path(),
        "chopnet": n.parent().path(),
        "cooked": ntracks > 0,
        "tracks": ntracks,
        "samples": samples,
        "errors": errs,
    }


# ── param table: chop_wave (wave) ──
_WAVE = [
    ('wave_type', 'wavetype', 'm', ['const', 'sin', 'normal', 'tri', 'ramp', 'square', 'pulse', 'expr'], 'Waveform shape.'),
    ('period', 'period', 'f', (0.0001, 10.0), 'Wave period (cycle length).'),
    ('phase', 'phase', 'f', (-1.0, 1.0), 'Phase offset (0..1 of a cycle).'),
    ('bias', 'bias', 'f', (-1.0, 1.0), 'Shape bias/skew.'),
    ('offset', 'offset', 'f', (-2.0, 2.0), 'Vertical offset added to the wave.'),
    ('amp', 'amp', 'f', (0.0, 10.0), 'Amplitude.'),
    ('decay', 'decay', 'f', (0.0, 1.0), 'Per-cycle amplitude decay.'),
    ('ramp', 'ramp', 'f', (-1.0, 1.0), 'Ramp shape control.'),
    ('channel_name', 'channelname', 's', None, 'Output channel name.'),
    ('range', 'range', 'm', ['full', 'frame', 'user'], 'Frame-range source.'),
    ('start', 'start', 'f', (0.0, 10.0), 'User range start.'),
    ('end', 'end', 'f', (0.0, 10.0), 'User range end.'),
    ('rate', 'rate', 'f', (0.0, 120.0), 'Sample rate.'),
    ('extend_left', 'left', 'm', ['hold', 'slope', 'cycle', 'mirror', 'default', 'cyclestep'], 'Extend condition before the range.'),
]

# ── param table: chop_waveform (waveform) ──
_WAVEFORM = [
    ('waveform', 'wave', 'ms', ['constant', 'sine', 'square'], 'Waveform shape (string token).'),
    ('period', 'period', 'f', (0.0, 10.0), 'Period.'),
    ('phase', 'phase', 'f', (-1.0, 1.0), 'Phase offset.'),
    ('bias', 'bias', 'f', (-1.0, 1.0), 'Shape bias.'),
    ('offset', 'offset', 'f', (-5.0, 5.0), 'Vertical offset.'),
    ('amp', 'amp', 'f', (0.0, 10.0), 'Amplitude.'),
    ('decay', 'decay', 'f', (0.0, 2.0), 'Per-cycle decay.'),
    ('ramp', 'ramp', 'f', (-1.0, 1.0), 'Ramp shape control.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_noise (noise) ──
_NOISE = [
    ('function', 'function', 'm', ['sparse', 'perlin', 'harmonic', 'brownian', 'int', 'alligator'], 'Noise function.'),
    ('seed', 'seed', 'f', (0.0, 10.0), 'Random seed.'),
    ('period', 'period', 'f', (0.0, 10.0), 'Feature period.'),
    ('harmonics', 'harmon', 'i', (0, 10), 'Harmonic count.'),
    ('spread', 'spread', 'f', (0.0, 20.0), 'Harmonic spread.'),
    ('roughness', 'rough', 'f', (0.0, 1.0), 'Roughness.'),
    ('exponent', 'exp', 'f', (0.0, 4.0), 'Value exponent.'),
    ('num_integrals', 'numint', 'i', (0, 5), 'Integral iterations.'),
    ('amp', 'amp', 'f', (0.0, 10.0), 'Amplitude.'),
    ('translate', 'trans', 'v', (0.0, 10.0, 3), 'Noise-field translate [x,y,z].'),
    ('rotate', 'rotate', 'v', (0.0, 360.0, 3), 'Noise-field rotate [x,y,z] (deg).'),
    ('scale', 'scale', 'v', (0.0, 10.0, 3), 'Noise-field scale [x,y,z].'),
]

# ── param table: chop_constant (constant) ──
_CONSTANT = [
    ('name0', 'name0', 's', None, 'Channel 0 name.'),
    ('value0', 'value0', 'f', (-1000000.0, 1000000.0), 'Channel 0 constant value. (range widened from spec [0,1] for usability)'),
    ('name1', 'name1', 's', None, 'Channel 1 name.'),
    ('value1', 'value1', 'f', (-1000000.0, 1000000.0), 'Channel 1 constant value. (widened)'),
    ('name2', 'name2', 's', None, 'Channel 2 name.'),
    ('value2', 'value2', 'f', (-1000000.0, 1000000.0), 'Channel 2 constant value. (widened)'),
    ('name3', 'name3', 's', None, 'Channel 3 name.'),
    ('value3', 'value3', 'f', (-1000000.0, 1000000.0), 'Channel 3 constant value. (widened)'),
]

# ── param table: chop_spline (spline) ──
_SPLINE = [
    ('type', 'type', 'm', ['bezier', 'cubic'], 'Spline type.'),
    ('compute', 'compute', 'b', None, 'Recompute the spline.'),
    ('relative', 'relative', 'm', ['abs', 'rel'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Range end.'),
    ('tolerance', 'tolerance', 'f', (0.0, 10.0), 'Fit tolerance.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_pulse (pulse) ──
_PULSE = [
    ('number', 'number', 'i', (1, 32), 'Number of pulses.'),
    ('interp', 'interp', 'm', ['nointerp', 'linear', 'easein', 'easeout', 'cosine', 'cubic'], 'Between-pulse interpolation.'),
    ('width', 'width', 'f', (0.0, 1.0), 'Pulse width.'),
    ('limit', 'limit', 'm', ['nolimit', 'clamp'], 'Value limiting.'),
    ('min', 'min', 'f', (-10.0, 10.0), 'Clamp minimum.'),
    ('max', 'max', 'f', (-10.0, 10.0), 'Clamp maximum.'),
    ('last_pulse', 'lastpulse', 'b', None, 'Emit a final pulse.'),
    ('pulse0', 'pulse0', 'f', (0.0, 10.0), 'Pulse 0 value.'),
    ('pulse1', 'pulse1', 'f', (0.0, 10.0), 'Pulse 1 value.'),
    ('pulse2', 'pulse2', 'f', (0.0, 10.0), 'Pulse 2 value.'),
    ('pulse3', 'pulse3', 'f', (0.0, 10.0), 'Pulse 3 value.'),
]

# ── param table: chop_channel (channel) ──
_CHANNEL = [
    ('show_all', 'showall', 'b', None, 'Show all channels.'),
    ('key_per_sample', 'keypersample', 'b', None, 'One key per sample.'),
    ('add_deps', 'adddeps', 'b', None, 'Add parameter dependencies.'),
    ('range', 'range', 'm', ['full', 'frame', 'user', 'value'], 'Frame-range source.'),
    ('exact_time', 'exacttime', 'b', None, 'Sample at exact time.'),
    ('start', 'start', 'f', (0.0, 10.0), 'User range start.'),
    ('end', 'end', 'f', (0.0, 10.0), 'User range end.'),
    ('rate', 'rate', 'f', (0.0, 120.0), 'Sample rate.'),
    ('extend_left', 'left', 'm', ['hold', 'slope', 'cycle', 'mirror', 'default', 'cyclestep'], 'Extend condition before the range.'),
]

# ── param table: chop_oscillator (oscillator) ──
_OSCILLATOR = [
    ('wave_type', 'wavetype', 'm', ['sin', 'normal', 'tri', 'ramp', 'square', 'pulse'], 'Waveform shape.'),
    ('frequency', 'frequency', 'f', (0.0, 1000.0), 'Base frequency (Hz).'),
    ('octave', 'octave', 'f', (-10.0, 10.0), 'Octave shift.'),
    ('offset', 'offset', 'f', (-2.0, 2.0), 'Vertical offset.'),
    ('amp', 'amp', 'f', (0.0, 10.0), 'Amplitude.'),
    ('bias', 'bias', 'f', (-1.0, 1.0), 'Shape bias.'),
    ('phase', 'phase', 'f', (0.0, 1.0), 'Phase offset.'),
    ('smooth', 'smooth', 'b', None, 'Smooth transitions.'),
    ('rate', 'rate', 'f', (0.0, 44100.0), 'Sample rate (Hz).'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_math (math) ──
_MATH = [
    ('pre_op', 'preop', 'm', ['off', 'negate', 'pos', 'root', 'square', 'inverse'], 'Pre-operation on each channel.'),
    ('channel_op', 'chanop', 'm', ['off', 'add', 'sub', 'mul', 'div', 'avg', 'min', 'max', 'len'], 'Combine channels within one input.'),
    ('chop_op', 'chopop', 'm', ['off', 'add', 'sub', 'mul', 'div', 'avg', 'min', 'max', 'len'], 'Combine across wired inputs.'),
    ('post_op', 'postop', 'm', ['off', 'negate', 'pos', 'root', 'square', 'inverse'], 'Post-operation.'),
    ('match', 'match', 'm', ['index', 'name'], 'Channel matching mode.'),
    ('match_failure', 'matchfailure', 'm', ['error', 'warning', 'ignore'], 'Behavior on match failure.'),
    ('align', 'align', 'm', ['none', 'stretch', 'start', 'end', 'shift1', 'trim1', 'stretch1', 'trim', 'squash'], 'Time alignment of inputs.'),
    ('pre_offset', 'preoff', 'f', (-10.0, 10.0), 'Offset added before gain.'),
    ('gain', 'gain', 'f', (-1.0, 10.0), 'Gain multiplier.'),
    ('post_offset', 'postoff', 'f', (-10.0, 10.0), 'Offset added after gain.'),
    ('from_range', 'fromrange', 'v', (0.0, 10.0, 2), 'Remap source range [min,max].'),
    ('to_range', 'torange', 'v', (0.0, 10.0, 2), 'Remap destination range [min,max].'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_function (function) ──
_FUNCTION = [
    ('func', 'func', 'm', ['sqrt', 'abs', 'sign', 'cos', 'sin', 'tan', 'acos', 'asin', 'atan', 'atan2', 'cosh', 'sinh', 'tanh', 'log', 'logb', 'ln', 'pow10', 'exp', 'powe', 'powb', 'pow'], 'Function.'),
    ('base_value', 'baseval', 'f', (0.0, 10.0), 'Base value (for pow/logb).'),
    ('exp_value', 'expval', 'f', (0.0, 10.0), 'Exponent value (for pow).'),
    ('angle_unit', 'angunit', 'm', ['deg', 'rad', 'cycle'], 'Angle unit for trig.'),
    ('match', 'match', 'm', ['index', 'name'], 'Channel matching mode.'),
    ('match_failure', 'matchfailure', 'm', ['error', 'warning', 'ignore'], 'Behavior on match failure.'),
    ('error', 'error', 'm', ['abort', 'replace', 'useprev'], 'Behavior on domain error.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_filter (filter) ──
_FILTER = [
    ('type', 'type', 'm', ['gauss', 'halfgauss', 'box', 'halfbox', 'edge', 'sharpen', 'despike'], 'Filter type.'),
    ('effect', 'effect', 'f', (0.0, 1.0), 'Effect amount.'),
    ('width', 'width', 'f', (0.001, 2.0), 'Filter width.'),
    ('spike', 'spike', 'f', (0.0, 1.0), 'Despike threshold.'),
    ('passes', 'passes', 'i', (1, 10), 'Filter passes.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_limit (limit) ──
_LIMIT = [
    ('type', 'type', 'm', ['off', 'clamp', 'loop', 'zigzag'], 'Limiting mode.'),
    ('min', 'min', 'f', (-10.0, 10.0), 'Minimum.'),
    ('max', 'max', 'f', (-10.0, 10.0), 'Maximum.'),
    ('positive', 'positive', 'b', None, 'Keep positive only.'),
    ('norm', 'norm', 'b', None, 'Normalize.'),
    ('quant_value', 'quantvalue', 'm', ['off', 'ceiling', 'floor', 'round'], 'Value quantization.'),
    ('value_step', 'vstep', 'f', (0.0001, 1.0), 'Value quantization step.'),
    ('value_offset', 'voffset', 'f', (-1.0, 1.0), 'Value quantization offset.'),
    ('quant_index', 'quantindex', 'm', ['off', 'relstart', 'relzero'], 'Index quantization.'),
    ('index_step', 'istep', 'f', (0.0, 2.0), 'Index quantization step.'),
    ('index_offset', 'ioffset', 'f', (-1.0, 1.0), 'Index quantization offset.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_lag (lag) ──
_LAG = [
    ('lag_method', 'lagmethod', 'm', ['value', 'amp', 'mag'], 'Lag method.'),
    ('lag', 'lag', 'v', (0.0, 1.0, 2), 'Lag amount [rise,fall].'),
    ('overshoot', 'overshoot', 'v', (0.0, 1.0, 2), 'Overshoot [rise,fall].'),
    ('clamp', 'clamp', 'b', None, 'Clamp slope.'),
    ('slope', 'slope', 'v', (0.0, 2.0, 2), 'Max slope [rise,fall].'),
    ('accel_clamp', 'aclamp', 'b', None, 'Clamp acceleration.'),
    ('accel', 'accel', 'v', (0.0, 2.0, 2), 'Max acceleration [rise,fall].'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_lookup (lookup) ──
_LOOKUP = [
    ('index', 'index', 'v', (0.0, 10.0, 2), 'Index range [min,max].'),
    ('channel_match', 'chanmatch', 'm', ['onetoone', 'onetomany'], 'Channel matching.'),
    ('match', 'match', 'm', ['index', 'name'], 'Match mode.'),
    ('match_failure', 'matchfailure', 'm', ['error', 'warning', 'ignore'], 'Behavior on match failure.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_cycle (cycle) ──
_CYCLE = [
    ('before', 'before', 'f', (0.0, 20.0), 'Cycles before.'),
    ('after', 'after', 'f', (0.0, 20.0), 'Cycles after.'),
    ('mirror', 'mirror', 'b', None, 'Mirror alternate cycles.'),
    ('extremes', 'extremes', 'b', None, 'Include end extremes.'),
    ('blend_method', 'blendmethod', 'm', ['pre', 'ovl', 'ins'], 'Blend method.'),
    ('blend_func', 'blendfunc', 'm', ['lin', 'ei', 'eo', 'cos', 'cub', 'add'], 'Blend function.'),
    ('blend_region', 'blendregion', 'f', (0.0, 10.0), 'Blend region size.'),
    ('blend_bias', 'blendbias', 'f', (-1.0, 1.0), 'Blend bias.'),
    ('step', 'step', 'f', (0.0, 1.0), 'Cycle step.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_blend (blend) ──
_BLEND = [
    ('method', 'method', 'm', ['prop', 'dif'], 'Blend method (proportional/difference).'),
    ('first_weight', 'firstweight', 'b', None, 'Use the first input as weights.'),
    ('rotation_blend', 'shotrotblend', 'm', ['off', 'on', 'nlerp'], 'Rotation blending mode.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_merge (merge) ──
_MERGE = [
    ('align', 'align', 'm', ['none', 'stretch', 'start', 'end', 'shift1', 'trim1', 'stretch1', 'trim', 'squash'], 'Time alignment.'),
    ('duplicate', 'duplicate', 'm', ['unique', 'first', 'last', 'override'], 'Duplicate-name handling.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_warp (warp) ──
_WARP = [
    ('method', 'method', 'm', ['rate', 'index'], 'Warp method.'),
    ('scale_index', 'scaleindex', 'b', None, 'Scale the warp index.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_resample (resample) ──
_RESAMPLE = [
    ('method', 'method', 'm', ['strech', 'preserve', 'index', 'newint'], 'Resample method.'),
    ('rate', 'rate', 'f', (0.0, 120.0), 'New sample rate.'),
    ('relative', 'relative', 'm', ['abs', 'rel'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Range end.'),
    ('interp', 'interp', 'm', ['nointerp', 'linear', 'cubic', 'edge'], 'Interpolation.'),
    ('const_area', 'constarea', 'b', None, 'Preserve area.'),
    ('correct', 'correct', 'b', None, 'Correct for cyclic data.'),
    ('cycle_length', 'cyclelen', 'f', (0.0, 360.0), 'Cycle length (for correction).'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_shift (shift) ──
_SHIFT = [
    ('reference', 'reference', 'm', ['refstart', 'refend'], 'Reference edge.'),
    ('relative', 'relative', 'm', ['abs', 'rel', 'cur'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'New range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'New range end.'),
    ('scroll', 'scroll', 'f', (-10.0, 10.0), 'Scroll amount.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_hold (hold) ──
_HOLD = [
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_spectrum (spectrum) ──
_SPECTRUM = [
    ('convert', 'convert', 'm', ['tofreq', 'fromfreq'], 'Conversion direction.'),
    ('segment', 'segment', 'b', None, 'Segment the signal.'),
    ('relative', 'relative', 'm', ['abs', 'rel', 'cur', 'slice'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Range end.'),
    ('mag_suffix', 'magsuffix', 's', None, 'Magnitude channel suffix.'),
    ('phase_suffix', 'phasesuffix', 's', None, 'Phase channel suffix.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_multiply (multiply) ──
_MULTIPLY = [
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_invert (invert) ──
_INVERT = [
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_extend (extend) ──
_EXTEND = [
    ('left', 'left', 'm', ['asis', 'hold', 'slope', 'cycle', 'mirror', 'default', 'cyclestep'], 'Extend before the range.'),
    ('right', 'right', 'm', ['asis', 'hold', 'slope', 'cycle', 'mirror', 'default', 'cyclestep'], 'Extend after the range.'),
    ('default_value', 'defval', 'f', (-10.0, 10.0), "Default value for 'default' extend."),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_stretch (stretch) ──
_STRETCH = [
    ('interp', 'interp', 'm', ['nointerp', 'linear', 'cubic', 'edge'], 'Interpolation.'),
    ('const_area', 'constarea', 'b', None, 'Preserve area.'),
    ('relative', 'relative', 'm', ['abs', 'rel'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Range end.'),
    ('scale', 'scale', 'f', (0.0, 10.0), 'Value scale.'),
    ('reverse', 'reverse', 'b', None, 'Reverse in time.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_trim (trim) ──
_TRIM = [
    ('relative', 'relative', 'm', ['abs', 'rel', 'cur', 'slice'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Trim start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Trim end.'),
    ('discard', 'discard', 'm', ['trimExt', 'trimInt'], 'Discard exterior or interior.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_area (area) ──
_AREA = [
    ('order', 'order', 'm', ['first', 'second', 'third'], 'Integration order.'),
    ('constant1', 'constant1', 'f', (-10.0, 10.0), 'Integration constant 1.'),
    ('constant2', 'constant2', 'f', (-10.0, 10.0), 'Integration constant 2.'),
    ('constant3', 'constant3', 'f', (-10.0, 10.0), 'Integration constant 3.'),
    ('relative', 'relative', 'm', ['abs', 'rel'], 'Range interpretation.'),
    ('start', 'start', 'f', (-10.0, 10.0), 'Range start.'),
    ('end', 'end', 'f', (-10.0, 10.0), 'Range end.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_envelope (envelope) ──
_ENVELOPE = [
    ('method', 'method', 'm', ['exp', 'window'], 'Envelope method.'),
    ('bounds', 'bounds', 'm', ['mag', 'power', 'min', 'max'], 'Bounds measure.'),
    ('width', 'width', 'f', (0.0, 10.0), 'Envelope width.'),
    ('interp', 'interp', 'm', ['none', 'linear', 'cubic'], 'Interpolation.'),
    ('norm', 'norm', 'b', None, 'Normalize.'),
    ('resample', 'resample', 'b', None, 'Resample the envelope.'),
    ('sample_rate', 'samplerate', 'f', (0.0, 120.0), 'Resample rate.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_interp (interp) ──
_INTERP = [
    ('blend_func', 'blendfunc', 'm', ['lin', 'ei', 'eo', 'cos', 'cub', 'add'], 'Blend function.'),
    ('overlap', 'overlap', 'm', ['avg', 'first', 'last'], 'Overlap handling.'),
    ('match', 'match', 'm', ['index', 'name'], 'Channel matching.'),
    ('match_failure', 'matchfailure', 'm', ['error', 'warning', 'ignore'], 'Behavior on match failure.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_delay (delay) ──
_DELAY = [
    ('num_copies', 'numcopies', 'i', (1, 4), 'Number of echoes.'),
    ('remainder', 'remainder', 'm', ['crop', 'extend', 'mix'], 'Remainder handling.'),
    ('delay1', 'delay1', 'f', (0.0, 4.0), 'Echo 1 delay.'),
    ('gain1', 'gain1', 'f', (0.0, 2.0), 'Echo 1 gain.'),
    ('delay2', 'delay2', 'f', (0.0, 4.0), 'Echo 2 delay.'),
    ('gain2', 'gain2', 'f', (0.0, 2.0), 'Echo 2 gain.'),
    ('delay3', 'delay3', 'f', (0.0, 4.0), 'Echo 3 delay.'),
    ('gain3', 'gain3', 'f', (0.0, 2.0), 'Echo 3 gain.'),
    ('delay4', 'delay4', 'f', (0.0, 4.0), 'Echo 4 delay.'),
    ('gain4', 'gain4', 'f', (0.0, 2.0), 'Echo 4 gain.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_slope (slope) ──
_SLOPE = [
    ('type', 'type', 'm', ['slope', 'accel', 'slacc'], 'Derivative type.'),
    ('method', 'method', 'm', ['pc', 'cn', 'pn'], 'Difference method.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_fan (fan) ──
_FAN = [
    ('fan_op', 'fanop', 'm', ['out', 'in'], 'Fan out or in.'),
    ('channel_name', 'channame', 's', None, 'Channel-name pattern for the fan.'),
    ('range', 'range', 'm', ['clamp', 'loop', 'zero'], 'Out-of-range handling.'),
    ('all_off', 'alloff', 'm', ['set0', 'setneg'], 'Value when all off.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_count (count) ──
_COUNT = [
    ('threshold', 'threshold', 'b', None, 'Enable thresholding.'),
    ('thresh_up', 'threshup', 'f', (0.0, 10.0), 'Rising threshold.'),
    ('thresh_down', 'threshdown', 'f', (0.0, 10.0), 'Falling threshold.'),
    ('retrigger', 'retrigger', 'f', (0.0, 20.0), 'Retrigger delay.'),
    ('trigger_on', 'triggeron', 'm', ['increase', 'decrease'], 'Trigger edge.'),
    ('output', 'output', 'm', ['off', 'loop', 'min', 'lc', 'cl'], 'Output mode.'),
    ('limit_min', 'limitmin', 'f', (0.0, 20.0), 'Count minimum.'),
    ('limit_max', 'limitmax', 'f', (0.0, 20.0), 'Count maximum.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_null (null) ──
_NULL = [
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_vector (vector) ──
_VECTOR = [
    ('operation', 'operation', 'm', ['magnitude', 'normalize', 'distance', 'dot', 'normdot', 'angle', 'cross', 'sproject', 'vproject', 'add', 'sub', 'subba', 'nop'], 'Vector operation.'),
    ('vector_mask', 'vectormask', 's', None, 'Channel mask for vector A.'),
    ('use_b_mask', 'usebmask', 'b', None, 'Use a separate mask for vector B.'),
    ('vector_mask_b', 'vectormaskb', 's', None, 'Channel mask for vector B.'),
    ('use_c_mask', 'usecmask', 'b', None, 'Use a separate mask for vector C.'),
    ('vector_mask_c', 'vectormaskc', 's', None, 'Channel mask for vector C.'),
    ('align', 'align', 'm', ['none', 'stretch', 'start', 'end', 'shift1', 'trim1', 'stretch1', 'trim', 'squash'], 'Time alignment.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
]

# ── param table: chop_attribute (attribute) ──
_ATTRIBUTE = [
    ('slerp', 'slerp', 'm', ['pass', 'replace', 'append', 'remove'], 'Rotation-attribute action.'),
    ('rotation_order', 'rOrd', 'm', ['xyz', 'xzy', 'yxz', 'yzx', 'zxy', 'zyx'], 'Rotation order.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_copy (copy) ──
_COPY = [
    ('method', 'method', 'm', ['trigger', 'convolve'], 'Copy method.'),
    ('output', 'output', 'm', ['match', 'accum'], 'Output mode.'),
    ('threshold', 'threshold', 'f', (0.0, 10.0), 'Trigger threshold.'),
    ('remainder', 'remainder', 'm', ['crop', 'extend', 'mix'], 'Remainder handling.'),
    ('keep', 'keep', 'b', None, 'Keep the source frames.'),
]

# ── param table: chop_shuffle (shuffle) ──
_SHUFFLE = [
    ('method', 'method', 'm', ['off', 'swap', 'seqname', 'seqall', 'seqn', 'seqeveryn', 'splitall', 'splitn', 'spliteveryn'], 'Shuffle method.'),
    ('n_value', 'nval', 'i', (1, 12), 'N value for the method.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_reorder (reorder) ──
_REORDER = [
    ('method', 'method', 'm', ['numeric', 'character', 'basename', 'numsuffix'], 'Reorder method.'),
    ('num_pattern', 'numpattern', 's', None, 'Numeric ordering pattern.'),
    ('char_pattern', 'charpattern', 's', None, 'Character ordering pattern.'),
    ('remainder_pos', 'rempos', 'm', ['begin', 'end'], 'Where to place unmatched channels.'),
    ('remainder_order', 'remorder', 'm', ['input', 'alpha'], 'Order of unmatched channels.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_rename (rename) ──
_RENAME = [
    ('rename_from', 'renamefrom', 's', None, 'Source channel-name pattern.'),
    ('rename_to', 'renameto', 's', None, 'Destination channel-name pattern.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_delete (delete) ──
_DELETE = [
    ('discard', 'discard', 'm', ['scoped', 'nonscoped'], 'Discard scoped or non-scoped.'),
    ('select', 'select', 'm', ['byname', 'bynum'], 'Selection mode.'),
    ('delete_scope', 'delscope', 's', None, 'Channel-name pattern to delete.'),
    ('select_numbers', 'selnumbers', 's', None, 'Channel-number selection.'),
    ('channel_value', 'chanvalue', 'm', ['off', 'complete', 'partial', 'outside'], 'Value-based deletion.'),
    ('select_range', 'selrange', 'v', (-10.0, 10.0, 2), 'Value range [min,max]. (min widened from spec [0,10] to admit default -1)'),
    ('select_constant', 'selconst', 'b', None, 'Delete constant channels.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_switch (switch) ──
_SWITCH = [
    ('index_first', 'indexfirst', 'b', None, 'Index the first input as 0.'),
    ('index', 'index', 'i', (0, 10), 'Selected input index.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_layer (layer) ──
_LAYER = [
    ('active', 'active', 'i', (0, 10), 'Active layer index.'),
    ('scope', 'scope', 's', None, 'Channel-name pattern selecting which channels are affected.'),
    ('sample_rate_select', 'srselect', 'm', ['first', 'max', 'min', 'err'], 'Sample-rate reconciliation when inputs differ.'),
    ('units', 'units', 'm', ['frames', 'samples', 'seconds'], 'Units for time-valued parameters.'),
]

# ── param table: chop_composite (comp) ──
_COMPOSITE = [
    ('base', 'base', 'f', (0.0, 10.0), 'Base value.'),
    ('match', 'match', 'm', ['index', 'name', 'union'], 'Channel matching.'),
    ('match_failure', 'matchfailure', 'm', ['error', 'warning', 'ignore'], 'Behavior on match failure.'),
    ('quat_rot', 'quatrot', 'b', None, 'Quaternion rotation blend.'),
    ('short_rot', 'shortrot', 'b', None, 'Shortest-path rotation.'),
    ('rot_scope', 'rotscope', 's', None, 'Rotation channel pattern.'),
    ('cycle_length', 'cyclelen', 'f', (0.0, 360.0), 'Cycle length.'),
    ('effect', 'effect', 'f', (0.0, 10.0), 'Effect amount.'),
    ('relative', 'relative', 'm', ['abs', 'rel', 'cur'], 'Range interpretation.'),
    ('start', 'start', 'f', (0.0, 10.0), 'Rise start.'),
    ('peak', 'peak', 'f', (0.0, 10.0), 'Peak time.'),
    ('release', 'release', 'f', (-10.0, 0.0), 'Release time.'),
    ('end', 'end', 'f', (-10.0, 0.0), 'End time.'),
    ('rise_func', 'risefunc', 'm', ['lin', 'ei', 'eo', 'cos', 'cub', 'add'], 'Rise function.'),
    ('fall_func', 'fallfunc', 'm', ['lin', 'ei', 'eo', 'cos', 'cub', 'add'], 'Fall function.'),
]

# ── param table: chop_trigger (trigger) ──
_TRIGGER = [
    ('threshold', 'threshold', 'b', None, 'Enable thresholding.'),
    ('thresh_up', 'threshup', 'f', (0.0, 2.0), 'Rising threshold.'),
    ('thresh_down', 'threshdown', 'f', (0.0, 2.0), 'Falling threshold.'),
    ('retrigger', 'retrigger', 'f', (0.0, 2.0), 'Retrigger delay.'),
    ('min_trigger', 'mintrigger', 'f', (0.0, 4.0), 'Minimum trigger interval.'),
    ('trigger_on', 'triggeron', 'm', ['increase', 'decrease'], 'Trigger edge.'),
    ('delay', 'delay', 'f', (0.0, 2.0), 'Delay.'),
    ('attack', 'attack', 'f', (0.0, 2.0), 'Attack time.'),
    ('attack_shape', 'ashape', 'm', ['linear', 'easein', 'easeout', 'halfcos'], 'Attack shape.'),
    ('peak', 'peak', 'f', (0.0, 2.0), 'Peak level.'),
    ('peak_length', 'peaklen', 'f', (0.0, 2.0), 'Peak hold length.'),
    ('decay', 'decay', 'f', (0.0, 2.0), 'Decay time.'),
    ('decay_shape', 'dshape', 'm', ['linear', 'easein', 'easeout', 'halfcos'], 'Decay shape.'),
    ('sustain', 'sustain', 'f', (0.0, 2.0), 'Sustain level.'),
    ('release', 'release', 'f', (0.0, 2.0), 'Release time.'),
]

@endpoint("chop_wave")
def chop_wave(params):
    """CHOP Wave (wave) — generates a periodic waveform channel (sine/triangle/ramp/square/pulse) over a frame range. GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("wave")
    _apply(n, params, _WAVE)
    return _cooked(n)


@endpoint("chop_waveform")
def chop_waveform(params):
    """CHOP Waveform (waveform) — generates a constant/sine/square waveform channel (data-driven waveform source). GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("waveform")
    _apply(n, params, _WAVEFORM)
    return _cooked(n)


@endpoint("chop_noise")
def chop_noise(params):
    """CHOP Noise (noise) — generates an animated noise channel (sparse/perlin/harmonic/brownian/alligator). GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("noise")
    _apply(n, params, _NOISE)
    return _cooked(n)


@endpoint("chop_constant")
def chop_constant(params):
    """CHOP Constant (constant) — generates channels holding constant values (up to four named channels). GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("constant")
    _apply(n, params, _CONSTANT)
    return _cooked(n)


@endpoint("chop_spline")
def chop_spline(params):
    """CHOP Spline (spline) — generates a spline-interpolated channel (bezier/cubic) over a range. GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("spline")
    _apply(n, params, _SPLINE)
    return _cooked(n)


@endpoint("chop_pulse")
def chop_pulse(params):
    """CHOP Pulse (pulse) — generates a sequence of value pulses over a range. GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("pulse")
    _apply(n, params, _PULSE)
    return _cooked(n)


@endpoint("chop_channel")
def chop_channel(params):
    """CHOP Channel (channel) — generates channels sampled from parameter channels / keyframes over a range. GENERATOR: fresh chopnet, cooks standalone. Data-only: channel math only, no file/code/expression surface."""
    n = _gen_net(params).createNode("channel")
    _apply(n, params, _CHANNEL)
    return _cooked(n)


@endpoint("chop_oscillator")
def chop_oscillator(params):
    """CHOP Oscillator (oscillator) — audio-style oscillator driven by an input channel (REQUIRES an input CHOP). OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "oscillator", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, _OSCILLATOR)
    return _cooked(n)


@endpoint("chop_math")
def chop_math(params):
    """CHOP Math (math) — per-channel and cross-CHOP arithmetic, gain and remap. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "math", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _MATH)
    return _cooked(n)


@endpoint("chop_function")
def chop_function(params):
    """CHOP Function (function) — applies a math function (sqrt/trig/log/pow/...) to the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "function", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _FUNCTION)
    return _cooked(n)


@endpoint("chop_filter")
def chop_filter(params):
    """CHOP Filter (filter) — temporal filter (gaussian/box/edge/sharpen/despike) on input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "filter", params.get("name"))
    _apply(n, params, _FILTER)
    return _cooked(n)


@endpoint("chop_limit")
def chop_limit(params):
    """CHOP Limit (limit) — clamps / loops / quantizes input channel values. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "limit", params.get("name"))
    _apply(n, params, _LIMIT)
    return _cooked(n)


@endpoint("chop_lag")
def chop_lag(params):
    """CHOP Lag (lag) — smooths input channels with lag/overshoot (spring-like follow). OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "lag", params.get("name"))
    _apply(n, params, _LAG)
    return _cooked(n)


@endpoint("chop_lookup")
def chop_lookup(params):
    """CHOP Lookup (lookup) — uses input 0 as an index to look up values in input 1. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "lookup", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _LOOKUP)
    return _cooked(n)


@endpoint("chop_cycle")
def chop_cycle(params):
    """CHOP Cycle (cycle) — repeats/mirrors the input channels before and after with optional blends. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "cycle", params.get("name"))
    _apply(n, params, _CYCLE)
    return _cooked(n)


@endpoint("chop_blend")
def chop_blend(params):
    """CHOP Blend (blend) — weight-blends channels across wired inputs. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "blend", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _BLEND)
    return _cooked(n)


@endpoint("chop_merge")
def chop_merge(params):
    """CHOP Merge (merge) — merges the channels of all wired inputs into one stream. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "merge", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _MERGE)
    return _cooked(n)


@endpoint("chop_warp")
def chop_warp(params):
    """CHOP Warp (warp) — time-warps input 0 by the warp channel on input 1. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "warp", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _WARP)
    return _cooked(n)


@endpoint("chop_resample")
def chop_resample(params):
    """CHOP Resample (resample) — resamples the input channels to a new rate / range. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "resample", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _RESAMPLE)
    return _cooked(n)


@endpoint("chop_shift")
def chop_shift(params):
    """CHOP Shift (shift) — shifts / scrolls the input channels in time. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "shift", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _SHIFT)
    return _cooked(n)


@endpoint("chop_hold")
def chop_hold(params):
    """CHOP Hold (hold) — holds (sample-and-holds) the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "hold", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _HOLD)
    return _cooked(n)


@endpoint("chop_spectrum")
def chop_spectrum(params):
    """CHOP Spectrum (spectrum) — converts input channels to/from the frequency domain. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "spectrum", params.get("name"))
    _apply(n, params, _SPECTRUM)
    return _cooked(n)


@endpoint("chop_multiply")
def chop_multiply(params):
    """CHOP Multiply (multiply) — multiplies the channels of all wired inputs together. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "multiply", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _MULTIPLY)
    return _cooked(n)


@endpoint("chop_invert")
def chop_invert(params):
    """CHOP Invert (invert) — inverts (reciprocal) the input channel values. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "invert", params.get("name"))
    _apply(n, params, _INVERT)
    return _cooked(n)


@endpoint("chop_extend")
def chop_extend(params):
    """CHOP Extend (extend) — sets how the input channels extend before/after their range. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "extend", params.get("name"))
    _apply(n, params, _EXTEND)
    return _cooked(n)


@endpoint("chop_stretch")
def chop_stretch(params):
    """CHOP Stretch (stretch) — stretches the input channels in time and value. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "stretch", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _STRETCH)
    return _cooked(n)


@endpoint("chop_trim")
def chop_trim(params):
    """CHOP Trim (trim) — trims the input channels to a sub-range. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "trim", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _TRIM)
    return _cooked(n)


@endpoint("chop_area")
def chop_area(params):
    """CHOP Area (area) — integrates the input channels (area / running integral). OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "area", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, _AREA)
    return _cooked(n)


@endpoint("chop_envelope")
def chop_envelope(params):
    """CHOP Envelope (envelope) — extracts the amplitude envelope of the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "envelope", params.get("name"))
    _apply(n, params, _ENVELOPE)
    return _cooked(n)


@endpoint("chop_interp")
def chop_interp(params):
    """CHOP Interpolate (interp) — interpolates between the wired inputs over time. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "interp", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _INTERP)
    return _cooked(n)


@endpoint("chop_delay")
def chop_delay(params):
    """CHOP Delay (delay) — adds delayed, gained echoes of the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "delay", params.get("name"))
    _apply(n, params, _DELAY)
    return _cooked(n)


@endpoint("chop_slope")
def chop_slope(params):
    """CHOP Slope (slope) — computes the slope / acceleration (derivative) of the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "slope", params.get("name"))
    _apply(n, params, _SLOPE)
    return _cooked(n)


@endpoint("chop_fan")
def chop_fan(params):
    """CHOP Fan (fan) — fans one channel out to many, or fans many channels in to one. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "fan", params.get("name"))
    _apply(n, params, _FAN)
    return _cooked(n)


@endpoint("chop_count")
def chop_count(params):
    """CHOP Count (count) — counts threshold crossings of the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "count", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, _COUNT)
    return _cooked(n)


@endpoint("chop_null")
def chop_null(params):
    """CHOP Null (null) — pass-through null (a stable named tap into the channel stream). OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "null", params.get("name"))
    _apply(n, params, _NULL)
    return _cooked(n)


@endpoint("chop_vector")
def chop_vector(params):
    """CHOP Vector (vector) — vector operations (magnitude/normalize/dot/cross/project/...) on channel triples. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "vector", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, _VECTOR)
    return _cooked(n)


@endpoint("chop_attribute")
def chop_attribute(params):
    """CHOP Attribute (attribute) — manages transform attributes (rotation order / slerp) on the channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "attribute", params.get("name"))
    _apply(n, params, _ATTRIBUTE)
    return _cooked(n)


@endpoint("chop_copy")
def chop_copy(params):
    """CHOP Copy (copy) — stamps input 0 at each trigger sample of input 1. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "copy", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _COPY)
    return _cooked(n)


@endpoint("chop_shuffle")
def chop_shuffle(params):
    """CHOP Shuffle (shuffle) — reorders / splits / sequences the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "shuffle", params.get("name"))
    _apply(n, params, _SHUFFLE)
    return _cooked(n)


@endpoint("chop_reorder")
def chop_reorder(params):
    """CHOP Reorder (reorder) — reorders channels by numeric / character pattern. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "reorder", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _REORDER)
    return _cooked(n)


@endpoint("chop_rename")
def chop_rename(params):
    """CHOP Rename (rename) — renames channels by pattern. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "rename", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _RENAME)
    return _cooked(n)


@endpoint("chop_delete")
def chop_delete(params):
    """CHOP Delete (delete) — deletes channels by name or number. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "delete", params.get("name"))
    _wire_extra(n, params, 1)
    _apply(n, params, _DELETE)
    return _cooked(n)


@endpoint("chop_switch")
def chop_switch(params):
    """CHOP Switch (switch) — passes through one of the wired inputs, selected by index. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "switch", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _SWITCH)
    return _cooked(n)


@endpoint("chop_layer")
def chop_layer(params):
    """CHOP Layer (layer) — layers the wired inputs with per-layer weights (active layer selects the base). OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "layer", params.get("name"))
    _wire_extra(n, params, 3)
    _apply(n, params, _LAYER)
    return _cooked(n)


@endpoint("chop_composite")
def chop_composite(params):
    """CHOP Composite (comp) — composites (additive rise/peak/release) the wired inputs. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "comp", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, _COMPOSITE)
    return _cooked(n)


@endpoint("chop_trigger")
def chop_trigger(params):
    """CHOP Trigger (trigger) — generates an ADSR-style envelope triggered by the input channels. OPERATOR: wired to input 0 in the input's chopnet. Data-only: channel math only, no file/code/expression surface."""
    n = child_after(params["input"], "trigger", params.get("name"))
    _apply(n, params, _TRIGGER)
    return _cooked(n)


