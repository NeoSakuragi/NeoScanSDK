#!/usr/bin/env python3
"""Render the PCB 3D model using Blender in headless mode."""

import bpy
import sys
import math

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import VRML (Blender handles this well)
vrml_path = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production/neocart_3d.wrl"
step_path = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production/neocart_3d.step"

# Try STEP first (better geometry)
try:
    bpy.ops.wm.stl_import(filepath=step_path)
except:
    pass

# Import VRML
try:
    bpy.ops.import_scene.x3d(filepath=vrml_path)
    print("Loaded VRML")
except:
    # Try GLB
    glb_path = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production/neocart_3d.glb"
    bpy.ops.import_scene.gltf(filepath=glb_path)
    print("Loaded GLB")

# Select all imported objects and frame them
bpy.ops.object.select_all(action='SELECT')

# Get bounding box of all objects
min_x = min_y = min_z = float('inf')
max_x = max_y = max_z = float('-inf')
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        for v in obj.bound_box:
            world_v = obj.matrix_world @ bpy.app.driver_namespace.get('Vector', __import__('mathutils').Vector)(v)
            min_x = min(min_x, world_v.x)
            min_y = min(min_y, world_v.y)
            min_z = min(min_z, world_v.z)
            max_x = max(max_x, world_v.x)
            max_y = max(max_y, world_v.y)
            max_z = max(max_z, world_v.z)

cx = (min_x + max_x) / 2
cy = (min_y + max_y) / 2
cz = (min_z + max_z) / 2
size = max(max_x - min_x, max_y - min_y, max_z - min_z)

# Camera — isometric-ish angle looking down at the board
cam_data = bpy.data.cameras.new("Camera")
cam_data.type = 'PERSP'
cam_data.lens = 50
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam

dist = size * 1.8
cam.location = (cx + dist * 0.6, cy - dist * 0.6, cz + dist * 0.8)

# Point camera at center
direction = bpy.app.driver_namespace.get('Vector', __import__('mathutils').Vector)((cx - cam.location.x, cy - cam.location.y, cz - cam.location.z))
rot_quat = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot_quat.to_euler()

# Lighting
light_data = bpy.data.lights.new("Sun", type='SUN')
light_data.energy = 3
light = bpy.data.objects.new("Sun", light_data)
light.location = (cx, cy, cz + size * 3)
bpy.context.scene.collection.objects.link(light)

# Fill light
light2_data = bpy.data.lights.new("Fill", type='AREA')
light2_data.energy = 100
light2_data.size = size
light2 = bpy.data.objects.new("Fill", light2_data)
light2.location = (cx - size, cy + size, cz + size * 0.5)
bpy.context.scene.collection.objects.link(light2)

# Background
bpy.context.scene.world = bpy.data.worlds.new("World")
bpy.context.scene.world.use_nodes = True
bg = bpy.context.scene.world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.15, 0.15, 0.18, 1)

# Render settings
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.film_transparent = False

# Output
out_path = "/home/bruno/CLProjects/NeoGeo/hardware/neocart/production/neocart_render.png"
bpy.context.scene.render.filepath = out_path

bpy.ops.render.render(write_still=True)
print(f"Rendered to {out_path}")
