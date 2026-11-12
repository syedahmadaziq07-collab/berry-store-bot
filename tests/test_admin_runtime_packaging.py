"""Verify local imports, including function-local imports, ship in the admin image.

No application modules are imported: inspecting bot.py must never start a bot.
This check targets the explicit flat Python COPY manifest in Dockerfile.admin.
"""
import ast
from pathlib import Path
import shlex
import unittest

ROOT = Path(__file__).resolve().parents[1]


def missing_runtime_modules(root):
    copied = set()
    for line in (root / 'Dockerfile.admin').read_text().splitlines():
        parts = shlex.split(line)
        if not parts or parts[0].upper() != 'COPY' or any(p.startswith('--from=') for p in parts):
            continue
        copied.update(p for p in parts[1:-1] if p.endswith('.py'))
    if not copied:
        raise AssertionError('Admin Python COPY manifest is empty')
    missing = set()
    for source in copied:
        for node in ast.walk(ast.parse((root / source).read_text(), filename=source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                dependency = name.split('.')[0] + '.py'
                if (root / dependency).is_file() and dependency not in copied:
                    missing.add((source, dependency))
    return sorted(missing)


class AdminRuntimePackagingTests(unittest.TestCase):
    def test_all_local_runtime_imports_are_shipped(self):
        self.assertEqual(missing_runtime_modules(ROOT), [],
                         'Dockerfile.admin omits a local Python dependency')

    def test_packaged_workers_run_without_repository_modules(self):
        # Execute worker contracts from the deployed Python manifest only.
        # Repository root is absent from cwd/PYTHONPATH; provider traffic is mocked.
        import os
        import shutil
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            for line in (ROOT / 'Dockerfile.admin').read_text().splitlines():
                parts = shlex.split(line)
                if not parts or parts[0].upper() != 'COPY' or any(p.startswith('--from=') for p in parts):
                    continue
                for source in parts[1:-1]:
                    if source.endswith('.py'):
                        shutil.copy2(ROOT / source, bundle / Path(source).name)
            for suite in ('test_staging_job_worker.py', 'test_video_myr_worker.py'):
                result = subprocess.run(
                    [sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-p', suite, '-q'],
                    cwd=bundle, env=dict(os.environ, PYTHONPATH=str(bundle)),
                    capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
