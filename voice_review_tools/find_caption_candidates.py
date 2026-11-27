"""Find candidate captions for exported voices by scanning story resources.
Run from GkmasObjectManager with uv run <script> --help.
Creates a separate evidence CSV; never modifies existing captions or audio.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--voices', type=Path, default=Path('shro_voices'))
    p.add_argument('--output', type=Path, default=Path('caption_candidates.csv'))
    p.add_argument('--limit', type=int, default=0, help='Maximum number of story files to inspect; 0 means all')
    p.add_argument('--delay', type=float, default=0.2, help='Seconds between requests (default 0.2)')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if not args.voices.is_dir(): p.error(f'No voice directory: {args.voices}')
    if args.limit < 0 or args.delay < 0: p.error('limit and delay must be nonnegative')
    sys.path.insert(0, str(Path.cwd()))
    import GkmasObjectManager as gom
    from GkmasObjectManager.media.dummy import GkmasDummyMedia
    targets = {}
    for path in args.voices.rglob('captions.csv'):
        with path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('caption_status') != 'not_applicable' or row.get('text', '').strip(): continue
                name = Path(row['filename']).stem
                targets.setdefault(name, []).append(str(path.parent / row['filename']))
    print(f'Uncaptioned voice IDs: {len(targets)}', flush=True)
    if not targets: return 0
    manifest = gom.fetch()
    stories = [o for o in manifest.resources if o.name.startswith('adv_') and o.name.endswith('.txt')]
    if args.limit: stories = stories[:args.limit]
    print(f'Story files to scan: {len(stories)}, source bytes: {sum(o.size for o in stories) / 1024**2:.1f} MiB', flush=True)
    if args.dry_run: return 0
    if args.output.exists(): p.error(f'Output already exists: {args.output}; choose another name')
    GkmasDummyMedia.ENABLE_CACHE = False
    errors = []
    hits = 0
    with args.output.open('x', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['voice_id', 'audio_path', 'candidate_text', 'scenario', 'note'])
        out.flush()
        for i, obj in enumerate(stories, 1):
            print(f'[{i}/{len(stories)}] {obj.name}', flush=True)
            try:
                obj._reporter.register()
                commands = obj.media.commands
                commands = sorted((c for c in commands if c.get('cmd') in ('message', 'voice')), key=lambda c:c['clip']['_startTime'])
                # Record the raw message text for review; no assertion that it is spoken verbatim.
                for a, b in zip(commands, commands[1:]):
                    voice = b.get('voice', '')
                    if a.get('cmd') != 'message' or b.get('cmd') != 'voice' or voice not in targets: continue
                    text = a.get('text', '').strip()
                    if not text: continue
                    for audio_path in targets[voice]:
                        writer.writerow([voice, audio_path, text, obj.name, 'candidate: verify against audio'])
                        hits += 1
                out.flush()
            except Exception as exc:
                errors.append({'scenario':obj.name, 'error':str(exc)})
                print(f'  ERROR: {exc}', file=sys.stderr, flush=True)
            if args.delay: time.sleep(args.delay)
    if errors:
        error_path = args.output.with_suffix('.errors.json')
        error_path.write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Errors written to {error_path}', file=sys.stderr)
    print(f'Finished: {hits} candidate rows; {len(errors)} failed scenarios. Verify each candidate against audio.')
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(main())
