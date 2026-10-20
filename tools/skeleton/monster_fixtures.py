"""Make tests/fixtures/monsters/*.npz from the Clean step's outputs (positions and triangles
only, seams welded, float32/uint16) so the unit tests run on the real bake-off monsters.

    python tools/skeleton/monster_fixtures.py MODELS_CLEAN_OUT_DIR
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from asset_forge.skeleton.glb import read_mesh  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "monsters"


def main(src: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for gen in ("hi3dgen", "triposg"):
        for name in ("spider", "brute"):
            v, f = read_mesh(src / gen / name / "clean.glb")
            u, inv = np.unique(np.round(v, 5), axis=0, return_inverse=True)
            np.savez_compressed(OUT / f"{gen}_{name}.npz", v=u.astype(np.float32),
                                f=inv.reshape(-1)[f].astype(np.uint16))
            print(gen, name, len(u), "points")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
