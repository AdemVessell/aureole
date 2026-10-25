"""Blender CLI helper: convert the centimetre OBJ to a metre-authored FBX.

The OBJ is intentionally centimetres for Unreal's common 1 UU = 1 cm import
path.  FBX is authored as metres (the 300 cm diameter becomes 3.0 Blender
units), with Z-up coordinates retained for Unreal import.
"""

import argparse
import sys
import bpy


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--obj", required=True)
    p.add_argument("--fbx", required=True)
    # Blender keeps its own flags in sys.argv; user arguments follow `--`.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=args.obj, forward_axis="NEGATIVE_Z", up_axis="Y")
    else:
        bpy.ops.import_scene.obj(filepath=args.obj, axis_forward="-Z", axis_up="Y")
    imported = list(bpy.context.selected_objects)
    if not imported:
        raise RuntimeError("OBJ import produced no object")
    # The OBJ's coordinates are centimetres; convert geometry to metres for FBX.
    for obj in imported:
        obj.name = "GyroidLattice_300cm"
        obj.scale = (0.01, 0.01, 0.01)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if obj.type == "MESH":
            for poly in obj.data.polygons:
                poly.use_smooth = True
            obj.data.name = "GyroidLattice_Mesh"

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    bpy.ops.wm.save_as_mainfile(filepath=args.fbx.removesuffix(".fbx") + ".blend")
    bpy.ops.export_scene.fbx(
        filepath=args.fbx,
        use_selection=True,
        object_types={"MESH"},
        apply_unit_scale=True,
        global_scale=1.0,
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y",
        axis_up="Z",
        use_space_transform=True,
        bake_space_transform=False,
        mesh_smooth_type="OFF",
        add_leaf_bones=False,
        path_mode="AUTO",
        embed_textures=False,
    )
    print("EXPORTED", args.fbx)


if __name__ == "__main__":
    main()
