"""Tag every tool in reference/tool_nodes.json that is backed by a KineFX (character
animation & rigging) node with `"category": "KineFX"` — the provenance classification
parallel to the existing `"category": "Cop"` / `"category": "Labs"` tags. This makes
KineFX-derived tools machine-distinguishable even though their tool names are bare
descriptive (house convention).

Unlike the Labs lane (all types share the `labs::` prefix), the KineFX lane mixes
namespaces: most types are `kinefx::…`, but the classic-capture / deform / blendshape
building blocks are bare SOP types (`capture`, `cregion`, `deform`, `bonedeform`,
`blendshapes::2.0`, …) and two solvers are Labs skinning-converters (`labs::…`). So the
match is an EXPLICIT ALLOWLIST of the exact versioned type strings the six KineFX
handlers create (the union of every wave's INTEGRATION §c list), NOT a prefix match.

The allowlist is precise: e.g. the bare type `deform` is owned only by the KineFX
`skeleton_deform` endpoint (the generic bend/twist `deform` tool maps to
`bend/twist/lattice/…`, never bare `deform`), so no non-KineFX tool is mis-tagged.

Idempotent. Never clobbers an existing "Cop" or "Labs" tag.

  python scripts/tag_kinefx_category.py            # dry-run: report what would change
  python scripts/tag_kinefx_category.py --write     # write the tags
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL_NODES = REPO / "reference" / "tool_nodes.json"

# Union of every KineFX wave's INTEGRATION §c exact versioned node-type list (W1..W6 = 94 types,
# + the animation+rigging finish-out classic/otheranim-autorig/chop-anim node union = 115; total 209).
ALLOWLIST = {
    # W1 — Skeleton authoring & joint ops (11)
    "kinefx::skeleton", "kinefx::configurejoints", "kinefx::configurejointlimits",
    "kinefx::orientjoints", "kinefx::parentjoints", "kinefx::deletejoints",
    "kinefx::groupjoints", "kinefx::skeletonblend::3.0", "kinefx::skeletonmirror",
    "kinefx::rigdoctor", "kinefx::visrig",
    # W2 — Rig pose / IK-FK (13)
    "kinefx::rigpose", "kinefx::computerigpose", "kinefx::rigmatchpose",
    "kinefx::rigmirrorpose", "kinefx::rigstashpose", "kinefx::rigcopytransforms",
    "kinefx::ikchains::2.0", "kinefx::fullbodyik", "kinefx::fbikconfiguretargets",
    "kinefx::splineik", "kinefx::reversefoot", "kinefx::stabilizejoint",
    "kinefx::posedifference",
    # W3 — Capture & skinning weights (15)
    "kinefx::jointcapturebiharmonic", "kinefx::jointcaptureproximity",
    "kinefx::pointcapturebiharmonic", "kinefx::jointcapturepaint",
    "kinefx::capturepackedgeo", "captureproximity", "capture", "bonecapturelines",
    "cregion", "capturemirror", "capturecorrect", "captureoverride",
    "labs::name_from_capture_weight::1.0", "labs::skinning_converter::3.0",
    "kinefx::dembones_skinningconverter",
    # W4 — Deformation & blendshapes (14)
    "kinefx::jointdeform", "bonedeform", "kinefx::deformskelskin",
    "posespacedeformcombine", "posespaceeditconfigure",
    "kinefx::characterblendshapesadd", "kinefx::characterblendshapescore",
    "kinefx::characterblendshapesextract", "kinefx::characterblendshapechannels",
    "kinefx::characterblendshapes", "blendshapes::2.0", "kinefx::secondarymotion",
    "kinefx::dynamicwarp", "deform",
    # W5 — MotionClip & Motion Mixer (22)
    "kinefx::motionclip", "kinefx::motionclipcreate", "kinefx::computemotionclipcreate",
    "kinefx::computemotionclipretime", "kinefx::motionclipretime",
    "kinefx::motionclipcomputevelocity", "kinefx::motionclipcycle::2.0",
    "kinefx::motionclipevaluate", "kinefx::motionclipextract",
    "kinefx::motionclipextractkeyposes", "kinefx::motionclipextractlocomotion",
    "kinefx::motionclipmerge", "kinefx::motionclipposedelete::2.0",
    "kinefx::motionclipposeinsert", "kinefx::motionclipsequence::2.0",
    "kinefx::motionclipblend::2.0", "kinefx::motionclipunpack", "kinefx::motionclipupdate",
    "kinefx::motionclipcreateclipinfo", "kinefx::motionmixerretime",
    "kinefx::motionmixersmooth", "kinefx::motionmixertransform",
    # W6 — Retarget + mocap/character FILE-I/O (19)
    "kinefx::fbxcharacterimport", "kinefx::fbxanimimport", "kinefx::fbxskinimport",
    "kinefx::gltfcharacterimport", "kinefx::gltfanimimport", "kinefx::gltfskinimport",
    "kinefx::usdcharacterimport", "kinefx::usdanimimport", "kinefx::usdskinimport",
    "kinefx::mocapimport", "kinefx::clipimport", "kinefx::characterio::2.0",
    "kinefx::retargetbipedfbx", "kinefx::rop_fbxanimoutput",
    "kinefx::rop_fbxcharacteroutput", "kinefx::rop_gltfcharacteroutput",
    "kinefx::clipexport", "kinefx::scenecharacterexport", "kinefx::retargetfbxexport",
    # ---- animation+rigging finish-out (classic_1-4 + otheranim_ar1-3 + chop_anim_1-2 node union, 115) ----
    # classic bone rigs (OBJ), KineFX auto/animation/mocap/deform rigs (OBJ), KineFX rig-constraint
    # SOPs (constraint*), KineFX channel-anim CHOPs, dembones/skinning converters. All display
    # category "KineFX". Disjoint from the Crowd/Muscle allowlists and from otheranim_1's DOP
    # dynamics-constraint types (glue/conetwist/fem/cloth/sbd conrel — NOT tagged here).
    "animation_rig_biped_arm", "animation_rig_biped_hand_4f_2s",
    "animation_rig_biped_hand_4f_3s", "animation_rig_biped_hand_5f_3s",
    "animation_rig_biped_head_and_neck", "animation_rig_biped_leg",
    "animation_rig_biped_spine_3pc", "animation_rig_biped_spine_5pc",
    "animation_rig_character_placer", "animation_rig_quadruped_back_leg",
    "animation_rig_quadruped_front_leg", "animation_rig_quadruped_head_and_neck",
    "animation_rig_quadruped_ik_spine", "animation_rig_quadruped_tail",
    "animation_rig_quadruped_toes_4f", "animation_rig_quadruped_toes_5f", "auto_rig_biped_arm",
    "auto_rig_biped_hand_4f_2s", "auto_rig_biped_hand_4f_3s", "auto_rig_biped_hand_5f_3s",
    "auto_rig_biped_head_and_neck", "auto_rig_biped_leg", "auto_rig_biped_spine_3pc",
    "auto_rig_biped_spine_5pc", "auto_rig_character_placer", "auto_rig_eye",
    "auto_rig_quadruped_back_leg", "auto_rig_quadruped_front_leg",
    "auto_rig_quadruped_head_and_neck", "auto_rig_quadruped_ik_spine",
    "auto_rig_quadruped_tail", "auto_rig_quadruped_toes_4f", "auto_rig_quadruped_toes_5f",
    "biped_auto_rig", "bone", "bonelink", "bonesolidify", "captureattribpack",
    "captureattribunpack", "capturelayerpaint::2.0", "constraintbegin", "constraintblend",
    "constraintexport", "constraintgetlocalspace", "constraintgetparentspace",
    "constraintgetworldspace", "constraintlookat", "constraintobject",
    "constraintobjectoffset", "constraintobjectpretransform", "constraintoffset",
    "constraintoffsetblend", "constraintparent", "constraintparentx", "constraintpath",
    "constraintpoints", "constraintsequence", "constraintsimpleblend", "constraintsurface",
    "constrainttransform", "deform_bone_rig_biped_arm", "deform_bone_rig_biped_hand_4f_2s",
    "deform_bone_rig_biped_hand_4f_3s", "deform_bone_rig_biped_hand_5f_3s",
    "deform_bone_rig_biped_head_and_neck", "deform_bone_rig_biped_leg",
    "deform_bone_rig_biped_spine_3pc", "deform_bone_rig_biped_spine_5pc",
    "deform_bone_rig_quadruped_back_leg", "deform_bone_rig_quadruped_front_leg",
    "deform_bone_rig_quadruped_head_and_neck", "deform_bone_rig_quadruped_ik_spine",
    "deform_bone_rig_quadruped_tail", "deform_bone_rig_quadruped_toes_4f",
    "deform_bone_rig_quadruped_toes_5f", "deform_rig_biped_arm", "deform_rig_biped_hand_4f_2s",
    "deform_rig_biped_hand_4f_3s", "deform_rig_biped_hand_5f_3s",
    "deform_rig_biped_head_and_neck", "deform_rig_biped_leg", "deform_rig_biped_spine_3pc",
    "deform_rig_biped_spine_5pc", "deform_rig_quadruped_back_leg",
    "deform_rig_quadruped_front_leg", "deform_rig_quadruped_head_and_neck",
    "deform_rig_quadruped_ik_spine", "deform_rig_quadruped_tail",
    "deform_rig_quadruped_toes_4f", "deform_rig_quadruped_toes_5f",
    "dembones_skinningconverter", "dembones_skinningconverter::1.0", "jiggle",
    "labs::dembones_skinningconverter", "labs::impostor_camera_rig", "labs::neuron_mocap",
    "labs::post_anim_deform::1.0", "labs::rokoko_mocap", "lag", "mcacclaim",
    "mocap_rig_biped_arm", "mocap_rig_biped_head_and_neck", "mocap_rig_biped_leg",
    "mocap_rig_biped_spine_3pc", "mocap_rig_biped_spine_5pc", "mocapbiped1", "mocapbiped2",
    "mocapbiped3", "pose", "posedifference", "quadruped_auto_rig_4f", "quadruped_auto_rig_5f",
    "spring", "toon_character", "toon_character_deform_rig",
}


def is_kinefx(nodes):
    return any(str(n) in ALLOWLIST for n in nodes)


def main():
    write = "--write" in sys.argv
    data = json.loads(TOOL_NODES.read_text(encoding="utf-8"))
    tools = data["tools"]
    to_tag = []
    for name, entry in tools.items():
        if not isinstance(entry, dict):
            continue
        nodes = entry.get("nodes", [])
        cat = entry.get("category")
        if is_kinefx(nodes) and cat not in ("KineFX", "Labs", "Cop"):
            to_tag.append(name)
    print("kinefx-backed tools needing a KineFX tag:", len(to_tag))
    print("  ", sorted(to_tag))
    already = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "KineFX")
    print("already tagged KineFX:", already)
    if len(ALLOWLIST) != 209:
        print("WARNING: allowlist has %d types (expected 209)" % len(ALLOWLIST))
    if not write:
        print("\nDRY-RUN. Re-run with --write to apply.")
        return
    for name in to_tag:
        tools[name]["category"] = "KineFX"
    TOOL_NODES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "KineFX")
    print("\nWROTE %s  (+%d tagged; total KineFX=%d)" % (TOOL_NODES, len(to_tag), total))


if __name__ == "__main__":
    main()
