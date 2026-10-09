"""Image models. Every size_bytes was read from the Hugging Face API (LFS size)
or a HEAD request on 2026-10-08; tests/test_catalog_sizes_live.py re-checks
them when run with AI_STUDIO_CHECK_HF=1.

The SD1.5 / SDXL checkpoints are the pre-rebuild models, unchanged in meaning:
one ``checkpoint`` part (plus ``vae`` where it needs one). Their files from
before the rebuild stay in models/sd/catalog/ and are found there.
"""

from catalog import LCM_LORA_FILENAME, part

# Engine flags shared by entries. The SD1.5 ones are the flags sd-server always
# had: direct conv and VAE tiling keep every Vulkan allocation under the Iris
# Xe's per-allocation ceiling (see the old model_manager._launch notes).
SD15_FLAGS = ["--diffusion-conv-direct", "--vae-conv-direct", "--vae-tiling"]
# Newer models: weights wait in RAM and move to the iGPU when used, flash
# attention in the diffusion model, VAE in tiles. All as the sd.cpp docs run
# them; reasoned from the docs, not run on this laptop yet.
DIT_FLAGS = ["--offload-to-cpu", "--diffusion-fa", "--vae-conv-direct", "--vae-tiling"]

_LCM_LORA = part(
    "lora",
    "latent-consistency/lcm-lora-sdv1-5",
    "pytorch_lora_weights.safetensors",
    134621556,
    filename=LCM_LORA_FILENAME,
)

# Shared parts (stored once, used by several models).
_ZIMAGE_LLM = part(
    "llm",
    "unsloth/Qwen3-4B-Instruct-2507-GGUF",
    "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    2497281120,
)
_FLUX1_AE = part(
    "vae", "Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors", 335304388
)
_FLUX2_AE = part(
    "vae", "Comfy-Org/flux2-dev", "split_files/vae/flux2-vae.safetensors", 336213556
)
_QWEN3VL_8B = part(
    "llm",
    "Qwen/Qwen3-VL-8B-Instruct-GGUF",
    "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
    5027784800,
)


def _sd15(**settings):
    return {
        "steps": 16,
        "cfg_scale": 7.0,
        "sampler": "dpm++2m",
        "width": 512,
        "height": 512,
        "use_lcm": False,
        **settings,
    }


ENTRIES = [
    # ---- the pre-rebuild checkpoints -------------------------------------
    {
        "id": "meinamix-v10",
        "label": "Anime -- General",
        "blurb": "General-purpose anime art style -- characters, backgrounds, everyday scenes.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "current",
        "cpu_helper": True,
        "parts": [
            part(
                "checkpoint",
                "Meina/MeinaMix",
                "Meina%20V10%20-%20baked%20VAE.safetensors",
                3526112242,
                filename="meinamix_v10.safetensors",
            )
        ],
        "settings": _sd15(),
        "engine_flags": SD15_FLAGS,
        "notes": "MeinaMix V10, SD1.5, baked VAE. No content filter.",
    },
    {
        "id": "meinahentai",
        "label": "Anime -- Alternate",
        "blurb": "Same lineage as Anime -- General, tuned toward a different subject focus.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "current",
        "cpu_helper": True,
        "parts": [
            part(
                "checkpoint",
                "Meina/MeinaMix",
                "MeinaHentai%20-%20baked%20VAE.safetensors",
                2132651163,
                filename="meinahentai.safetensors",
            )
        ],
        "settings": _sd15(),
        "engine_flags": SD15_FLAGS,
        "notes": "MeinaHentai, SD1.5, baked VAE, tuned toward explicit content.",
    },
    {
        "id": "counterfeit-v3",
        "label": "Anime -- Illustrative",
        "blurb": "Vibrant, illustrative anime style -- strong color and linework.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "current",
        "cpu_helper": True,
        "parts": [
            part(
                "checkpoint",
                "gsdf/Counterfeit-V3.0",
                "Counterfeit-V3.0_fp16.safetensors",
                4244124028,
                filename="counterfeit_v3.safetensors",
            )
        ],
        "settings": _sd15(),
        "engine_flags": SD15_FLAGS,
        "notes": "Counterfeit V3.0 fp16, SD1.5.",
    },
    {
        "id": "realistic-vision-v6",
        "label": "Realistic -- General",
        "blurb": "Photorealistic general-purpose style, not anime.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "current",
        "cpu_helper": True,
        "parts": [
            part(
                "checkpoint",
                "SG161222/Realistic_Vision_V6.0_B1_noVAE",
                "Realistic_Vision_V6.0_NV_B1_fp16.safetensors",
                2132625894,
                filename="realisticVisionV60B1_fp16.safetensors",
            ),
            part(
                "vae",
                "stabilityai/sd-vae-ft-mse-original",
                "vae-ft-mse-840000-ema-pruned.safetensors",
                334641190,
            ),
            _LCM_LORA,
        ],
        "settings": _sd15(sampler="lcm", steps=6, cfg_scale=1.8, use_lcm=True),
        "engine_flags": SD15_FLAGS,
        "notes": "Realistic Vision V6.0 B1 (SD1.5) + ft-mse VAE. The LCM LoRA "
        "works on this one (tested before the rebuild); on the Meina models it "
        "gives a haze, so use_lcm is per entry.",
    },
    {
        "id": "segmind-vega",
        "label": "Realistic -- High Detail",
        "blurb": "Realistic style with sharper detail in big pictures, but slower to make.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "current",
        "cpu_helper": True,
        "parts": [
            part(
                "checkpoint",
                "segmind/Segmind-Vega",
                "segmind-vega.safetensors",
                3293395670,
            ),
            part(
                "vae",
                "madebyollin/sdxl-vae-fp16-fix",
                "sdxl_vae.safetensors",
                334641162,
                filename="sdxl-vae-fp16-fix.safetensors",
            ),
        ],
        "settings": _sd15(steps=20, width=1024, height=1024),
        "engine_flags": SD15_FLAGS,
        "notes": "Distilled SDXL at 1024px with the fp16-fix VAE; steps/cfg untuned.",
    },
    # ---- new compact models ----------------------------------------------
    {
        "id": "z-image-turbo",
        "label": "Fast and Detailed",
        "blurb": "Sharp, natural-looking pictures in a handful of steps, and it "
        "can write short text inside the picture.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "leejet/Z-Image-Turbo-GGUF",
                "z_image_turbo-Q4_K.gguf",
                3864250304,
            ),
            _ZIMAGE_LLM,
            _FLUX1_AE,
        ],
        "settings": {
            "steps": 8,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": DIT_FLAGS,
        "notes": "Z-Image-Turbo 6B Q4_K GGUF + Qwen3-4B-Instruct-2507 Q4_K_M llm + "
        "FLUX.1 ae. cfg 1.0, 8 steps per sd.cpp docs/z_image.md. Not run here yet.",
    },
    {
        "id": "flux2-klein-4b",
        "label": "Quick Sketch to Finish",
        "blurb": "A small, quick all-rounder that follows the prompt closely.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "leejet/FLUX.2-klein-4B-GGUF",
                "flux-2-klein-4b-Q4_0.gguf",
                2460378560,
            ),
            part("llm", "unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf", 2497281312),
            _FLUX2_AE,
        ],
        "settings": {
            "steps": 4,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": DIT_FLAGS,
        "notes": "FLUX.2-klein 4B Q4_0 + Qwen3-4B Q4_K_M (plain Qwen3-4B, not the "
        "2507 instruct Z-Image uses) + flux2 VAE from Comfy-Org/flux2-dev (same "
        "file as the gated BFL one). cfg 1.0, 4 steps per docs/flux2.md. Also "
        "edits with -r, not wired yet.",
    },
    {
        "id": "qwen-image-2.1",
        "label": "Editing and Clear Backgrounds",
        "blurb": "Good at text and layout, and can make pictures with a see-through background.",
        "tier": "compact",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "Abiray/Qwen-Image-2.1-GGUF",
                "qwen_image_2.1_Q3_K_M.gguf",
                3185944736,
            ),
            _QWEN3VL_8B,
            part(
                "vae",
                "Comfy-Org/Qwen-Image-2.1",
                "vae/qwen_image_2.1_vae_bf16.safetensors",
                675509688,
            ),
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 6.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": [
            "--offload-to-cpu",
            "--fa",
            "--vae-conv-direct",
            "--vae-tiling",
        ],
        "notes": "Qwen-Image 2.1 Q3_K_M (Abiray) + Qwen3-VL-8B Q4_K_M llm + its own "
        "VAE (earlier Qwen/Wan VAEs are not interchangeable). Needs the newer "
        "engine (support landed 2026-09-20). cfg 6.0 euler per "
        "docs/qwen_image_2.1.md; steps are the sd.cpp default, untuned. Transparent "
        "output needs the RGBA prompt wording and png output.",
    },
    # ---- big models (connected only) ---------------------------------------
    {
        "id": "z-image-base",
        "label": "Fast and Detailed -- Full",
        "blurb": "The full version of Fast and Detailed: slower, with more variety.",
        "tier": "big",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion", "unsloth/Z-Image-GGUF", "z-image-Q4_K_M.gguf", 5066995776
            ),
            _ZIMAGE_LLM,
            _FLUX1_AE,
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 5.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": DIT_FLAGS,
        "notes": "Z-Image base Q4_K_M, cfg 5.0 per docs/z_image.md; steps default.",
    },
    {
        "id": "flux2-klein-9b",
        "label": "Quick Sketch to Finish -- Large",
        "blurb": "The larger version of Quick Sketch to Finish, with finer detail.",
        "tier": "big",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "leejet/FLUX.2-klein-9B-GGUF",
                "flux-2-klein-9b-Q4_0.gguf",
                5616208032,
            ),
            part("llm", "unsloth/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf", 5027784512),
            _FLUX2_AE,
        ],
        "settings": {
            "steps": 4,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": DIT_FLAGS,
        "notes": "FLUX.2-klein 9B Q4_0 + Qwen3-8B Q4_K_M + flux2 VAE.",
    },
    {
        "id": "ideogram-4",
        "label": "Posters, Comics and Lettering",
        "blurb": "The best at words inside pictures, page layouts, comics and manga.",
        "tier": "big",
        "engine": "sd",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "ideogram-ai/ideogram-4-fp8",
                "transformer/diffusion_pytorch_model.safetensors",
                9289792888,
                filename="ideogram4_fp8.safetensors",
                gated=True,
            ),
            part(
                "uncond_diffusion",
                "ideogram-ai/ideogram-4-fp8",
                "unconditional_transformer/diffusion_pytorch_model.safetensors",
                9289792888,
                filename="ideogram4_uncond_fp8.safetensors",
                gated=True,
            ),
            _QWEN3VL_8B,
            _FLUX2_AE,
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 7.0,
            "sampler": "euler",
            "width": 1024,
            "height": 1024,
        },
        "engine_flags": DIT_FLAGS,
        "notes": "Ideogram 4 fp8 main + unconditional model (repo gated: needs a "
        "Hugging Face sign-in) + Qwen3-VL-8B Q4_K_M (the same file the sd.cpp "
        "example uses, shared with Qwen-Image 2.1) + flux2 VAE. docs/ideogram4.md "
        "gives no steps/cfg; these are sd.cpp defaults, untuned. Prompts work "
        "best as the JSON layout format.",
    },
]
