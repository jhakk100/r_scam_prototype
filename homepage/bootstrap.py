"""Restore the complete offline application from verified Git LFS parts."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'bootstrap-libs'))
import zstandard


def update_application(output):
    """Apply small tracked app updates without repackaging unchanged model weights."""
    names = ['server.py', 'community.py', 'verify_community.py', 'app/index.html', 'app/app.js',
             'app/input.js', 'app/community.js', 'app/style.css', 'standalone-guide.md']
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    changed = False
    for name in names:
        relative = '읽어주세요.md' if name == 'standalone-guide.md' else name
        source, target = HERE / name, output / relative
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.update')
            temporary.write_bytes(data)
            temporary.replace(target)
        row = {'bytes': len(data), 'sha256': digest,
               'category': 'documentation' if name == 'standalone-guide.md' else
                           'web_assets' if name.startswith('app/') else 'application'}
        if manifest['files'].get(relative) != row:
            manifest['files'][relative] = row
            changed = True
    if changed:
        manifest['application_source'] = 'homepage tracked source; model payload unchanged'
        temporary = manifest_path.with_suffix('.json.update')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(manifest_path)


class PartsReader(io.RawIOBase):
    def __init__(self, parts):
        self.parts = iter(parts)
        self.handle = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.handle is None:
                try:
                    self.handle = next(self.parts).open('rb')
                except StopIteration:
                    return 0
            count = self.handle.readinto(buffer)
            if count:
                return count
            self.handle.close()
            self.handle = None

    def close(self):
        if self.handle:
            self.handle.close()
        super().close()


def main():
    payload = HERE / 'payload'
    manifest_bytes = (payload/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    identity = hashlib.sha256(manifest_bytes).hexdigest()
    output = HERE / '실행묶음'
    ready = output / '.payload-ready'
    if ready.is_file() and ready.read_text(encoding='ascii') == identity:
        update_application(output)
        print('Offline application is ready.', flush=True)
        return
    if manifest['format'] != 'tar.zstd.parts.v1':
        raise ValueError('Unsupported application payload.')
    paths = []
    overall = hashlib.sha256()
    for row in manifest['parts']:
        path = (payload/row['file']).resolve()
        if not path.is_relative_to(payload.resolve()) or not path.is_file():
            raise ValueError('Missing application part. Run git lfs pull in the downloaded repository.')
        if path.stat().st_size != row['bytes']:
            raise ValueError('Git LFS data is missing or incomplete. Run: git lfs pull --include="homepage/payload/*"')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8*1024*1024), b''):
                digest.update(block)
                overall.update(block)
        if digest.hexdigest() != row['sha256']:
            raise ValueError('Application part checksum mismatch: '+row['file'])
        paths.append(path)
        print('Verified', row['file'], flush=True)
    if overall.hexdigest() != manifest['archive_sha256']:
        raise ValueError('Compressed archive checksum mismatch.')
    output.mkdir(exist_ok=True)
    extracted = {}
    print('Restoring the offline application. This runs only on first start...', flush=True)
    with PartsReader(paths) as raw, zstandard.ZstdDecompressor().stream_reader(raw) as decoded:
        with tarfile.open(fileobj=decoded, mode='r|', bufsize=1024*1024) as archive:
            for member in archive:
                if not member.isfile():
                    raise ValueError('Only regular files are allowed in the application archive.')
                target = (output/member.name).resolve()
                if not target.is_relative_to(output.resolve()):
                    raise ValueError('Archive path escapes the application folder.')
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.extractfile(member) as source, target.open('wb') as dest:
                    for block in iter(lambda: source.read(8*1024*1024), b''):
                        dest.write(block)
                        digest.update(block)
                extracted[member.name] = digest.hexdigest()
                if len(extracted) % 1000 == 0:
                    print('Restored files:', len(extracted), flush=True)
    for row in manifest.get('sidecar_files', []):
        source = (payload/row['file']).resolve()
        target = (output/row['target']).resolve()
        if not source.is_relative_to(payload.resolve()) or not target.is_relative_to(output.resolve()):
            raise ValueError('Configuration path escapes the application folder.')
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != row['bytes'] or digest != row['sha256']:
            raise ValueError('Configuration checksum mismatch: '+row['file'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        extracted[row['target']] = digest
    bundled_manifest_bytes = (output/'manifest.json').read_bytes()
    if hashlib.sha256(bundled_manifest_bytes).hexdigest() != manifest['bundle_manifest_sha256']:
        raise ValueError('Restored manifest checksum mismatch.')
    bundled = json.loads(bundled_manifest_bytes)
    for name, row in bundled['files'].items():
        if extracted.get(name) != row['sha256']:
            raise ValueError('Restored file checksum mismatch: '+name)
    ready.write_text(identity, encoding='ascii')
    report = {'status':'PASSED','restored_files':len(extracted),
              'verified_bundle_files':len(bundled['files']),'payload_sha256':identity,
              'all_restored_hashes_match':True}
    (output/'runtime').mkdir(exist_ok=True)
    (output/'runtime/payload-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    update_application(output)
    print('Offline application restored and verified.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Setup failed:', exc, file=sys.stderr)
        raise SystemExit(1)
