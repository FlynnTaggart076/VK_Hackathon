"""The published check must reject an internally inconsistent fixture."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "packages" / "housing_engine" / "verify_contract.py"
FIXTURES = ROOT / "fixtures" / "receipts"


class ContractVerifierTest(unittest.TestCase):
    def test_changed_charge_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            for fixture in FIXTURES.glob("*.json"):
                shutil.copy2(fixture, destination / fixture.name)
            august = destination / "water-2026-08.json"
            data = json.loads(august.read_text(encoding="utf-8"))
            data["services"][0]["charge_amount"] = "201.00"
            august.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VERIFIER)],
                env={**os.environ, "ENGINE_FIXTURES_DIR": str(destination)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AssertionError", result.stderr)


if __name__ == "__main__":
    unittest.main()
