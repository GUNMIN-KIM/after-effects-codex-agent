# Twin-ship flyby over the beach plate: camera matched to the iPhone plate (26 mm eq, level horizon, -1.5 deg roll).
# Ships pass overhead from behind the camera and streak away toward the black hole. Transparent RGBA + engine screen positions.
import bpy, math, os, sys, json
from mathutils import Vector, Quaternion
SP = os.path.dirname(os.path.abspath(__file__))
ASSETS = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else os.path.join(SP, '..', 'assets')
OUT = os.path.join(SP, 'work', 'ships'); os.makedirs(OUT, exist_ok=True)
FR = 48; SAMPLES = 24
RES = (1080, 1920)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = RES; sc.render.film_transparent = True
sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.6
sc.render.fps = 30; sc.frame_start, sc.frame_end = 1, FR
sc.view_settings.view_transform = 'Standard'          # linear-ish output; the comp does the grading
sc.render.image_settings.file_format = 'OPEN_EXR'; sc.render.image_settings.color_depth = '16'; sc.render.image_settings.exr_codec = 'DWAA'

cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 26.3; cam_d.sensor_fit = 'VERTICAL'; cam_d.sensor_height = 36.0; cam_d.clip_end = 5000
cam = bpy.data.objects.new('cam', cam_d); bpy.context.collection.objects.link(cam)
cam.location = (0, 0, 1.28); cam.rotation_euler = (math.radians(90), math.radians(-1.5), 0)
sc.camera = cam

world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
bg = world.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.02, 0.025, 0.05, 1); bg.inputs[1].default_value = 0.6

def sun(frm, color, energy, angle=2):
    d = bpy.data.lights.new('sun', 'SUN'); d.color = color; d.energy = energy; d.angle = math.radians(angle)
    o = bpy.data.objects.new('sun', d); bpy.context.collection.objects.link(o)
    o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = (-Vector(frm).normalized()).to_track_quat('-Z', 'Y')
sun((0.05, 0.94, 0.34), (1.0, 0.70, 0.40), 7.0)      # golden key from the black hole, ahead and ~20 deg up
sun((-0.3, -0.8, 0.5), (0.55, 0.70, 1.0), 2.0, 20)   # cool sky fill from behind the camera
sun((0.0, 0.2, -1.0), (1.0, 0.82, 0.62), 1.6, 40)    # warm sand bounce from below

ACC = {'castor': (0.027, 0.80, 1.0), 'pollux': (1.0, 0.05, 0.62)}
def load_ship(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ASSETS, 'ship.glb'))
    objs = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None); bpy.context.collection.objects.link(root)
    for o in objs:
        if o.parent is None: o.parent = root
        if o.type != 'MESH': continue
        for i, m in enumerate(o.data.materials):
            m = m.copy(); o.data.materials[i] = m
            nt = m.node_tree; P = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
            if m.name.startswith('ShipHull'):
                if name == 'pollux':
                    for n in nt.nodes:
                        if n.type == 'TEX_IMAGE' and n.image and 'base' in n.image.name.lower():
                            n.image = bpy.data.images.load(os.path.join(ASSETS, 'ship_base_pollux.webp'))
                src = P.inputs['Emission Color'].links[0].from_socket if P.inputs['Emission Color'].links else None
                if src:
                    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
                    s = {x.identifier: x for x in mix.inputs}; s['Factor_Float'].default_value = 1
                    nt.links.new(src, s['A_Color']); s['B_Color'].default_value = (*ACC[name], 1)
                    nt.links.new({x.identifier: x for x in mix.outputs}['Result_Color'], P.inputs['Emission Color'])
                P.inputs['Emission Strength'].default_value = 6.0
                P.inputs['Coat Weight'].default_value = 1.0; P.inputs['Coat Roughness'].default_value = 0.05
            elif 'Engine' in m.name:
                P.inputs['Emission Color'].default_value = (*[c * 0.6 + 0.4 for c in ACC[name]], 1); P.inputs['Emission Strength'].default_value = 60
            elif 'Nav' in m.name:
                P.inputs['Emission Strength'].default_value = 40
            elif 'Glass' in m.name:
                P.inputs['Roughness'].default_value = 0.02; P.inputs['Coat Weight'].default_value = 1.0
    return root

ships = {'castor': load_ship('castor'), 'pollux': load_ship('pollux')}
# glTF import gives Y-up -> Blender Z-up already; ship nose points +Y in Blender space.

def path(t, pts):
    # Catmull-Rom through pts, t in [0,1]
    n = len(pts) - 1; s = min(t * n, n - 1e-6); i = int(s); u = s - i
    p0 = pts[max(i - 1, 0)]; p1 = pts[i]; p2 = pts[i + 1]; p3 = pts[min(i + 2, n)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)

P_C = [Vector(v) for v in [(-9, -7, 7.0), (-3.5, 4, 5.6), (0.5, 19, 6.4), (4, 70, 16), (7, 240, 74)]]
P_P = [Vector(v) for v in [(-6, -10, 6.2), (-0.8, 1.5, 4.9), (3.2, 16.5, 5.6), (8.5, 68, 15), (13, 236, 72)]]
def ease(x): return x

eng = {}
for f in range(1, FR + 1):
    sc.frame_set(f)
for name, root in ships.items():
    pts = P_C if name == 'castor' else P_P
    delay = 0.0 if name == 'castor' else 0.06
    for f in range(0, FR + 2):
        t = min(max((f / FR - delay) / (1 - delay), 0), 1)
        tt = ease(t)
        p = path(tt, pts); p2 = path(min(tt + 0.01, 1), pts)
        v = (p2 - p); v = v.normalized() if v.length > 1e-6 else Vector((0, 1, 0))
        q = Vector((0, 1, 0)).rotation_difference(v)
        bank = Quaternion(v, math.radians(-28 + 40 * t) * (1 if name == 'castor' else 0.8))
        root.location = p; root.rotation_mode = 'QUATERNION'; root.rotation_quaternion = bank @ q
        s = 1.0
        root.scale = (s, s, s)
        root.keyframe_insert('location', frame=f); root.keyframe_insert('rotation_quaternion', frame=f)
from bpy_extras.object_utils import world_to_camera_view
for f in range(1, FR + 1):
    sc.frame_set(f)
    for name, root in ships.items():
        m = root.matrix_world
        e = []
        for sx in (-0.74, 0.74):
            co = world_to_camera_view(sc, cam, m @ Vector((sx, -1.72, -0.01)))
            e.append([co.x * RES[0], (1 - co.y) * RES[1], co.z])
        eng.setdefault(name, []).append(e)
json.dump(eng, open(os.path.join(OUT, 'engines.json'), 'w'))
if os.environ.get('PREVIEW'):
    sc.render.resolution_percentage = 50; sc.cycles.samples = 12; sc.render.image_settings.file_format = 'PNG'; sc.view_settings.view_transform = 'AgX'
    for f in map(int, os.environ['PREVIEW'].split(',')):
        sc.frame_set(f); sc.render.filepath = os.path.join(SP, '..', 'shots', 'ship_f%02d.png' % f); bpy.ops.render.render(write_still=True)
else:
    sc.render.filepath = os.path.join(OUT, 's_')
    bpy.ops.render.render(animation=True)
print('done')
