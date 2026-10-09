"""3D world models: worlds you walk through, built a piece at a time as you move.

Each entry runs on a world runner (``src/worlds/``), named in ``engine`` as
``world:<runner-id>``. Feasibility, sources and what is verified versus
reasoned are in ``docs/WORLDS.md``.

Every size_bytes below was read from the Hugging Face API (LFS size) on
2026-10-08; code archives were downloaded once and counted. Downloads use the
``main`` branch like the rest of the catalog; the revision each size was read
at is in the comment above each file list.

World parts can have a ``dest``: where the runner links the stored file inside
its runtime folder (``models/worlds/runtime/<runner>/``), because these
projects expect their own folder layout. The stored filename is made unique by
a prefix, since many projects ship files with the same names.
"""

from catalog import hf, part


def _hf_files(repo, prefix, dest_root, files, role="weights"):
    """Parts for a list of (path in repo, size) from one Hugging Face repo."""
    return [
        {
            "role": role,
            "url": hf(repo, path),
            "filename": f"{prefix}--{path.replace('/', '--')}",
            "size_bytes": size,
            "dest": f"{dest_root}/{path}",
        }
        for path, size in files
    ]


def _code(repo, sha, size, prefix):
    """A pinned source archive of a GitHub project (role "code")."""
    return {
        "role": "code",
        "url": f"https://codeload.github.com/{repo}/tar.gz/{sha}",
        "filename": f"{prefix}-code-{sha[:7]}.tar.gz",
        "size_bytes": size,
        "dest": "src",
    }


# The walk-through runner reuses parts the video catalog already lists (same
# filename, url and size), so they are stored once.
_VACE_13B = part(
    "diffusion",
    "calcuis/wan-1.3b-gguf",
    "wan2.1-vace-1.3b-q8_0.gguf",
    2369289920,
)
_UMT5 = part(
    "t5xxl",
    "city96/umt5-xxl-encoder-gguf",
    "umt5-xxl-encoder-Q4_K_M.gguf",
    3655145312,
)
_WAN21_VAE = part(
    "vae",
    "QuantStack/Wan2.2-T2V-A14B-GGUF",
    "VAE/Wan2.1_VAE.safetensors",
    253815318,
)

# inspatio/world-1.5 at revision 6a5cf5e27b8a05930911a5416fa8c68eabdda414 (sizes from the Hugging Face API, 2026-10-08)
_INSPATIO_DIT = _hf_files(
    "inspatio/world-1.5",
    "inspatio-world-1.5",
    "checkpoints/InSpatio-World-1.3B",
    [
        ("InSpatio-World-1.5-1.3B.safetensors", 5676566992),
    ],
)

# Wan-AI/Wan2.1-T2V-1.3B at revision 37ec512624d61f7aa208f7ea8140a131f93afc9a (sizes from the Hugging Face API, 2026-10-08)
_INSPATIO_WAN = _hf_files(
    "Wan-AI/Wan2.1-T2V-1.3B",
    "wan2.1-t2v-1.3b",
    "checkpoints/Wan2.1-T2V-1.3B",
    [
        ("Wan2.1_VAE.pth", 507609880),
        ("config.json", 249),
        ("google/umt5-xxl/special_tokens_map.json", 6623),
        ("google/umt5-xxl/spiece.model", 4548313),
        ("google/umt5-xxl/tokenizer.json", 16837417),
        ("google/umt5-xxl/tokenizer_config.json", 61728),
        ("models_t5_umt5-xxl-enc-bf16.pth", 11361920418),
    ],
)

# depth-anything/DA3NESTED-GIANT-LARGE at revision 8615eefb62f2db4f8d6ebaa59160086981672829 (sizes from the Hugging Face API, 2026-10-08)
_INSPATIO_DEPTH = _hf_files(
    "depth-anything/DA3NESTED-GIANT-LARGE",
    "da3-nested-giant-large",
    "checkpoints/depth",
    [
        ("config.json", 3113),
        ("model.safetensors", 6759558100),
    ],
)

# TencentARC/WorldCrafter-Fast at revision 51320c3eb58a6313ccd6021a1da6d723d53e1a58 (sizes from the Hugging Face API, 2026-10-08)
_WORLDCRAFTER_FAST = _hf_files(
    "TencentARC/WorldCrafter-Fast",
    "worldcrafter-fast",
    "weights/WorldCrafter-Fast",
    [
        ("SHA256SUMS", 4978),
        ("adapter_high_noise/dmd_timestep_contract.json", 123820),
        ("adapter_high_noise/pytorch_lora_weights.safetensors", 2503578928),
        ("adapter_high_noise/repencoder_frozen.json", 841),
        ("adapter_high_noise/transformer_partial.pth", 1062367927),
        ("adapter_low_noise/dmd_timestep_contract.json", 123820),
        ("adapter_low_noise/pytorch_lora_weights.safetensors", 2503578928),
        ("adapter_low_noise/repencoder_frozen.json", 841),
        ("adapter_low_noise/transformer_partial.pth", 1062367927),
        ("inference_config.json", 419),
        ("manifest.json", 13014),
        ("repencoder/config.json", 628),
        ("repencoder/manifest.json", 440),
        ("repencoder/model.safetensors", 2478869000),
        ("scheduler/scheduler_config.json", 546),
        ("text_encoder/config.json", 853),
        ("text_encoder/model-00001-of-00005.safetensors", 4972389712),
        ("text_encoder/model-00002-of-00005.safetensors", 4899225672),
        ("text_encoder/model-00003-of-00005.safetensors", 4966309504),
        ("text_encoder/model-00004-of-00005.safetensors", 4999880704),
        ("text_encoder/model-00005-of-00005.safetensors", 2885866152),
        ("text_encoder/model.safetensors.index.json", 22476),
        ("tokenizer/special_tokens_map.json", 7079),
        ("tokenizer/spiece.model", 4548313),
        ("tokenizer/tokenizer.json", 16837459),
        ("tokenizer/tokenizer_config.json", 61758),
        ("transformer_high_noise/config.json", 961),
        (
            "transformer_high_noise/diffusion_pytorch_model-00001-of-00006.safetensors",
            9992440632,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model-00002-of-00006.safetensors",
            9943937952,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model-00003-of-00006.safetensors",
            9944020376,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model-00004-of-00006.safetensors",
            9839059792,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model-00005-of-00006.safetensors",
            9839059792,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model-00006-of-00006.safetensors",
            7608728496,
        ),
        (
            "transformer_high_noise/diffusion_pytorch_model.safetensors.index.json",
            97788,
        ),
        ("transformer_low_noise/config.json", 961),
        (
            "transformer_low_noise/diffusion_pytorch_model-00001-of-00006.safetensors",
            9992440632,
        ),
        (
            "transformer_low_noise/diffusion_pytorch_model-00002-of-00006.safetensors",
            9943937952,
        ),
        (
            "transformer_low_noise/diffusion_pytorch_model-00003-of-00006.safetensors",
            9944020376,
        ),
        (
            "transformer_low_noise/diffusion_pytorch_model-00004-of-00006.safetensors",
            9839059792,
        ),
        (
            "transformer_low_noise/diffusion_pytorch_model-00005-of-00006.safetensors",
            9839059792,
        ),
        (
            "transformer_low_noise/diffusion_pytorch_model-00006-of-00006.safetensors",
            7608728496,
        ),
        ("transformer_low_noise/diffusion_pytorch_model.safetensors.index.json", 97788),
        ("vae/config.json", 724),
        ("vae/diffusion_pytorch_model.safetensors", 507591892),
    ],
)

# AlayaLab/Evoke at revision 7fa34ecef85754fde6f08996b1ece9d195dcd2f4 (sizes from the Hugging Face API, 2026-10-08)
_EVOKE = _hf_files(
    "AlayaLab/Evoke",
    "evoke",
    "models",
    [
        ("evoke-base/configuration.json", 56),
        ("evoke-base/model_index.json", 458),
        ("evoke-base/modular_model_index.json", 1688),
        ("evoke-base/scheduler/scheduler_config.json", 539),
        ("evoke-base/text_encoder/config.json", 853),
        ("evoke-base/text_encoder/model-00001-of-00005.safetensors", 4972389712),
        ("evoke-base/text_encoder/model-00002-of-00005.safetensors", 4899225672),
        ("evoke-base/text_encoder/model-00003-of-00005.safetensors", 4966309504),
        ("evoke-base/text_encoder/model-00004-of-00005.safetensors", 4999880704),
        ("evoke-base/text_encoder/model-00005-of-00005.safetensors", 2885866152),
        ("evoke-base/text_encoder/model.safetensors.index.json", 22476),
        ("evoke-base/tokenizer/special_tokens_map.json", 7079),
        ("evoke-base/tokenizer/spiece.model", 4548313),
        ("evoke-base/tokenizer/tokenizer.json", 16837459),
        ("evoke-base/tokenizer/tokenizer_config.json", 61758),
        ("evoke-base/vae/config.json", 724),
        ("evoke-base/vae/diffusion_pytorch_model.safetensors", 507591892),
        ("evoke/stage3_post_distillation/transformer/config.json", 1067),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00001-of-00012.safetensors",
            4863130760,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00002-of-00012.safetensors",
            4919553296,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00003-of-00012.safetensors",
            4919506272,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00004-of-00012.safetensors",
            4919553368,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00005-of-00012.safetensors",
            4919506368,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00006-of-00012.safetensors",
            4919553392,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00007-of-00012.safetensors",
            4919506368,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00008-of-00012.safetensors",
            4919553392,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00009-of-00012.safetensors",
            4919506368,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00010-of-00012.safetensors",
            4919553392,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00011-of-00012.safetensors",
            4919506368,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model-00012-of-00012.safetensors",
            3191392904,
        ),
        (
            "evoke/stage3_post_distillation/transformer/diffusion_pytorch_model.safetensors.index.json",
            97784,
        ),
    ],
)

ENTRIES = [
    {
        "id": "world-walk",
        "label": "Walk Into a Picture",
        "blurb": "Give it a picture and a few moves, and it keeps drawing what "
        "you would see as you walk on. An approximation made with the video "
        "engine this app already has, so it is slow but runs here.",
        "tier": "compact",
        "engine": "world:walk-sd",
        "parts": [_VACE_13B, _UMT5, _WAN21_VAE],
        "settings": {
            "width": 512,
            "height": 288,
            "frames": 17,
            "fps": 16,
            "steps": 12,
            "cfg_scale": 5.0,
            "sampler": "euler",
            "flow_shift": 3.0,
            "seed": -1,
            "sd_args": ["--offload-to-cpu", "--diffusion-fa", "--vae-tiling"],
        },
        "notes": "Wan2.1 VACE 1.3B Q8_0 (calcuis repo listed in sd.cpp "
        "docs/wan.md) + umt5 Q4_K_M + Wan2.1 VAE, run by the sd CLI in vid_gen "
        "mode. Each step warps the current frame along the camera moves "
        "(zoom/shift, grey where unknown) into a control video, then VACE "
        "redraws it; the last frame starts the next step. Not a real world "
        "model: no 3D memory, no parallax. Settings are reasoned for the Iris "
        "Xe and untimed.",
    },
    {
        "id": "inspatio-world-1.5",
        "label": "Real Walk-Through World",
        "blurb": "A true world model: it turns one picture into a walk you "
        "steer, keeping the scene steady as you move. Made for big graphics "
        "cards; here it would need a special setup and run very slowly.",
        "tier": "big",
        "engine": "world:inspatio",
        "parts": [
            _code(
                "inspatio/inspatio-world-v1.5",
                "dd3561f544053fe22d739b6b2f8461c9c97bf8cb",
                59831747,
                "inspatio-world",
            ),
            *_INSPATIO_DIT,
            *_INSPATIO_WAN,
            *_INSPATIO_DEPTH,
        ],
        "settings": {"width": 832, "height": 480, "frames": 81, "fps": 16},
        "notes": "InSpatio-World 1.5 (Apache-2.0), Wan2.1-T2V-1.3B based causal "
        "4-step model with depth-warp conditioning (in_dim 36). Needs Wan2.1 "
        "T2V 1.3B text encoder/VAE/tokenizer and Depth-Anything-3 NESTED "
        "GIANT-LARGE (CC-BY-NC-4.0). Upstream code exits without CUDA "
        "(inference.py); CPU use needs a patch, see docs/WORLDS.md. First run "
        "converts the T5 .pth to safetensors (another 11 GB).",
    },
    {
        "id": "worldcrafter-fast",
        "label": "Explorer World",
        "blurb": "Walks a camera through a world made from one picture or a "
        "prompt, and remembers what it has shown. Far too heavy for this "
        "laptop; listed so you know it exists.",
        "tier": "big",
        "engine": "world:worldcrafter",
        "parts": [
            _code(
                "TencentARC/WorldCrafter",
                "c2240fc4a9c3edbc8a07258c22f615a8eba0a839",
                30565917,
                "worldcrafter",
            ),
            *_WORLDCRAFTER_FAST,
        ],
        "notes": "TencentARC WorldCrafter-Fast: Wan2.2 A14B-sized two-expert "
        "transformer + camera adapters + repencoder, bf16. Needs an NVIDIA GPU "
        "(README: CUDA 12.8, flash-attn-3, xformers). Too big for the disk.",
    },
    {
        "id": "evoke",
        "label": "Steerable World",
        "blurb": "A world you steer like a game, where you can also add events "
        "by typing them. Built for several large graphics cards; listed so "
        "you know it exists.",
        "tier": "big",
        "engine": "world:evoke",
        "parts": [
            _code(
                "AlayaLab/Evoke",
                "1d271be45128bbda4263e9e3c7dfc8f6ba260492",
                133506293,
                "evoke",
            ),
            *_EVOKE,
        ],
        "notes": "Evoke (Apache-2.0), 14B post-distill model (3 steps, "
        "CFG-free) + base text encoder/VAE. README pins torch 2.4 cu124, "
        "flash-attn 2.8.3, deepspeed; interactive UI quoted on five H200s.",
    },
]
