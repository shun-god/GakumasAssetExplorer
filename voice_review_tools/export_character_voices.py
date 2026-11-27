"""Export character voices using GkmasObjectManager from the current directory.

Run from the GkmasObjectManager repository with `uv run <this-script> --help`.
Story archives may contain several speakers; every story archive must be checked.
"""
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character', default='shro', help='Character identifier (default: shro)')
    parser.add_argument('--output', type=Path, default=Path('shro_voices'), help='Output directory')
    parser.add_argument('--include-adv', action='store_true', help='Scan ALL story voice archives (large download)')
    parser.add_argument('--dry-run', action='store_true', help='Show candidate counts and bytes without downloading audio')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9]+', args.character):
        parser.error('character must contain only lowercase letters and digits')

    # uv run executes this script from another directory; import the local repository.
    sys.path.insert(0, str(Path.cwd()))
    try:
        import GkmasObjectManager as gom
        from GkmasObjectManager.media.dummy import GkmasDummyMedia
    except ImportError as exc:
        parser.error(f'Run from the GkmasObjectManager repository with its uv environment: {exc}')

    print('Fetching latest manifest...', flush=True)
    manifest = gom.fetch()
    voices = [o for o in manifest.resources if o.name.startswith('sud_vo_')]
    regular = [o for o in voices if not o.name.startswith('sud_vo_adv_') and args.character in o.name]
    story = [o for o in voices if o.name.startswith('sud_vo_adv_')] if args.include_adv else []
    candidates = regular + story
    size = sum(o.size for o in candidates)
    print(f'Manifest revision: {manifest.revision}; regular: {len(regular)}; story archives: {len(story)}')
    print(f'Candidate source data: {size / 1024**3:.2f} GiB (converted output and temporary files require additional space).')
    if not args.include_adv:
        print('Story voices excluded. Add --include-adv to scan all story archives.')
    if args.dry_run or not candidates:
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / '.completed.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('Invalid .completed.json')
    # Avoid retaining all prior source/converted bytes in memory.
    GkmasDummyMedia.ENABLE_CACHE = False
    failures = []
    ambiguous = []
    for index, obj in enumerate(candidates, 1):
        key = f'captions-v1:{obj.name}:{obj.md5}'
        if key in state:
            print(f'[{index}/{len(candidates)}] Skipping completed {obj.name}', flush=True)
            continue
        print(f'[{index}/{len(candidates)}] Processing {obj.name}', flush=True)
        try:
            data = obj.get_data(audio_format='wav')
            blob = data['bytes']
            is_story = obj.name.startswith('sud_vo_adv_')
            selected = []
            if data['mimetype'] == 'application/zip':
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    for member in archive.infolist():
                        filename = Path(member.filename.replace('\\', '/')).name
                        if member.is_dir() or not filename.lower().endswith('.wav'):
                            continue
                        # Same speaker rule used by the repository's dataset script.
                        speaker = Path(filename).stem.split('_')[-1].split('-')[0]
                        if not is_story or speaker == args.character:
                            selected.append((filename, archive.read(member)))
            elif is_story:
                # A single WAV loses the internal stream name, so speaker is unknown.
                ambiguous.append(obj.name)
                print('  Skipped: single story WAV has no verifiable speaker identifier.')
            else:
                selected.append((Path(obj.name).stem + '.wav', blob))
            captions = {}
            caption_status = 'not_applicable'
            if is_story and selected:
                scenario_name = obj.name.removeprefix('sud_vo_').removesuffix('.acb') + '.txt'
                try:
                    scenario = manifest.resources[scenario_name]
                except KeyError:
                    caption_status = 'scenario_not_found'
                else:
                    # Same scenario and caption map used by the browser endpoint.
                    scenario._reporter.register()
                    captions = scenario.media.caption_map
                    caption_status = 'loaded'
            dest = args.output / Path(obj.name).stem
            if selected:
                dest.mkdir(parents=True, exist_ok=True)
                for filename, content in selected:
                    target = dest / filename
                    if target.exists():
                        if target.read_bytes() != content:
                            raise FileExistsError(f'Existing file differs: {target}')
                    else:
                        target.write_bytes(content)
                # Keep blanks so missing captions can be filled in by hand.
                with (dest / 'captions.csv').open('w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['filename', 'text', 'caption_status'])
                    for filename, _ in selected:
                        stem = Path(filename).stem
                        full_key = stem if stem.startswith(Path(obj.name).stem + '_') else Path(obj.name).stem + '_' + stem
                        caption = captions.get(full_key, '')
                        status = 'matched' if caption else ('not_found' if caption_status == 'loaded' else caption_status)
                        writer.writerow([filename, caption, status])
            # Ambiguous archives are recorded separately and remain eligible for retry.
            if is_story and data['mimetype'] != 'application/zip':
                continue
            state[key] = len(selected)
            temporary = state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(state_path)
            print(f'  Saved {len(selected)} WAV file(s).', flush=True)
        except Exception as exc:
            failures.append((obj.name, str(exc)))
            print(f'  ERROR: {exc}', file=sys.stderr, flush=True)
    print(f'Finished: {len(failures)} error(s), {len(ambiguous)} story archive(s) with unknown speaker.')
    for name in ambiguous:
        print(f'  Unknown speaker: {name}')
    for name, error in failures:
        print(f'  Failed: {name}: {error}', file=sys.stderr)
    return 1 if failures or ambiguous else 0


if __name__ == '__main__':
    raise SystemExit(main())
