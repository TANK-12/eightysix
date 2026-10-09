"""Video models, run per job by the sd CLI in ``-M vid_gen`` (video_models.py).

Every size_bytes was read from the Hugging Face API (LFS size) on 2026-10-08.
Settings follow the stable-diffusion.cpp docs (wan.md, minimax_h3.md, ltx2.md,
hunyuan_video.md); none has been run on this laptop yet.

Settings keys beyond the image ones: ``frames`` (default length), ``fps``,
``flow_shift``, ``high_noise`` (steps/cfg/sampler for the high-noise expert of
a two-expert model), ``frame_grid`` ((step, offset): frame counts are rounded
up to step*k + offset), ``audio`` (makes its own sound).
"""

from catalog import part

VIDEO_FLAGS = ["--offload-to-cpu", "--diffusion-fa", "--vae-tiling"]

_UMT5 = part(
    "t5xxl",
    "city96/umt5-xxl-encoder-gguf",
    "umt5-xxl-encoder-Q4_K_M.gguf",
    3655145312,
)
_H3_VIDEO_VAE = part(
    "vae",
    "unsloth/MiniMax-H3-GGUF",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    5207808496,
)
_H3_AUDIO_VAE = part(
    "audio_vae",
    "unsloth/MiniMax-H3-GGUF",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    605254808,
)

ENTRIES = [
    {
        "id": "wan2.2-ti2v-5b",
        "label": "Short Clips",
        "blurb": "Turns a prompt, or a still picture, into a few seconds of moving video.",
        "tier": "compact",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "QuantStack/Wan2.2-TI2V-5B-GGUF",
                "Wan2.2-TI2V-5B-Q4_K_M.gguf",
                3433116000,
            ),
            _UMT5,
            part(
                "vae",
                "QuantStack/Wan2.2-TI2V-5B-GGUF",
                "VAE/Wan2.2_VAE.safetensors",
                1409400960,
            ),
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 6.0,
            "sampler": "euler",
            "width": 832,
            "height": 480,
            "frames": 33,
            "fps": 24,
            "flow_shift": 3.0,
            "frame_grid": [4, 1],
        },
        "engine_flags": VIDEO_FLAGS,
        "notes": "Wan2.2 TI2V 5B Q4_K_M + umt5-xxl Q4_K_M + Wan2.2 VAE (the 5B uses "
        "the 2.2 VAE, the 14B ones the 2.1 VAE). cfg 6.0, flow-shift 3.0, 33 "
        "frames per docs/wan.md. The doc warns the Wan VAE needs a lot of VRAM: "
        "--vae-tiling is on.",
    },
    # ---- big models (connected only) ---------------------------------------
    {
        "id": "minimax-h3-small",
        "label": "Video with Sound",
        "blurb": "Makes video together with its own sound, from a prompt or a starting picture.",
        "tier": "big",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "unsloth/MiniMax-H3-GGUF",
                "minimax_h3_fl2va_pruned-Q2_K.gguf",
                6724190304,
            ),
            part(
                "llm",
                "unsloth/MiniMax-H3-GGUF",
                "qwen3vl_32b_minimax_h3-Q2_K_M.gguf",
                13102161024,
            ),
            _H3_VIDEO_VAE,
            _H3_AUDIO_VAE,
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "width": 864,
            "height": 480,
            "frames": 56,
            "fps": 24,
            "frame_grid": [17, 5],
            "audio": True,
        },
        "engine_flags": VIDEO_FLAGS + ["--rng", "cpu"],
        "notes": "MiniMax-H3 FL2VA pruned Q2_K + its Qwen3-VL-32B encoder Q2_K_M + "
        "video VAE fp16 + audio VAE. Tier big although it is the smallest H3: "
        "the four parts are 25.6 GB and with --offload-to-cpu they all sit in "
        "RAM (31 GiB, no swap), so it would likely freeze the laptop. cfg 1.0, "
        "56 frames (17k+5 grid), 24 fps fixed, --rng cpu per docs/minimax_h3.md.",
    },
    {
        "id": "minimax-h3",
        "label": "Video with Sound -- Large",
        "blurb": "A sharper version of Video with Sound.",
        "tier": "big",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "unsloth/MiniMax-H3-GGUF",
                "minimax_h3_fl2va_pruned-Q4_K.gguf",
                11420663904,
            ),
            part(
                "llm",
                "leejet/MiniMax-H3-GGUF",
                "qwen3vl_32b_minimax_h3-Q4_K_M.gguf",
                18218065024,
            ),
            _H3_VIDEO_VAE,
            _H3_AUDIO_VAE,
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "width": 864,
            "height": 480,
            "frames": 56,
            "fps": 24,
            "frame_grid": [17, 5],
            "audio": True,
        },
        "engine_flags": VIDEO_FLAGS + ["--rng", "cpu"],
        "notes": "MiniMax-H3 FL2VA pruned Q4_K + Qwen3-VL-32B Q4_K_M (35 GB of "
        "parts: more than this laptop's RAM).",
    },
    {
        "id": "wan2.2-a14b",
        "label": "Cinematic Clips",
        "blurb": "Higher-quality video clips with steadier motion, but very slow here.",
        "tier": "big",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "QuantStack/Wan2.2-T2V-A14B-GGUF",
                "LowNoise/Wan2.2-T2V-A14B-LowNoise-Q4_K_M.gguf",
                9650090496,
            ),
            part(
                "high_noise_diffusion",
                "QuantStack/Wan2.2-T2V-A14B-GGUF",
                "HighNoise/Wan2.2-T2V-A14B-HighNoise-Q4_K_M.gguf",
                9650090496,
            ),
            _UMT5,
            part(
                "vae",
                "QuantStack/Wan2.2-T2V-A14B-GGUF",
                "VAE/Wan2.1_VAE.safetensors",
                253815318,
            ),
        ],
        "settings": {
            "steps": 10,
            "cfg_scale": 3.5,
            "sampler": "euler",
            "width": 832,
            "height": 480,
            "frames": 33,
            "fps": 16,
            "flow_shift": 3.0,
            "frame_grid": [4, 1],
            "high_noise": {"steps": 8, "cfg_scale": 3.5, "sampler": "euler"},
        },
        "engine_flags": VIDEO_FLAGS,
        "notes": "Wan2.2 T2V A14B low+high noise experts Q4_K_M + umt5 + Wan2.1 "
        "VAE. Settings per docs/wan.md (10 + 8 steps, cfg 3.5, flow-shift 3.0). "
        "Text to video only (the I2V experts are separate files).",
    },
    {
        "id": "ltx-2.5",
        "label": "Fast Video with Sound",
        "blurb": "Long, smooth clips with sound, from a prompt or a starting picture.",
        "tier": "big",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "vantagewithai/LTX-2.5-GGUF",
                "dev/ltx-2.5-22b-dev-transformer-Q4_K_M.gguf",
                15687639424,
            ),
            part(
                "llm",
                "Lightricks/LTX-2.5",
                "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
                26263858182,
                gated=True,
            ),
            part(
                "vae",
                "Lightricks/LTX-2.5",
                "vae/ltx-2.5-video-vae-conv-bf16.safetensors",
                1452269922,
                gated=True,
            ),
            part(
                "audio_vae",
                "Lightricks/LTX-2.5",
                "vae/ltx-2.5-audio-vae-bf16.safetensors",
                364866540,
                gated=True,
            ),
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 3.0,
            "sampler": "euler",
            "width": 1280,
            "height": 720,
            "frames": 121,
            "fps": 24,
            "audio": True,
        },
        "engine_flags": VIDEO_FLAGS,
        "notes": "LTX-2.5 22B dev Q4_K_M + Gemma4-12B encoder bf16 (could be "
        "converted to Q8 once with sd -M convert) + conv video VAE + audio VAE. "
        "Lightricks repo is gated (Hugging Face sign-in). cfg 3.0, 121 frames per "
        "docs/ltx2.md. 44 GB of parts.",
    },
    {
        "id": "hunyuanvideo-1.5",
        "label": "Detailed Video",
        "blurb": "Detailed, true-to-prompt video clips, very slow on this laptop.",
        "tier": "big",
        "engine": "sd-video",
        "engine_build": "next",
        "parts": [
            part(
                "diffusion",
                "Comfy-Org/HunyuanVideo_1.5_repackaged",
                "split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_fp16.safetensors",
                16653368128,
            ),
            part(
                "llm",
                "mradermacher/Qwen2.5-VL-7B-Instruct-GGUF",
                "Qwen2.5-VL-7B-Instruct.Q4_K_M.gguf",
                4683072512,
            ),
            part(
                "t5xxl",
                "Comfy-Org/HunyuanVideo_1.5_repackaged",
                "split_files/text_encoders/byt5_small_glyphxl_fp16.safetensors",
                438643184,
            ),
            part(
                "vae",
                "Comfy-Org/HunyuanVideo_1.5_repackaged",
                "split_files/vae/hunyuanvideo15_vae_fp16.safetensors",
                2521292758,
            ),
        ],
        "settings": {
            "steps": 20,
            "cfg_scale": 6.0,
            "sampler": "euler",
            "width": 848,
            "height": 480,
            "frames": 33,
            "fps": 24,
            "frame_grid": [4, 1],
        },
        "engine_flags": VIDEO_FLAGS,
        "notes": "HunyuanVideo 1.5 480p T2V fp16 + Qwen2.5-VL-7B Q4_K_M + byT5 glyph "
        "encoder (passed as --t5xxl, as docs/hunyuan_video.md does) + its VAE. "
        "cfg 6.0, 33 frames per the doc (which shows 720p; 480p chosen here).",
    },
]
