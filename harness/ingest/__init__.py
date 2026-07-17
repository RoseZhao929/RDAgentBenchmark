"""Per-dataset ingest adapters producing CanonicalCase."""

from harness.ingest.phenopacket_store import (
    ingest_phenopacket_store,
    phenopacket_to_canonical,
)
from harness.ingest.rarearena import (
    ingest_rarearena,
    rarearena_record_to_canonical,
    RareArenaSubset,
)
from harness.ingest.rarebench import (
    ingest_rarebench,
    rarebench_record_to_canonical,
    RareBenchSplit,
)

__all__ = [
    # Phenopacket-Store
    "ingest_phenopacket_store",
    "phenopacket_to_canonical",
    # RareArena
    "ingest_rarearena",
    "rarearena_record_to_canonical",
    "RareArenaSubset",
    # RareBench
    "ingest_rarebench",
    "rarebench_record_to_canonical",
    "RareBenchSplit",
]
