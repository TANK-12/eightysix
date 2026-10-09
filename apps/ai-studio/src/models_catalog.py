"""Pre-rebuild name for the model catalog, kept so old imports still work.

The catalog itself is the declarative ``catalog/`` package now; add models
there, not here.
"""

from catalog import (  # noqa: F401
    CATALOG,
    DEFAULT_MODEL_ID,
    LCM_LORA_FILENAME,
    LCM_LORA_NAME,
    LCM_LORA_URL,
)
