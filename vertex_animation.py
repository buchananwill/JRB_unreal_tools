# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>


bl_info = {
    "name": "Vertex Animation",
    "author": "Joshua Bogart",
    "version": (1, 0),
    "blender": (4, 0, 1),
    "location": "View3D > Sidebar > Unreal Tools Tab",
    "description": "A tool for storing per frame vertex data for use in a vertex shader.",
    "warning": "",
    "doc_url": "",
    "category": "Unreal Tools",
}


import bpy
import bmesh


def get_per_frame_mesh_data(context, data, objects):
    """Return a list of combined mesh data per frame"""
    meshes = []
    for i in frame_range(context.scene):
        context.scene.frame_set(i)
        depsgraph = context.evaluated_depsgraph_get()
        bm = bmesh.new()
        for ob in objects:
            eval_object = ob.evaluated_get(depsgraph)
            mesh = data.meshes.new_from_object(eval_object)
            mesh.transform(ob.matrix_world)
            bm.from_mesh(mesh)
            data.meshes.remove(mesh)
        mesh = data.meshes.new("mesh")
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        meshes.append(mesh)
    return meshes


def create_export_mesh_object(context, data, me):
    """Return a mesh object with correct UVs"""
    while len(me.uv_layers) < 2:
        me.uv_layers.new()
    uv_layer = me.uv_layers[1]
    uv_layer.name = "vertex_anim"
    for loop in me.loops:
        uv_layer.data[loop.index].uv = (
            (loop.vertex_index + 0.5)/len(me.vertices), 128/255
        )
    ob = data.objects.new("export_mesh", me)
    context.scene.collection.objects.link(ob)
    return ob


def get_vertex_data(data, meshes):
    """Return lists of vertex offsets and normals from a list of mesh data"""
    original = meshes[0].vertices
    offsets = []
    normals = []
    for mesh in reversed(meshes):
        for vertex in mesh.vertices:
            offset = vertex.co - original[vertex.index].co
            x, y, z = offset
            offsets.extend((x, y, z, 1.0))
            x, y, z = vertex.normal
            normals.extend(
                (normalize_signed_to_zero_to_one_space(x),
                 normalize_signed_to_zero_to_one_space(y),
                normalize_signed_to_zero_to_one_space(z),
                 1.0)
            )
        if not mesh.users:
            data.meshes.remove(mesh)
    return offsets, normals


def normalize_signed_to_zero_to_one_space(x):
    return (x + 1) * 0.5


def frame_range(scene):
    """Return a range object with scene's frame start, end, and step"""
    return range(scene.frame_start, scene.frame_end+1, scene.frame_step)


def bake_vertex_data(data, offsets, normals, size):
    """Stores vertex offsets and normals in separate image textures"""
    width, height = size

    lowest_negative_offset = 0.0
    highest_positive_offset = 0.0
    for float_index in range(len(offsets)):
        if float_index >= len(offsets) or (float_index +1) % 4 == 0:
            continue
        lowest_negative_offset = min(offsets[float_index], lowest_negative_offset)
        highest_positive_offset = max(offsets[float_index], highest_positive_offset)

    lowest_negative_offset *= -1
    neg_max_plus_pos_max = highest_positive_offset + lowest_negative_offset
    neg_max_plus_pos_max = 1 if neg_max_plus_pos_max == 0 else neg_max_plus_pos_max

    for float_index in range(len(offsets)):
        if float_index >= len(offsets) or (float_index +1) % 4 == 0:
            continue
        offsets[float_index] += lowest_negative_offset
        offsets[float_index] /= neg_max_plus_pos_max

    offset_texture = data.images.new(
        name=f"offsets_neg_max_{lowest_negative_offset}_pos_max_{highest_positive_offset}" ,
        width=width,
        height=height,
        alpha=True,
        float_buffer=True
    )
    normal_texture = data.images.new(
        name="normals",
        width=width,
        height=height,
        alpha=True
    )

    offset_texture.pixels = offsets
    normal_texture.pixels = normals
    return [offset_texture, normal_texture]

import bpy
import os
import re


def save_image_exr(image: bpy.types.Image, halfdepth = False):
    """
    Save a Blender Image as OpenEXR (RGBA, Float Full depth, Codec None, Non-Color)
    into the folder containing the current .blend file, resolving name conflicts
    by adding or incrementing a _N suffix.

    :param image: The bpy.types.Image to save.
    """
    # Ensure the .blend is saved
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError("Please save your .blend file before calling save_image_exr().")
    directory = os.path.dirname(blend_path)

    # Base name (no extension) from image.name
    base_name = os.path.splitext(image.name)[0]
    ext = ".exr"

    # Helper to compute a unique filename
    def unique_filepath(name):
        full = os.path.join(directory, name + ext)
        if not os.path.exists(full):
            return name, full

        # If already ends with _<num>, bump it; otherwise start at 1
        m = re.match(r'^(.*)_(\d+)$', name)
        if m:
            root, idx = m.group(1), int(m.group(2)) + 1
        else:
            root, idx = name, 1

        return unique_filepath(f"{root}_{idx}")

    # Determine final name + path
    final_name, filepath = unique_filepath(base_name)

    # Create a context override so the operator knows which image to save
    image.file_format = 'OPEN_EXR'
    # image.use_half_precision = halfdepth
    # image.colorspace_settings.name = 'NONE'
    # image.colorspace_settings.is_data = True
    image.filepath = filepath
    image.save()

    print(f"Image '{image.name}' saved as '{os.path.basename(filepath)}'")

# Example usage:
# img = bpy.data.images['Render Result']
# save_image_exr(img)


class OBJECT_OT_ProcessAnimMeshes(bpy.types.Operator):
    """Store combined per frame vertex offsets and normals for all
    selected mesh objects into separate image textures"""
    bl_idname = "object.process_anim_meshes"
    bl_label = "Process Anim Meshes"

    @property
    def allowed_modifiers(self):
        return [
            'ARMATURE', 'CAST', 'CURVE', 'DISPLACE', 'HOOK',
            'LAPLACIANDEFORM', 'LATTICE', 'MESH_DEFORM',
            'SHRINKWRAP', 'SIMPLE_DEFORM', 'SMOOTH',
            'CORRECTIVE_SMOOTH', 'LAPLACIANSMOOTH',
            'SURFACE_DEFORM', 'WARP', 'WAVE',
        ]

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob and ob.type == 'MESH' and ob.mode == 'OBJECT'

    def execute(self, context):
        units = context.scene.unit_settings
        data = bpy.data
        objects = [ob for ob in context.selected_objects if ob.type == 'MESH']
        vertex_count = sum([len(ob.data.vertices) for ob in objects])
        frame_count = len(frame_range(context.scene))
        for ob in objects:
            for mod in ob.modifiers:
                if mod.type not in self.allowed_modifiers:
                    self.report(
                        {'ERROR'},
                        f"Objects with {mod.type.title()} modifiers are not allowed!"
                    )
                    return {'CANCELLED'}
        if units.system != 'METRIC' or round(units.scale_length, 2) != 0.01:
            self.report(
                {'ERROR'},
                "Scene Unit must be Metric with a Unit Scale of 0.01!"
            )
            return {'CANCELLED'}        
        if vertex_count > 8192:
            self.report(
                {'ERROR'},
                f"Vertex count of {vertex_count :,}, exceeds limit of 8,192!"
            )
            return {'CANCELLED'}
        if frame_count > 8192:
            self.report(
                {'ERROR'},
                f"Frame count of {frame_count :,}, exceeds limit of 8,192!"
            )
            return {'CANCELLED'}
        meshes = get_per_frame_mesh_data(context, data, objects)
        export_mesh_data = meshes[0].copy()
        create_export_mesh_object(context, data, export_mesh_data)
        offsets, normals = get_vertex_data(data, meshes)
        texture_size = vertex_count, frame_count
        offsets_texture, normals_texture = bake_vertex_data(data, offsets, normals, texture_size)
        save_image_exr(offsets_texture)
        save_image_exr(normals_texture)

        return {'FINISHED'}


class VIEW3D_PT_VertexAnimation(bpy.types.Panel):
    """Creates a Panel in 3D Viewport"""
    bl_label = "Vertex Animation"
    bl_idname = "VIEW3D_PT_vertex_animation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Unreal Tools"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        scene = context.scene
        col = layout.column(align=True)
        col.prop(scene, "frame_start", text="Frame Start")
        col.prop(scene, "frame_end", text="End")
        col.prop(scene, "frame_step", text="Step")
        row = layout.row()
        row.operator("object.process_anim_meshes")


def register():
    bpy.utils.register_class(OBJECT_OT_ProcessAnimMeshes)
    bpy.utils.register_class(VIEW3D_PT_VertexAnimation)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_ProcessAnimMeshes)
    bpy.utils.unregister_class(VIEW3D_PT_VertexAnimation)


if __name__ == "__main__":
    register()
