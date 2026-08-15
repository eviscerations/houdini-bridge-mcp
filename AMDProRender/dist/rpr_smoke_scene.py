#!/usr/bin/env hython
"""
rpr_smoke_scene.py — build a minimal lit USD scene for the ProRender render-proof.

Run with Houdini's hython (has pxr USD 25):
    hython rpr_smoke_scene.py <out.usd>

Produces a stage with: a red sphere on a grey ground, a dome light, a camera aimed
at the sphere, and a UsdRender RenderSettings/Product/Var (640x360, color AOV) with
the stage's renderSettingsPrimPath metadata set so husk auto-discovers it.
No renderer is baked in — husk selects HdRprPlugin at the command line.
"""
import sys
from pxr import Usd, UsdGeom, UsdLux, UsdRender, Gf, Sdf

out = sys.argv[1] if len(sys.argv) > 1 else "rpr_smoke.usd"

stage = Usd.Stage.CreateNew(out)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

UsdGeom.Xform.Define(stage, "/World")

# --- red sphere at origin, radius 1 ---
sph = UsdGeom.Sphere.Define(stage, "/World/sphere")
sph.CreateRadiusAttr(1.0)
sph.CreateDisplayColorAttr([Gf.Vec3f(0.7, 0.08, 0.08)])

# --- grey ground plane (a wide, thin box-ish mesh via a large sphere is ugly; use a mesh grid) ---
ground = UsdGeom.Mesh.Define(stage, "/World/ground")
ground.CreatePointsAttr([Gf.Vec3f(-10, -1, -10), Gf.Vec3f(10, -1, -10),
                         Gf.Vec3f(10, -1, 10),   Gf.Vec3f(-10, -1, 10)])
ground.CreateFaceVertexCountsAttr([4])
ground.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
ground.CreateDisplayColorAttr([Gf.Vec3f(0.35, 0.35, 0.38)])

# --- dome light (even ambient illumination, no texture needed) ---
dome = UsdLux.DomeLight.Define(stage, "/World/dome")
dome.CreateIntensityAttr(2.0)

# --- key distant light for a highlight ---
sun = UsdLux.DistantLight.Define(stage, "/World/sun")
sun.CreateIntensityAttr(3.0)
UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))

# --- camera, backed off on +Z looking toward origin ---
cam = UsdGeom.Camera.Define(stage, "/World/cam")
cx = UsdGeom.Xformable(cam)
cx.AddTranslateOp().Set(Gf.Vec3d(0, 1.2, 6.0))
cx.AddRotateXYZOp().Set(Gf.Vec3f(-8, 0, 0))
cam.CreateFocalLengthAttr(35.0)

# --- render settings / product / var ---
rs = UsdRender.Settings.Define(stage, "/Render/rendersettings")
rs.CreateResolutionAttr(Gf.Vec2i(640, 360))
rs.CreateCameraRel().SetTargets([Sdf.Path("/World/cam")])

var = UsdRender.Var.Define(stage, "/Render/rendersettings/color")
var.CreateSourceNameAttr("color")
var.CreateDataTypeAttr("color3f")

prod = UsdRender.Product.Define(stage, "/Render/rendersettings/product")
prod.CreateProductNameAttr("rpr_smoke.exr")     # husk -o overrides this if passed
prod.CreateCameraRel().SetTargets([Sdf.Path("/World/cam")])
prod.CreateOrderedVarsRel().SetTargets([var.GetPath()])

rs.CreateProductsRel().SetTargets([prod.GetPath()])

# make husk auto-discover the settings prim
stage.GetRootLayer().pseudoRoot.SetCustomDataByKey("renderSettingsPrimPath", "/Render/rendersettings")
stage.SetMetadata("renderSettingsPrimPath", "/Render/rendersettings")

stage.GetRootLayer().Save()
print("wrote %s (renderSettingsPrimPath=/Render/rendersettings, cam=/World/cam, 640x360)" % out)
