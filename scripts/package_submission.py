"""Build the local source handoff without credentials or generated workspaces."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('README.md', 'run_demo.py', 'requirements.txt', 'Start-Mutabi.ps1',
              '.env.example', '.gitignore', 'TEST_CASES.md')
SOURCE_DIRS = ('mutabi', 'data/demo', 'tests', 'evaluation', 'scripts', 'docs')
SUFFIXES = {'.py', '.js', '.css', '.html', '.csv', '.json', '.md', '.txt', '.png', '.jpg'}


def main():
    files = [ROOT / name for name in ROOT_FILES]
    for directory in SOURCE_DIRS:
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and path.suffix.lower() in SUFFIXES and '__pycache__' not in path.parts:
                files.append(path)
    files = sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())
    for path in files:
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
            raise ValueError('Source entries must be regular files within the repository')
    destination = ROOT / 'deliverables'
    destination.mkdir(exist_ok=True)
    archive = destination / 'mutabi-source.zip'
    manifest = []
    with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            output.writestr('mutabi-source/' + relative, data)
            manifest.append({'path': relative, 'bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest()})
    with ZipFile(archive) as source:
        if source.testzip() is not None:
            raise ValueError('Source archive failed its integrity check')
    report = {'archive': archive.name, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'file_count': len(files), 'files': manifest,
              'excludes': ['.env and credentials', '.venv and installed dependencies',
                           'runtime databases, recordings and sessions', '.git', 'video exports']}
    (destination / 'mutabi-source-manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'file_count': len(files),
                      'size_mb': round(archive.stat().st_size / 1000000, 2), 'sha256': report['archive_sha256']}))


if __name__ == '__main__':
    main()
