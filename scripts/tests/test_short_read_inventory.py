import gzip
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "short_read_inventory.py"
spec = importlib.util.spec_from_file_location("short_read_inventory", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fastq(lengths):
    return "".join(f"@read{i}\n{'A' * n}\n+\n{'I' * n}\n"
                   for i, n in enumerate(lengths))


class ShortReadInventoryTests(unittest.TestCase):
    def test_pipeline_trigger_with_long_contig_and_short_reads(self):
        shell = os.environ.get("BASH", "bash")
        pipeline = SCRIPT.with_name("sample_steps.sh").read_text(encoding="utf-8")
        block = pipeline.split("TRIGGER_RESCUE=0\n", 1)[1].split(
            'if [[ $TRIGGER_RESCUE -eq 1 && "$INPUT_MODE" == "READS" ]]; then', 1)[0]
        for mode, count, max_length, manual, expected in [
            ("READS", 1, 1000, 0, 1), ("READS", 0, 1000, 0, 0),
            ("READS", 0, 100, 0, 1), ("CONTIGS", 0, 100, 0, 0),
            ("READS", 0, 1000, 1, 1),
        ]:
            with self.subTest(mode=mode, short_reads=count, manual=manual):
                setup = (f'INPUT_MODE={mode}; MOCK_SHORT_COUNT={count}; SHORT_READ_COUNT={count}; '
                         f'max_contig_len={max_length}; RESCUE_MODE={manual}; '
                         'ASSEMBLY_FAILED=0; SAMPLE_SINGLE=input.fq; '
                         'WORK_ROOT=unused; SAMPLE_NAME=sample; SCRIPT_DIR=unused; '
                         'TRIGGER_RESCUE=0; python3() { echo "$MOCK_SHORT_COUNT"; }; '
                         'log_fatal() { exit 99; };\n')
                result = subprocess.run([shell, "-c", setup + block +
                                         '\nprintf "RESULT=%s" "$TRIGGER_RESCUE"'],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.endswith(f"RESULT={expected}"), result.stdout)

    def test_boundaries_and_long_background(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.fq"
            path.write_text(fastq([19, 20, 34, 35, 54, 55, 74, 75, 100, 101, 1000]))
            result = module.inventory([path])
            self.assertEqual(result["short_read_count"], 8)
            self.assertEqual(result["inputs"][0]["reads_by_length"],
                             {"below_20": 1, "20_34": 2, "35_54": 2,
                              "55_74": 2, "75_100": 2, "above_100": 2})

    def test_gzip_mates_are_reads_not_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"R{mate}.fq.gz" for mate in (1, 2)]
            for path in paths:
                with gzip.open(path, "wt") as handle:
                    handle.write(fastq([20, 125]))
            self.assertEqual(module.inventory(paths)["short_read_count"], 2)

    def test_empty_filtered_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.fq"
            path.touch()
            self.assertEqual(module.inventory([path])["short_read_count"], 0)

    def test_malformed_input_does_not_publish_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.fq"
            path.write_text(fastq([20]) + "@truncated\nAAAA\n")
            output = Path(directory) / "inventory.json"
            process = subprocess.run([sys.executable, str(SCRIPT), "--fastq", str(path),
                                      "--out", str(output)], capture_output=True)
            self.assertEqual(process.returncode, 1)
            self.assertFalse(output.exists())
            self.assertFalse(list(Path(directory).glob("*.tmp.*")))


if __name__ == "__main__":
    unittest.main()
