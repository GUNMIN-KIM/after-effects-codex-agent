"""Dry-run stubs: keep every node schema real, replace only model math.

FakeVAE is a lossless temporal codec (Wan layout: 1 + 4k frames -> 1 + k latents,
8x spatial). Latent channels 0..11 hold 4 RGB frames, so decoded frames can be traced
back to exact source frames. Samplers copy the conditioning latents through.
"""
import logging
import torch
import torch.nn.functional as F
import nodes
from comfy_api.latest import io

log = logging.getLogger("dryrun")
CALLS = []


class FakeModel:
    def __init__(self, name):
        self.name = name


def _down(x):  # [T,H,W,3] -> [T,3,H/8,W/8]
    return F.avg_pool2d(x.movedim(-1, 1), 8)


class FakeVAE:
    latent_channels = 16

    def encode(self, pixels):
        pixels = pixels[..., :3].float()
        T, H, W, _ = pixels.shape
        assert H % 8 == 0 and W % 8 == 0, f"VAE encode needs /8 size, got {W}x{H}"
        d = _down(pixels)
        lt = (T - 1) // 4 + 1
        out = torch.zeros(1, 16, lt, H // 8, W // 8)
        out[0, 0:3, 0] = d[0]
        for j in range(1, lt):
            for k in range(4):
                src = min(4 * j - 3 + k, T - 1)
                out[0, 3 * k:3 * k + 3, j] = d[src]
        CALLS.append(("vae.encode", T, W, H))
        return out

    def decode(self, samples):
        B, C, lt, h, w = samples.shape
        frames = [samples[:, 0:3, 0]]
        for j in range(1, lt):
            for k in range(4):
                frames.append(samples[:, 3 * k:3 * k + 3, j])
        v = torch.stack(frames, dim=1)  # B,T,3,h,w
        v = v.reshape(-1, 3, h, w)
        v = F.interpolate(v, scale_factor=8, mode="nearest")
        v = v.reshape(B, -1, 3, h * 8, w * 8).movedim(2, -1).clamp(0, 1)
        CALLS.append(("vae.decode", v.shape[1], w * 8, h * 8))
        return v

    def spacial_compression_encode(self):
        return 8

    def temporal_compression_decode(self):
        return 4


class FakeClip:
    pass


class FakeCV:
    pass


def _cond():
    return [[torch.zeros(1, 4, 8), {}]]


nodes.UNETLoader.load_unet = lambda self, unet_name, weight_dtype="default": (FakeModel(unet_name),)
nodes.LoraLoaderModelOnly.load_lora_model_only = lambda self, model, lora_name, strength_model: (FakeModel(f"{model.name}+{lora_name}@{strength_model}"),)
nodes.CLIPLoader.load_clip = lambda self, clip_name, type="stable_diffusion", device="default": (FakeClip(),)
nodes.CLIPTextEncode.encode = lambda self, clip, text: (_cond(),)
nodes.VAELoader.load_vae = lambda self, vae_name: (FakeVAE(),)
nodes.CLIPVisionLoader.load_clip = lambda self, clip_name: (FakeCV(),)
nodes.CLIPVisionEncode.encode = lambda self, clip_vision, image, crop="center": (FakeCV(),)


def _ksampler(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=1.0):
    CALLS.append(("KSampler", model.name, seed, steps, cfg))
    log.warning("DRYRUN KSampler model=%s steps=%s cfg=%s seed=%s", model.name, steps, cfg, seed)
    lat = latent_image["samples"]
    vf = None
    for c in positive:
        if "vace_frames" in c[1]:
            vf = c[1]["vace_frames"][0]
    out = lat.clone()
    if vf is not None:
        # inactive channels: source outside the mask, 0.5 gray inside -> "generated" area shows gray
        out = vf[:, :16].clone()
        assert out.shape == lat.shape, (out.shape, lat.shape)
    return ({**latent_image, "samples": out},)


nodes.KSampler.sample = _ksampler

orig = nodes.NODE_CLASS_MAPPINGS


def _patch_v3(name, fn):
    cls = orig[name]
    cls.execute = classmethod(fn)


def _model_passthrough(cls, model, **kw):
    return io.NodeOutput(model)


for n in ("ModelSamplingSD3",):
    c = orig[n]
    if hasattr(c, "patch"):
        c.patch = lambda self, model, shift, multiplier=1000: (model,)
    else:
        _patch_v3(n, lambda cls, model, **kw: io.NodeOutput(model))

_patch_v3("WanAnimate2Cache", _model_passthrough)
_patch_v3("ContextWindowsManual", _model_passthrough)
_patch_v3("KSamplerSelect", lambda cls, sampler_name: io.NodeOutput(sampler_name))


def _basic_sched(cls, model, scheduler, steps, denoise):
    CALLS.append(("BasicScheduler", model.name, steps))
    log.warning("DRYRUN BasicScheduler model=%s steps=%s", model.name, steps)
    return io.NodeOutput(torch.linspace(1, 0, steps + 1))


_patch_v3("BasicScheduler", _basic_sched)


def _sampler_custom(cls, model, add_noise, noise_seed, cfg, positive, negative, sampler, sigmas, latent_image):
    log.warning("DRYRUN SamplerCustom model=%s seed=%s cfg=%s steps=%s", model.name, noise_seed, cfg, len(sigmas) - 1)
    lat = latent_image["samples"]
    out = lat.clone()
    d = positive[0][1]
    cat = d["concat_latent_image"]
    mask = d["concat_mask"]
    pose = d.get("pose_video_latent")
    T = lat.shape[2]
    trim = cat.shape[2] - (pose.shape[2] if pose is not None else 0)
    for t in range(T):
        if mask[0, 0, t].max() == 0:
            out[:, :, t] = cat[:, :, t]
        elif pose is not None:
            out[:, :, t] = pose[:, :, t - trim]
    return io.NodeOutput({**latent_image, "samples": out}, {**latent_image, "samples": out})


_patch_v3("SamplerCustom", _sampler_custom)

NODE_CLASS_MAPPINGS = {}
log.warning("DRYRUN stubs installed")
