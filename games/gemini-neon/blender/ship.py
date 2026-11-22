"""Gemini Neon hero ship.

Builds a SubD hard-surface racer (lofted fuselage, engine pods with intakes and nozzles,
wings, fins, canards, vents, hover pads), gives it procedural PBR materials
(pearl/graphite paint, panel lines, decals, burnt titanium, carbon fibre),
bakes everything to one UV set and writes a game-ready GLB.

    pip install bpy pillow
    python ship.py -- --out ../assets --tex 2048 --preview ship.png --fonts <dir with Unbounded-ExtraBold.ttf, Rajdhani-Bold.ttf>

Blender axes: X right, Y forward (nose), Z up. The glTF export converts to Y-up, nose -Z.
"""
import bpy, bmesh, math, os, sys
import numpy as np

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(arg('--out', os.path.join(HERE, '..', 'assets')))
TEX = int(arg('--tex', '2048'))
SUBD = int(arg('--subd', '2'))
PREVIEW = arg('--preview')
FONTS = arg('--fonts', HERE)
SAMPLES = int(arg('--samples', '96'))
os.makedirs(OUT, exist_ok=True)
WORK = os.path.join(OUT, '_bake')
os.makedirs(WORK, exist_ok=True)

ACCENTS = {'castor': (0.027, 0.80, 1.0), 'pollux': (1.0, 0.05, 0.62)}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'

# ---------------------------------------------------------------- geometry helpers
def link(ob):
    bpy.context.collection.objects.link(ob)
    return ob

def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return link(bpy.data.objects.new(name, me))

def recalc(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()

def loft(name, sections, ringfn, caps=(True, True)):
    verts, faces, n = [], [], 0
    for y, params, zoff, xoff in sections:
        pts = ringfn(*params); n = len(pts)
        verts += [(x + xoff, y, z + zoff) for x, z in pts]
    S = len(sections)
    for i in range(S - 1):
        for j in range(n):
            faces.append((i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j))
    if caps[0]: faces.append(tuple(reversed(range(n))))
    if caps[1]: faces.append(tuple(range((S - 1) * n, S * n)))
    ob = mesh_from(name, verts, faces)
    recalc(ob)
    return ob, n

def crease_long(ob, n, ring_ids, value):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    layer = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        if a // n != b // n and a % n == b % n and a % n in ring_ids:
            e[layer] = value
    bm.to_mesh(ob.data); bm.free()

def subsurf(ob, levels=SUBD):
    m = ob.modifiers.new('subd', 'SUBSURF'); m.levels = levels; m.render_levels = levels
    return ob

def bevel(ob, width=0.008, segs=3, angle=35):
    m = ob.modifiers.new('bevel', 'BEVEL'); m.width = width; m.segments = segs
    m.limit_method = 'ANGLE'; m.angle_limit = math.radians(angle); m.harden_normals = False
    return ob

def smooth(ob):
    for p in ob.data.polygons: p.use_smooth = True
    return ob

def prism(name, pts, axis, center, thickness):
    """Extrude a 2D outline. axis 'Z': pts are (x,y); 'X': pts are (y,z)."""
    h = thickness / 2
    if axis == 'Z':
        bot = [(x, y, center - h) for x, y in pts]; top = [(x, y, center + h) for x, y in pts]
    else:
        bot = [(center - h, y, z) for y, z in pts]; top = [(center + h, y, z) for y, z in pts]
    n = len(pts)
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    ob = mesh_from(name, bot + top, faces); recalc(ob)
    return ob

def cylinder(name, r, depth, loc, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, rotation=rot, vertices=verts)
    ob = bpy.context.object; ob.name = name
    return ob

def apply_mods(ob):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.select_set(False)
    return ob

def join(objs, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.object; ob.name = name
    return ob

def faces_at(bm, axis, value, eps=1e-4):
    k = 'xyz'.index(axis)
    return [f for f in bm.faces if all(abs(v.co[k] - value) < eps for v in f.verts)]

def recess(ob, axis, value, inset, depth, scale=0.9):
    """Inset a cap face and push it into the body (intakes, nozzles)."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    caps = faces_at(bm, axis, value)
    bmesh.ops.inset_region(bm, faces=caps, thickness=inset, depth=0)
    ret = bmesh.ops.extrude_face_region(bm, geom=caps)
    nv = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    vec = [0, 0, 0]; vec['xyz'.index(axis)] = depth
    bmesh.ops.translate(bm, verts=nv, vec=vec)
    c = sum((v.co for v in nv), nv[0].co * 0) / len(nv)
    bmesh.ops.scale(bm, verts=nv, vec=(scale, 1 if axis == 'y' else scale, scale), space=__import__('mathutils').Matrix.Translation(-c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()

# ---------------------------------------------------------------- shape
def ring_fuse(w, ht, hb):
    R = [(0, ht), (0.5 * w, 0.95 * ht), (0.88 * w, 0.58 * ht), (w, 0.08 * ht), (w, -0.14 * hb),
         (0.78 * w, -0.8 * hb), (0.4 * w, -hb), (0, -hb)]
    return R + [(-x, z) for x, z in reversed(R[1:-1])]

def ring_pod(r, flat=0.9, n=12):
    return [(r * math.sin(2 * math.pi * i / n), r * flat * math.cos(2 * math.pi * i / n)) for i in range(n)]

FUSE = [(2.02, (0.03, 0.02, 0.02), 0.0), (1.78, (0.15, 0.065, 0.055), 0.0), (1.35, (0.30, 0.13, 0.095), 0.01),
        (0.85, (0.42, 0.19, 0.125), 0.02), (0.30, (0.50, 0.24, 0.145), 0.03), (-0.30, (0.54, 0.25, 0.155), 0.03),
        (-0.90, (0.53, 0.215, 0.155), 0.03), (-1.38, (0.46, 0.175, 0.14), 0.03), (-1.58, (0.38, 0.14, 0.12), 0.03)]
POD_X = 0.74
POD = [(0.42, 0.13), (0.36, 0.172), (0.12, 0.196), (-0.45, 0.206), (-1.15, 0.2), (-1.5, 0.186), (-1.7, 0.172)]

parts_hull, parts_carbon, parts_dark, parts_emit, parts_light = [], [], [], [], []

fuse, n = loft('fuselage', [(y, p, z, 0.0) for y, p, z in FUSE], ring_fuse)
recess(fuse, 'y', -1.58, 0.035, 0.1, 0.8)
crease_long(fuse, n, {3, 4, 10, 11}, 0.9)
crease_long(fuse, n, {6, 8}, 0.45)
smooth(subsurf(fuse)); parts_hull.append(fuse)

for s in (-1, 1):
    pod, pn = loft('pod', [(y, (r,), -0.01, s * POD_X) for y, r in POD], ring_pod)
    recess(pod, 'y', 0.42, 0.028, -0.34, 0.82)
    recess(pod, 'y', -1.7, 0.024, 0.24, 0.9)
    smooth(subsurf(pod)); parts_hull.append(pod)
    # intake fan
    hub = cylinder('hub', 0.045, 0.06, (s * POD_X, 0.11, -0.01), (math.pi / 2, 0, 0), 16)
    smooth(hub); parts_dark.append(hub)
    for k in range(14):
        a = 2 * math.pi * k / 14
        bpy.ops.mesh.primitive_cube_add(size=1, location=(s * POD_X + math.sin(a) * 0.09, 0.1, -0.01 + math.cos(a) * 0.09))
        bl = bpy.context.object; bl.scale = (0.012, 0.004, 0.09); bl.rotation_euler = (0.0, a, 0.0)
        bl.rotation_euler.rotate_axis('Z', 0.5)
        parts_dark.append(bl)
    # nozzle glow + petals
    glow = cylinder('engine', 0.13, 0.01, (s * POD_X, -1.47, -0.01), (math.pi / 2, 0, 0), 32)
    parts_emit.append(glow)
    for k in range(16):
        a = 2 * math.pi * k / 16
        bpy.ops.mesh.primitive_cube_add(size=1, location=(s * POD_X + math.sin(a) * 0.168, -1.73, -0.01 + math.cos(a) * 0.168 * 0.9))
        pe = bpy.context.object; pe.scale = (0.05, 0.08, 0.008); pe.rotation_euler = (0.0, a, 0.0)
        parts_dark.append(pe)
    # hover pads
    for y in (-0.25, -1.22):
        pad = cylinder('pad', 0.085, 0.035, (s * POD_X, y, -0.19), verts=24); bevel(pad, 0.006, 2); parts_dark.append(pad)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.072, minor_radius=0.009, location=(s * POD_X, y, -0.21), major_segments=32, minor_segments=8)
        parts_emit.append(bpy.context.object)
    # wing
    wing = prism('wing', [(s * x, y) for x, y in [(0.84, -0.3), (1.62, -1.02), (1.67, -1.3), (1.5, -1.34), (0.84, -1.44)]], 'Z', -0.035, 0.05)
    wing.rotation_euler = (0, s * -0.06, 0)
    bevel(wing, 0.012, 3); parts_carbon.append(wing)
    # wing leading-edge light strip + wingtip nav light
    le = prism('le', [(s * x, y) for x, y in [(0.86, -0.29), (1.62, -1.0), (1.625, -1.02), (0.865, -0.31)]], 'Z', -0.035 + 0.028, 0.006)
    le.rotation_euler = (0, s * -0.06, 0); parts_emit.append(le)
    th = s * -0.06; lx, lz = s * 1.665, -0.035
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, location=(lx * math.cos(th) + lz * math.sin(th), -1.17, -lx * math.sin(th) + lz * math.cos(th)))
    parts_light.append(bpy.context.object)
    # tail fin
    fin = prism('fin', [(-0.95, 0.1), (-1.62, 0.1), (-1.76, 0.6), (-1.5, 0.62)], 'X', 0.0, 0.03)
    fin.location = (s * POD_X, 0, 0); fin.rotation_euler = (0, s * 0.24, 0)
    bevel(fin, 0.008, 3); parts_carbon.append(fin)
    # canard
    can = prism('canard', [(s * x, y) for x, y in [(0.28, 1.14), (0.64, 0.88), (0.64, 0.76), (0.28, 0.8)]], 'Z', 0.0, 0.025)
    bevel(can, 0.006, 2); parts_carbon.append(can)
    # side vents
    for k in range(6):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(s * 0.537, -0.48 - k * 0.07, -0.01))
        v = bpy.context.object; v.scale = (0.03, 0.022, 0.07); v.rotation_euler = (0.25, 0, 0)
        bevel(v, 0.003, 1); parts_dark.append(v)

# dorsal intake behind the canopy
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 0.2; v.co.y *= 0.42; v.co.z *= 0.1
    if v.co.y > 0: v.co.z *= 0.55; v.co.x *= 0.8
    v.co.y -= 0.42; v.co.z += 0.255
me = bpy.data.meshes.new('dorsal'); bm.to_mesh(me); bm.free()
dorsal = link(bpy.data.objects.new('dorsal', me))
recess(dorsal, 'y', max(v.co.y for v in dorsal.data.vertices), 0.02, -0.15, 0.8)
smooth(subsurf(dorsal)); parts_hull.append(dorsal)

ant = cylinder('antenna', 0.006, 0.28, (0.12, -1.44, 0.25), (math.radians(-35), 0, 0), 8); parts_dark.append(ant)
ant2 = cylinder('antenna2', 0.005, 0.2, (-0.12, -1.46, 0.23), (math.radians(-40), 0, 0), 8); parts_dark.append(ant2)

bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0, location=(0, 0.38, 0.2))
canopy = bpy.context.object; canopy.name = 'canopy'; canopy.scale = (0.235, 0.62, 0.17); smooth(canopy)

# ---------------------------------------------------------------- material helpers
class NB:
    def __init__(self, mat):
        self.nt = mat.node_tree; self.N = self.nt.nodes; self.L = self.nt.links
    def node(self, t, **kw):
        n = self.N.new(t)
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def feed(self, sock, v):
        if isinstance(v, (int, float)): sock.default_value = v
        elif isinstance(v, tuple): sock.default_value = v if len(v) == 4 else (*v, 1.0)
        else: self.L.new(v, sock)
    def math(self, op, a, b=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.feed(n.inputs[0], a)
        if b is not None: self.feed(n.inputs[1], b)
        return n.outputs[0]
    def ss(self, x, a, b):
        n = self.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        self.feed(n.inputs['Value'], x); n.inputs['From Min'].default_value = a; n.inputs['From Max'].default_value = b
        return n.outputs['Result']
    def inv(self, x): return self.math('SUBTRACT', 1.0, x)
    def line(self, x, center, w):
        d = self.math('ABSOLUTE', self.math('SUBTRACT', x, center))
        return self.inv(self.ss(d, w, w * 1.6))
    def mix(self, f, a, b):
        n = self.node('ShaderNodeMix', data_type='RGBA')
        sock = {s.identifier: s for s in n.inputs}
        self.feed(sock['Factor_Float'], f); self.feed(sock['A_Color'], a); self.feed(sock['B_Color'], b)
        return {s.identifier: s for s in n.outputs}['Result_Color']
    def mixf(self, f, a, b):
        n = self.node('ShaderNodeMix', data_type='FLOAT')
        sock = {s.identifier: s for s in n.inputs}
        self.feed(sock['Factor_Float'], f); self.feed(sock['A_Float'], a); self.feed(sock['B_Float'], b)
        return {s.identifier: s for s in n.outputs}['Result_Float']
    def maxs(self, *xs):
        out = xs[0]
        for x in xs[1:]: out = self.math('MAXIMUM', out, x)
        return out
    def rgb(self, c):
        n = self.node('ShaderNodeRGB'); n.outputs[0].default_value = (*c, 1.0); return n.outputs[0]

def new_mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, NB(m)

def principled(nb):
    return nb.N['Principled BSDF']

def make_decal(path, text, font, size, w, h, mirror=False):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try: f = ImageFont.truetype(os.path.join(FONTS, font), size)
    except OSError: f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size)
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]), text, font=f, fill=(255, 255, 255, 255))
    if mirror: img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img.save(path)
    return bpy.data.images.load(path)

side_img = make_decal(os.path.join(WORK, 'decal_side.png'), 'GEMINI  FLIGHT  GROUP', 'Rajdhani-Bold.ttf', 120, 2048, 160)
num_imgs = {k: make_decal(os.path.join(WORK, f'decal_{k}.png'), n, 'Unbounded-ExtraBold.ttf', 150, 256, 200) for k, n in (('castor', '01'), ('pollux', '02'))}

def decal_mask(nb, img, u, v):
    vec = nb.node('ShaderNodeCombineXYZ'); nb.feed(vec.inputs[0], u); nb.feed(vec.inputs[1], v)
    tex = nb.node('ShaderNodeTexImage', image=img, extension='CLIP', interpolation='Cubic')
    nb.L.new(vec.outputs[0], tex.inputs[0])
    return tex.outputs['Alpha']

# ---------------------------------------------------------------- paint material
paint, nb = new_mat('Paint')
P = principled(nb)
tc = nb.node('ShaderNodeTexCoord'); sep = nb.node('ShaderNodeSeparateXYZ'); nb.L.new(tc.outputs['Object'], sep.inputs[0])
x, y, z = sep.outputs[0], sep.outputs[1], sep.outputs[2]
geo = nb.node('ShaderNodeNewGeometry'); nsep = nb.node('ShaderNodeSeparateXYZ'); nb.L.new(geo.outputs['Normal'], nsep.inputs[0])
nx, nz = nsep.outputs[0], nsep.outputs[2]
ax = nb.math('ABSOLUTE', x)
top = nb.ss(nz, -0.34, -0.12)
onfuse = nb.inv(nb.ss(ax, 0.5, 0.56))
inrange = nb.math('MULTIPLY', nb.inv(nb.ss(y, 1.72, 1.84)), nb.ss(y, -1.56, -1.46))
pearl, graphite = nb.rgb((0.78, 0.80, 0.86)), nb.rgb((0.03, 0.033, 0.045))
accent_node = nb.node('ShaderNodeRGB'); accent_node.outputs[0].default_value = (*ACCENTS['castor'], 1.0)
accent = accent_node.outputs[0]
base = nb.mix(top, graphite, pearl)
# subtle pearlescent drift along the body
drift = nb.math('MULTIPLY', nb.math('SINE', nb.math('MULTIPLY', y, 1.7)), 0.04)
base = nb.mix(nb.math('ADD', drift, 0.04), base, nb.rgb((0.72, 0.78, 0.92)))
stripe = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.inv(nb.ss(ax, 0.036, 0.044)), top), nb.math('MULTIPLY', inrange, onfuse))
pin = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.line(ax, 0.066, 0.0045), top), nb.math('MULTIPLY', inrange, onfuse))
core = nb.math('MULTIPLY', nb.inv(nb.ss(ax, 0.007, 0.011)), stripe)
base = nb.mix(stripe, base, nb.mix(0.2, accent, graphite))
base = nb.mix(pin, base, accent)
base = nb.mix(core, base, nb.rgb((0.02, 0.02, 0.03)))
# chine light line, intake rings, nose lights
chine = nb.math('MULTIPLY', nb.line(z, 0.046, 0.0055), nb.math('MULTIPLY', nb.ss(ax, 0.3, 0.42), nb.inv(nb.ss(nb.math('ABSOLUTE', nz), 0.45, 0.6))))
chine = nb.math('MULTIPLY', chine, nb.math('MULTIPLY', nb.ss(y, -1.45, -1.3), nb.inv(nb.ss(y, 1.45, 1.6))))
ring = nb.math('MULTIPLY', nb.line(y, 0.3, 0.012), nb.ss(ax, 0.5, 0.56))
nose = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.line(z, 0.012, 0.009), nb.math('MULTIPLY', nb.ss(y, 1.32, 1.36), nb.inv(nb.ss(y, 1.6, 1.64)))),
               nb.inv(nb.ss(nb.math('ABSOLUTE', nz), 0.5, 0.7)))
base = nb.mix(nb.maxs(chine, ring), base, accent)
base = nb.mix(nose, base, nb.rgb((0.9, 0.95, 1.0)))
# burnt titanium nozzles
noz = nb.math('MULTIPLY', nb.inv(nb.ss(y, -1.5, -1.42)), nb.ss(ax, 0.52, 0.56))
heat = nb.ss(y, -1.72, -1.5)
ti = nb.mix(heat, nb.rgb((0.16, 0.17, 0.32)), nb.rgb((0.42, 0.33, 0.22)))
ti = nb.mix(nb.ss(y, -1.55, -1.44), ti, nb.rgb((0.55, 0.55, 0.56)))
base = nb.mix(noz, base, ti)
# panel lines
pl = []
for yy in (1.55, 1.08, 0.58, -0.05, -0.62, -1.18):
    pl.append(nb.math('MULTIPLY', nb.line(y, yy, 0.0028), onfuse))
for yy in (0.22, -0.3, -0.86, -1.32):
    pl.append(nb.math('MULTIPLY', nb.line(y, yy, 0.0028), nb.ss(ax, 0.55, 0.6)))
for xx in (0.2, 0.33):
    pl.append(nb.math('MULTIPLY', nb.math('MULTIPLY', nb.line(ax, xx, 0.0026), top), nb.math('MULTIPLY', nb.ss(y, -1.42, -1.35), nb.inv(nb.ss(y, -0.06, 0.0)))))
pl.append(nb.math('MULTIPLY', nb.line(z, -0.08, 0.0026), nb.math('MULTIPLY', onfuse, nb.ss(y, -1.4, -1.3))))
panel = nb.maxs(*pl)
base = nb.mix(nb.math('MULTIPLY', panel, 0.65), base, nb.rgb((0.02, 0.02, 0.025)))
# decals: side callsign strip, top hull numbers
u_side = nb.math('DIVIDE', nb.math('ADD', nb.math('MULTIPLY', nb.math('ADD', y, 0.475), nb.math('SIGN', x)), 0.475), 0.95)
v_side = nb.math('DIVIDE', nb.math('SUBTRACT', z, -0.062), 0.075)
side_mask = nb.math('MULTIPLY', decal_mask(nb, side_img, u_side, v_side), nb.math('MULTIPLY', nb.ss(nb.math('ABSOLUTE', nx), 0.6, 0.8), onfuse))
base = nb.mix(nb.math('MULTIPLY', side_mask, 0.92), base, nb.rgb((0.85, 0.87, 0.92)))
num_masks = []
for xc in (-0.2, 0.2):
    u = nb.math('DIVIDE', nb.math('SUBTRACT', x, xc - 0.085), 0.17)
    v = nb.math('DIVIDE', nb.math('SUBTRACT', y, -1.3), 0.13)
    num_masks.append((u, v))
num_tex_nodes = []
nm = None
for u, v in num_masks:
    vec = nb.node('ShaderNodeCombineXYZ'); nb.feed(vec.inputs[0], u); nb.feed(vec.inputs[1], v)
    t = nb.node('ShaderNodeTexImage', image=num_imgs['castor'], extension='CLIP', interpolation='Cubic'); nb.L.new(vec.outputs[0], t.inputs[0])
    num_tex_nodes.append(t)
    m = nb.math('MULTIPLY', t.outputs['Alpha'], top)
    nm = m if nm is None else nb.math('MAXIMUM', nm, m)
base = nb.mix(nm, base, nb.rgb((0.025, 0.027, 0.035)))
# ambient-occlusion grime and edge wear
ao = nb.node('ShaderNodeAmbientOcclusion', samples=16); ao.inputs['Distance'].default_value = 0.12
base = nb.mix(nb.math('MULTIPLY', nb.inv(ao.outputs['AO']), 0.55), base, nb.rgb((0.012, 0.01, 0.012)))
noise = nb.node('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 14; noise.inputs['Detail'].default_value = 8
nb.L.new(tc.outputs['Object'], noise.inputs['Vector'])
grime = nb.math('MULTIPLY', nb.ss(noise.outputs['Fac'], 0.55, 0.8), 0.18)
base = nb.mix(grime, base, nb.rgb((0.1, 0.09, 0.09)))
nb.L.new(base, P.inputs['Base Color'])
rough = nb.mixf(top, 0.46, 0.17)
rough = nb.mixf(noz, rough, 0.3)
rough = nb.math('ADD', rough, nb.math('MULTIPLY', nb.math('SUBTRACT', noise.outputs['Fac'], 0.5), 0.12))
rough = nb.math('ADD', rough, nb.math('MULTIPLY', panel, 0.35), clamp=True)
nb.L.new(rough, P.inputs['Roughness'])
metal = nb.mixf(top, 0.6, 0.1)
metal = nb.mixf(noz, metal, 1.0)
METAL_SOCKETS = {'Paint': metal}
nb.L.new(metal, P.inputs['Metallic'])
bump = nb.node('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.55; bump.inputs['Distance'].default_value = 0.002
nb.feed(bump.inputs['Height'], nb.math('MULTIPLY', panel, -1.0))
nb.L.new(bump.outputs['Normal'], P.inputs['Normal'])
EMIT_MASK = {'Paint': nb.maxs(core, chine, ring, nose)}
ACCENT_NODES = [accent_node]
NUM_NODES = num_tex_nodes

# ---------------------------------------------------------------- carbon / dark / glass / emit
carbon, cb = new_mat('Carbon')
C = principled(cb)
ctc = cb.node('ShaderNodeTexCoord')
chk = cb.node('ShaderNodeTexChecker'); chk.inputs['Scale'].default_value = 90
cb.L.new(ctc.outputs['Object'], chk.inputs['Vector'])
wave = cb.node('ShaderNodeTexWave', wave_type='BANDS', bands_direction='DIAGONAL'); wave.inputs['Scale'].default_value = 140
cb.L.new(ctc.outputs['Object'], wave.inputs['Vector'])
weave = cb.math('MULTIPLY', cb.math('ADD', chk.outputs['Fac'], cb.math('MULTIPLY', wave.outputs['Fac'], 0.6)), 0.5)
cb.L.new(cb.mix(weave, cb.rgb((0.012, 0.013, 0.018)), cb.rgb((0.05, 0.052, 0.062))), C.inputs['Base Color'])
cb.L.new(cb.mixf(weave, 0.42, 0.26), C.inputs['Roughness'])
C.inputs['Metallic'].default_value = 0.15
cbump = cb.node('ShaderNodeBump'); cbump.inputs['Strength'].default_value = 0.15; cb.L.new(weave, cbump.inputs['Height']); cb.L.new(cbump.outputs['Normal'], C.inputs['Normal'])
METAL_SOCKETS['Carbon'] = 0.15
EMIT_MASK['Carbon'] = 0.0

dark, db = new_mat('Dark')
D = principled(db)
D.inputs['Base Color'].default_value = (0.022, 0.022, 0.028, 1); D.inputs['Metallic'].default_value = 0.85; D.inputs['Roughness'].default_value = 0.38
METAL_SOCKETS['Dark'] = 0.85
EMIT_MASK['Dark'] = 0.0

glass, gb = new_mat('Glass')
G = principled(gb)
G.inputs['Base Color'].default_value = (0.008, 0.01, 0.018, 1); G.inputs['Roughness'].default_value = 0.02; G.inputs['Metallic'].default_value = 0.0
G.inputs['Coat Weight'].default_value = 1.0

emit, eb = new_mat('EngineGlow')
E = principled(eb)
E.inputs['Base Color'].default_value = (0, 0, 0, 1); E.inputs['Emission Color'].default_value = (1, 1, 1, 1); E.inputs['Emission Strength'].default_value = 6
lightm, lb = new_mat('NavLight')
Lp = principled(lb)
Lp.inputs['Base Color'].default_value = (0, 0, 0, 1); Lp.inputs['Emission Color'].default_value = (1, 1, 1, 1); Lp.inputs['Emission Strength'].default_value = 8

def assign(objs, mat):
    for o in objs:
        o.data.materials.clear(); o.data.materials.append(mat)

assign(parts_hull, paint); assign(parts_carbon, carbon); assign(parts_dark, dark)
assign(parts_emit, emit); assign(parts_light, lightm); assign([canopy], glass)

# ---------------------------------------------------------------- bake
for o in parts_hull + parts_carbon + parts_dark + parts_emit + parts_light + [canopy]:
    apply_mods(o)
hull = join(parts_hull + parts_carbon + parts_dark, 'Hull')
emitter = join(parts_emit, 'EngineGlow')
lights = join(parts_light, 'NavLights')
for o in (hull, emitter, lights, canopy):
    for p in o.data.polygons: p.use_smooth = True

while hull.data.uv_layers:
    hull.data.uv_layers.remove(hull.data.uv_layers[0])
uvl = hull.data.uv_layers.new(name='UVMap')
hull.data.uv_layers.active = uvl; uvl.active_render = True
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = hull; hull.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.dissolve_degenerate(threshold=1e-5)
bpy.ops.mesh.select_all(action='SELECT')
# Smart UV Project and Pack Islands collapse islands in headless bpy 5.x, so: six-direction box projection + our own shelf packer.
bpy.ops.object.mode_set(mode='OBJECT')
def box_unwrap(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.normal_update()
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        n = f.normal; a = max(range(3), key=lambda i: abs(n[i])); sg = 1.0 if n[a] >= 0 else -1.0
        off = (a * 2 + (0 if sg > 0 else 1)) * 100.0   # keep the six directions from ever sharing UVs
        for l in f.loops:
            c = l.vert.co
            u, v = ((c.y * sg, c.z), (c.x * -sg, c.z), (c.x * sg, c.y))[a]
            l[uvl].uv = (u + off, v)
    bm.to_mesh(ob.data); bm.free()

def shelf_pack(ob, margin_px=6, fill=0.72):
    from bpy_extras import bmesh_utils
    bm = bmesh.new(); bm.from_mesh(ob.data); uvl = bm.loops.layers.uv.active
    islands = []
    for faces in bmesh_utils.bmesh_linked_uv_islands(bm, uvl):
        loops = [l for f in faces for l in f.loops]
        co = np.array([l[uvl].uv[:] for l in loops])
        mn, mx = co.min(0), co.max(0); size = mx - mn
        rot = size[1] > size[0]
        if rot: co = co[:, ::-1]; mn, mx = co.min(0), co.max(0); size = mx - mn
        islands.append([loops, co - mn, size])
    islands.sort(key=lambda i: -i[2][1])
    area = sum(i[2][0] * i[2][1] for i in islands)
    side = math.sqrt(area / fill)
    while True:
        m = margin_px / TEX * side
        x = y = shelf = 0.0; placed = []
        for loops, co, size in islands:
            if x + size[0] + m > side: x = 0.0; y += shelf + m; shelf = 0.0
            placed.append((loops, co, (x + m, y + m))); x += size[0] + m; shelf = max(shelf, size[1])
        if y + shelf + 2 * m <= side: break
        side *= 1.04
    for loops, co, off in placed:
        for l, c in zip(loops, co): l[uvl].uv = ((c[0] + off[0]) / side, (c[1] + off[1]) / side)
    bm.to_mesh(ob.data); bm.free()
    print('packed', len(islands), 'islands, fill', round(area / side ** 2, 3))

box_unwrap(hull)
shelf_pack(hull)
print('hull tris', sum(len(p.vertices) - 2 for p in hull.data.polygons))
_uv = np.array([d.uv[:] for d in hull.data.uv_layers.active.data])
print('uv range', _uv.min(0).round(3), _uv.max(0).round(3))

def new_image(name, data=False):
    img = bpy.data.images.new(name, TEX, TEX, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return img

def target(img):
    for mat in hull.data.materials:
        t = mat.node_tree
        node = t.nodes.get('BAKE') or t.nodes.new('ShaderNodeTexImage')
        node.name = 'BAKE'; node.image = img
        t.nodes.active = node

def bake(kind, img, samples, **kw):
    target(img)
    scene.cycles.samples = samples
    scene.render.bake.margin = 12
    bpy.ops.object.select_all(action='DESELECT'); hull.select_set(True); bpy.context.view_layer.objects.active = hull
    bpy.ops.object.bake(type=kind, use_clear=True, margin=12, **kw)
    img.filepath_raw = os.path.join(WORK, img.name + '.png'); img.file_format = 'PNG'; img.save()
    print('baked', kind, img.name)

def with_emission(sockets, fn):
    """Temporarily route a per-material value into emission so EMIT bakes it."""
    saved = []
    for mat in hull.data.materials:
        t = mat.node_tree; P_ = t.nodes['Principled BSDF']; NB_ = NB(mat)
        val = sockets.get(mat.name, 0.0)
        old = [(l.from_socket) for l in t.links if l.to_socket == P_.inputs['Emission Color']]
        sp = P_.inputs['Emission Strength'].default_value
        comb = t.nodes.new('ShaderNodeCombineColor')
        for i in range(3): NB_.feed(comb.inputs[i], val)
        t.links.new(comb.outputs[0], P_.inputs['Emission Color']); P_.inputs['Emission Strength'].default_value = 1.0
        saved.append((mat, comb, sp))
    fn()
    for mat, comb, sp in saved:
        mat.node_tree.nodes.remove(comb); mat.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = sp

def set_accent(name):
    for n in ACCENT_NODES: n.outputs[0].default_value = (*ACCENTS[name], 1.0)
    for n in NUM_NODES: n.image = num_imgs[name]

imgs = {}
imgs['rough'] = new_image('rough', True); bake('ROUGHNESS', imgs['rough'], 4)
imgs['normal'] = new_image('normal', True); bake('NORMAL', imgs['normal'], 8, normal_space='TANGENT')
imgs['ao'] = new_image('ao', True); bake('AO', imgs['ao'], 64)
imgs['metal'] = new_image('metal', True); with_emission(METAL_SOCKETS, lambda: bake('EMIT', imgs['metal'], 1))
imgs['emit'] = new_image('emit', True); with_emission(EMIT_MASK, lambda: bake('EMIT', imgs['emit'], 4))
for k in ACCENTS:
    set_accent(k)
    imgs['base_' + k] = new_image('base_' + k); bake('DIFFUSE', imgs['base_' + k], 8, pass_filter={'COLOR'})

def arr(img):
    a = np.array(img.pixels[:], dtype=np.float32).reshape(TEX, TEX, 4)
    return a

ao_a, r_a, m_a = arr(imgs['ao']), arr(imgs['rough']), arr(imgs['metal'])
orm = np.ones((TEX, TEX, 4), np.float32)
orm[..., 0] = 0.35 + 0.65 * ao_a[..., 0]; orm[..., 1] = r_a[..., 0]; orm[..., 2] = m_a[..., 0]
img_orm = new_image('orm', True); img_orm.pixels[:] = orm.ravel()
img_orm.filepath_raw = os.path.join(WORK, 'orm.png'); img_orm.file_format = 'PNG'; img_orm.save()

# ---------------------------------------------------------------- export material + GLB
from PIL import Image
def webp(src_name, dst_name, q=88):
    Image.open(os.path.join(WORK, src_name + '.png')).convert('RGB').save(os.path.join(OUT, dst_name), 'WEBP', quality=q, method=6)
webp('base_pollux', 'ship_base_pollux.webp')

baked, kb = new_mat('ShipHull')
K = principled(kb)
def tex(img, data):
    n = kb.node('ShaderNodeTexImage', image=img); img.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return n
tb = tex(bpy.data.images.load(os.path.join(WORK, 'base_castor.png')), False); kb.L.new(tb.outputs[0], K.inputs['Base Color'])
to = tex(bpy.data.images.load(os.path.join(WORK, 'orm.png')), True)
so = kb.node('ShaderNodeSeparateColor'); kb.L.new(to.outputs[0], so.inputs[0])
kb.L.new(so.outputs[1], K.inputs['Roughness']); kb.L.new(so.outputs[2], K.inputs['Metallic'])
grp = bpy.data.node_groups.get('glTF Material Output') or bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
if not grp.interface.items_tree:
    grp.interface.new_socket('Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
gnode = kb.node('ShaderNodeGroup'); gnode.node_tree = grp; kb.L.new(so.outputs[0], gnode.inputs['Occlusion'])
tn = tex(bpy.data.images.load(os.path.join(WORK, 'normal.png')), True)
nm_node = kb.node('ShaderNodeNormalMap'); kb.L.new(tn.outputs[0], nm_node.inputs['Color']); kb.L.new(nm_node.outputs[0], K.inputs['Normal'])
te = tex(bpy.data.images.load(os.path.join(WORK, 'emit.png')), False); kb.L.new(te.outputs[0], K.inputs['Emission Color']); K.inputs['Emission Strength'].default_value = 1.0
hull.data.materials.clear(); hull.data.materials.append(baked)

bpy.ops.object.select_all(action='DESELECT')
for o in (hull, emitter, lights, canopy): o.select_set(True)
bpy.context.view_layer.objects.active = hull
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'ship.glb'), export_format='GLB', use_selection=True,
                          export_image_format='WEBP', export_yup=True, export_apply=True, export_tangents=False)
print('exported', os.path.join(OUT, 'ship.glb'), os.path.getsize(os.path.join(OUT, 'ship.glb')) // 1024, 'KB')

# ---------------------------------------------------------------- optional beauty render (QA)
if PREVIEW:
    world = bpy.data.worlds.new('w'); scene.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (0.004, 0.003, 0.008, 1)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.35))
    floor, fb = new_mat('Floor'); F = principled(fb)
    F.inputs['Base Color'].default_value = (0.01, 0.01, 0.014, 1); F.inputs['Roughness'].default_value = 0.12
    bpy.context.object.data.materials.append(floor)
    def area(loc, rot, col, energy, size):
        bpy.ops.object.light_add(type='AREA', location=loc, rotation=rot)
        l = bpy.context.object.data; l.color = col; l.energy = energy; l.size = size
    area((-3.5, 1.5, 2.0), (math.radians(60), 0, math.radians(-110)), ACCENTS['castor'], 600, 3)
    area((3.5, -1.0, 2.2), (math.radians(60), 0, math.radians(110)), ACCENTS['pollux'], 600, 3)
    area((0, 0, 5), (0, 0, 0), (0.85, 0.85, 1.0), 300, 4)
    area((0, 6, 1.5), (math.radians(-80), 0, 0), (1.0, 0.6, 0.8), 300, 6)
    for o in (emitter,):
        m = o.data.materials[0]; m.node_tree.nodes['Principled BSDF'].inputs['Emission Color'].default_value = (*ACCENTS['castor'], 1)
    em = hull.data.materials[0]; t_ = em.node_tree; P_ = t_.nodes['Principled BSDF']
    mul = t_.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'
    ms = {x.identifier: x for x in mul.inputs}; ms['Factor_Float'].default_value = 1.0
    t_.links.new(te.outputs[0], ms['A_Color']); ms['B_Color'].default_value = (*ACCENTS['castor'], 1)
    t_.links.new({x.identifier: x for x in mul.outputs}['Result_Color'], P_.inputs['Emission Color'])
    P_.inputs['Emission Strength'].default_value = 8.0
    bpy.ops.object.camera_add(location=(4.2, 4.6, 1.9))
    cam = bpy.context.object; scene.camera = cam
    d = cam.constraints.new('TRACK_TO'); bpy.ops.object.empty_add(location=(0, -0.1, 0.0)); d.target = bpy.context.object
    d.track_axis = 'TRACK_NEGATIVE_Z'; d.up_axis = 'UP_Y'
    cam.data.lens = 50
    scene.render.resolution_x = 1280; scene.render.resolution_y = 800
    scene.cycles.samples = SAMPLES; scene.cycles.use_denoising = True
    scene.view_settings.view_transform = 'AgX'
    for look in ('AgX - Punchy', 'Punchy'):
        try: scene.view_settings.look = look; break
        except TypeError: pass
    scene.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    print('preview', PREVIEW)
    # second view: chase-camera angle with a neutral key light, to check paint, stripe and decals
    area((1.5, -2.0, 4.5), (math.radians(25), 0, 0), (1.0, 0.97, 0.94), 900, 3)
    cam.location = (2.2, -5.2, 2.7)
    scene.render.filepath = PREVIEW.replace('.png', '_rear.png')
    bpy.ops.render.render(write_still=True)
    print('preview', scene.render.filepath)
