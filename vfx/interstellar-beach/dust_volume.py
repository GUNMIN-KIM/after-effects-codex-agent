# Volumetric haboob (dust wall) rendered with Cycles, camera matched to the plate (same as ships_flyby.py).
# Wall distance per output frame follows comp.storm_D(k). Writes RGBA float16 .npy per frame (premultiplied).
#   python dust_volume.py -- <k_first> <k_last> [res_scale]
import bpy, math, os, sys
import numpy as np
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
K0, K1 = int(ARGS[0]), int(ARGS[1]); SCALE = float(ARGS[2]) if len(ARGS) > 2 else 0.5
STEP = int(ARGS[3]) if len(ARGS) > 3 else 1
OUT = os.path.join(SP, 'work', 'dust'); os.makedirs(OUT, exist_ok=True)

def storm_D(k):
    xs = [14, 45, 72, 90, 104, 112, 118, 124]; ys = [7000, 2200, 700, 220, 24, 2.4, 0.0, -6]
    return float(np.interp(k, xs, ys))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; c = sc.cycles; c.device = 'CPU'
c.samples = int(os.environ.get('DUST_SPP', '12')); c.use_denoising = True
c.volume_step_rate = float(os.environ.get('DUST_STEP', '3.0')); c.volume_max_steps = 160
c.max_bounces = 3; c.volume_bounces = 1; c.diffuse_bounces = 0; c.glossy_bounces = 0; c.transparent_max_bounces = 2
sc.render.resolution_x, sc.render.resolution_y = int(1080 * SCALE), int(1920 * SCALE)
sc.render.film_transparent = True
sc.view_settings.view_transform = 'Standard'

cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 26.3; cam_d.sensor_fit = 'VERTICAL'; cam_d.sensor_height = 36.0; cam_d.clip_end = 20000
cam = bpy.data.objects.new('cam', cam_d); sc.collection.objects.link(cam)
cam.location = (0, 0, 1.28); cam.rotation_euler = (math.radians(90), math.radians(-1.5), 0); sc.camera = cam

world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
bgn = world.node_tree.nodes['Background']; bgn.inputs[0].default_value = (0.50, 0.52, 0.58, 1); bgn.inputs[1].default_value = 0.45
from mathutils import Vector
sun_d = bpy.data.lights.new('sun', 'SUN'); sun_d.energy = 4.2; sun_d.color = (1.0, 0.93, 0.82); sun_d.angle = math.radians(1.0)
sun = bpy.data.objects.new('sun', sun_d); sc.collection.objects.link(sun)
sun.rotation_mode = 'QUATERNION'; sun.rotation_quaternion = (-Vector((-0.55, -0.62, 0.56)).normalized()).to_track_quat('-Z', 'Y')

# volume domain: local y = 0 is the wall front, extends 900 m behind it
me = bpy.data.meshes.new('dom')
x0, x1, y0, y1, z0, z1 = -3200, 3200, -160, 900, -2, 470
v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
me.from_pydata(v, [], f); me.update()
dom = bpy.data.objects.new('dust', me); sc.collection.objects.link(dom)

mat = bpy.data.materials.new('dust'); mat.use_nodes = True
nt = mat.node_tree; N = nt.nodes; L = nt.links
N.remove(N['Principled BSDF'])
out = N['Material Output']
vol = N.new('ShaderNodeVolumePrincipled')
vol.inputs['Color'].default_value = (0.72, 0.50, 0.31, 1)
vol.inputs['Anisotropy'].default_value = 0.0
vol.inputs['Absorption Color'].default_value = (0.9, 0.8, 0.68, 1)
L.new(vol.outputs[0], out.inputs['Volume'])
def node(t, **kw):
    n = N.new(t)
    for k_, v_ in kw.items(): setattr(n, k_, v_)
    return n
def feed(s, x):
    if isinstance(x, (int, float)): s.default_value = x
    else: L.new(x, s)
def math_(op, a, b=None, clamp=False):
    n = node('ShaderNodeMath', operation=op, use_clamp=clamp); feed(n.inputs[0], a)
    if b is not None: feed(n.inputs[1], b)
    return n.outputs[0]
def ss(x, a, b):
    n = node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True); feed(n.inputs['Value'], x)
    feed(n.inputs['From Min'], a); feed(n.inputs['From Max'], b); return n.outputs['Result']
tc = node('ShaderNodeTexCoord'); sep = node('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
x, y, z = sep.outputs[0], sep.outputs[1], sep.outputs[2]
wv = node('ShaderNodeValue'); W_ = wv.outputs[0]
# rolling: the front churns upward, so sample the noise lower as time goes on
roll = node('ShaderNodeCombineXYZ'); feed(roll.inputs[0], 0.0); feed(roll.inputs[1], 0.0); feed(roll.inputs[2], math_('MULTIPLY', W_, -55.0))
pos = node('ShaderNodeVectorMath', operation='ADD'); L.new(tc.outputs['Object'], pos.inputs[0]); L.new(roll.outputs[0], pos.inputs[1])
nA = node('ShaderNodeTexNoise', noise_dimensions='4D'); L.new(pos.outputs[0], nA.inputs['Vector']); L.new(W_, nA.inputs['W'])
nA.inputs['Scale'].default_value = 0.0045; nA.inputs['Detail'].default_value = 14; nA.inputs['Roughness'].default_value = 0.62; nA.inputs['Distortion'].default_value = 0.35
nB = node('ShaderNodeTexNoise', noise_dimensions='2D')
cx = node('ShaderNodeCombineXYZ'); feed(cx.inputs[0], x); feed(cx.inputs[1], math_('MULTIPLY', W_, 3.0))
L.new(cx.outputs[0], nB.inputs['Vector']); nB.inputs['Scale'].default_value = 0.0018; nB.inputs['Detail'].default_value = 4
nC = node('ShaderNodeTexNoise', noise_dimensions='4D'); L.new(pos.outputs[0], nC.inputs['Vector']); L.new(W_, nC.inputs['W'])
nC.inputs['Scale'].default_value = 0.016; nC.inputs['Detail'].default_value = 8; nC.inputs['Roughness'].default_value = 0.6
A = math_('ADD', nA.outputs['Fac'], math_('MULTIPLY', math_('SUBTRACT', nC.outputs['Fac'], 0.5), 0.18)); B = nB.outputs['Fac']
top = math_('ADD', 170.0, math_('MULTIPLY', B, 260.0))
jit = math_('MULTIPLY', math_('SUBTRACT', A, 0.5), 160.0)
top_mask = math_('SUBTRACT', 1.0, ss(math_('ADD', z, jit), math_('SUBTRACT', top, 70.0), math_('ADD', top, 30.0)))
front = ss(math_('ADD', y, math_('MULTIPLY', math_('SUBTRACT', A, 0.5), 220.0)), -40.0, 70.0)
lobes = ss(A, 0.47, 0.53)
base = math_('ADD', 1.0, math_('MULTIPLY', math_('SUBTRACT', 1.0, ss(z, 0.0, 70.0)), 1.5))
dens = math_('MULTIPLY', math_('MULTIPLY', math_('MULTIPLY', lobes, top_mask), front), base)
dens = math_('ADD', math_('MULTIPLY', dens, float(os.environ.get('DUST_DENS', '0.12'))), math_('MULTIPLY', math_('MULTIPLY', top_mask, front), 0.0015))
L.new(dens, vol.inputs['Density'])
dom.data.materials.append(mat)

for k in range(K0, K1 + 1, STEP):
    D = storm_D(k)
    dom.location = (0.0, D, 0.0)
    wv.outputs[0].default_value = k * 0.012
    sc.render.filepath = os.path.join(OUT, 'tmp_%04d.exr' % k)
    sc.render.image_settings.file_format = 'OPEN_EXR'; sc.render.image_settings.color_depth = '16'; sc.render.image_settings.exr_codec = 'ZIP'
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath); w_, h_ = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h_, w_, 4)[::-1]
    np.save(os.path.join(OUT, 'd_%04d.npy' % k), a.astype(np.float16)); bpy.data.images.remove(img); os.remove(sc.render.filepath)
    print('dust frame', k, 'D=%.1f' % D, flush=True)
