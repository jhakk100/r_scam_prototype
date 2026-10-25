"""Losslessly compress the verified offline folder into Git LFS-sized parts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'bootstrap-libs'))
import zstandard


class PartsWriter:
    def __init__(self, folder, limit):
        self.folder, self.limit = folder, limit
        self.parts, self.handle, self.used = [], None, 0
        self.digest = None
        self.total = 0
        self.overall = hashlib.sha256()

    def finish_part(self):
        if self.handle:
            self.handle.close()
            self.parts.append({'file': self.name, 'bytes': self.used, 'sha256': self.digest.hexdigest()})
            print('Completed compressed part', self.name, self.used, flush=True)
            self.handle = None

    def write(self, data):
        view = memoryview(data)
        original = len(view)
        while view:
            if self.handle is None:
                self.name = f'maeum-check.tar.zst.part{len(self.parts)+1:04d}'
                self.handle = (self.folder / self.name).open('wb')
                self.used, self.digest = 0, hashlib.sha256()
            count = min(len(view), self.limit - self.used)
            block = view[:count]
            self.handle.write(block)
            self.digest.update(block)
            self.overall.update(block)
            self.used += count
            self.total += count
            view = view[count:]
            if self.used == self.limit:
                self.finish_part()
        return original

    def flush(self):
        if self.handle:
            self.handle.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--level', type=int, default=12)
    parser.add_argument('--part-bytes', type=int, default=1800000000)
    args = parser.parse_args()
    source = args.source.resolve()
    folder = HERE / 'payload'
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit('Payload folder is not empty; existing parts are preserved.')
    folder.mkdir(exist_ok=True)
    files = sorted(p for p in source.rglob('*') if p.is_file()
                   and 'runtime' not in p.relative_to(source).parts
                   and '__pycache__' not in p.relative_to(source).parts)
    writer = PartsWriter(folder, args.part_bytes)
    total_raw = sum(p.stat().st_size for p in files)
    done = 0
    started = time.monotonic()
    last = 0
    with zstandard.ZstdCompressor(level=args.level, threads=4).stream_writer(writer, closefd=False) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', bufsize=1024*1024, copybufsize=8*1024*1024) as archive:
            for path in files:
                relative = path.relative_to(source).as_posix()
                info = archive.gettarinfo(str(path), arcname=relative)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mtime = 0
                info.pax_headers = {}
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
                done += path.stat().st_size
                elapsed = time.monotonic() - started
                if elapsed - last >= 15 or done == total_raw:
                    print(f'Compressed input {done}/{total_raw} bytes; output {writer.total} bytes; {elapsed:.0f}s', flush=True)
                    last = elapsed
    writer.finish_part()
    sidecars = []
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.parts[0] == 'runtime' or 'runtime' not in relative.parts or '__pycache__' in relative.parts:
            continue
        dest = folder/'configuration'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        sidecars.append({'file':dest.relative_to(folder).as_posix(), 'target':relative.as_posix(),
                         'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {'format': 'tar.zstd.parts.v1', 'compression': 'zstd', 'sidecar_files':sidecars,
                'zstandard_version': zstandard.__version__, 'uncompressed_file_bytes': total_raw,
                'archive_file_count': len(files), 'compressed_bytes': writer.total,
                'archive_sha256': writer.overall.hexdigest(), 'parts': writer.parts,
                'bundle_manifest_sha256': hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()}
    (folder/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':'PACKAGED','compressed_bytes':writer.total,'parts':len(writer.parts)}), flush=True)


if __name__ == '__main__':
    main()
