from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from offline_evaluation.experiments.artifacts import (
    file_metadata,
    verify_outputs,
    write_json,
)


class ArtifactTests(SimpleTestCase):
    def test_written_json_can_be_checksum_verified(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "result.json"
            write_json(path, {"value": "周杰伦"})

            verify_outputs(directory, {"result.json": file_metadata(path)})

            self.assertFalse((directory / "result.json.tmp").exists())
