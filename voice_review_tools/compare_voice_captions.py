"""Transcribe uncaptioned WAVs locally and compare with scenario text candidates.
Writes a review CSV. Never edits source WAVs or captions.csv.
"""
import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def normalized(s):
    s = unicodedata.normalize('NFKC', s).replace('\\n', '')
    return ''.join(c for c in s if c.isalnum())


def similarity(a, b):
    a, b = normalized(a), normalized(b)
    if not a or not b: return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--voices', type=Path, default=Path('shro_voices'))
    p.add_argument('--candidates', type=Path, default=Path('caption_candidates.csv'))
    p.add_argument('--output', type=Path, default=Path('transcription_review.csv'))
    p.add_argument('--model', default='small', help='faster-whisper model name or local model directory')
    p.add_argument('--limit', type=int, default=10, help='Maximum WAVs to transcribe; 0 means all (default 10)')
    p.add_argument('--candidates-only', action='store_true', help='Only WAVs that have candidate text')
    args = p.parse_args()
    if args.limit < 0: p.error('--limit must be >= 0')
    if not args.voices.is_dir(): p.error(f'Voice folder not found: {args.voices}')
    if not args.candidates.is_file(): p.error(f'Candidate CSV not found: {args.candidates}')
    if args.output.exists(): p.error(f'Output exists: {args.output}; specify a new --output')
    candidates = defaultdict(list)
    with args.candidates.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            candidates[row['voice_id']].append((row['candidate_text'], row['scenario']))
    targets = []
    for path in sorted(args.voices.rglob('captions.csv')):
        with path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('text', '').strip() or row.get('caption_status') != 'not_applicable': continue
                filename = Path(row['filename']).name
                wav = path.parent / filename
                if args.candidates_only and wav.stem not in candidates: continue
                targets.append(wav)
    if args.limit: targets = targets[:args.limit]
    print(f'WAVs to process: {len(targets)}; model: {args.model} (CPU)', flush=True)
    if not targets: return 0
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        p.error('faster-whisper is missing. Use uv run --with faster-whisper <script>')
    model = WhisperModel(args.model, device='cpu', compute_type='int8')
    errors = 0
    with args.output.open('x', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['filename','audio_path','asr_text','candidate_text','similarity','scenario','status'])
        out.flush()
        for i, wav in enumerate(targets,1):
            print(f'[{i}/{len(targets)}] {wav}',flush=True)
            try:
                segments, _ = model.transcribe(str(wav), language='ja', beam_size=5, condition_on_previous_text=False)
                transcript = ''.join(seg.text for seg in segments).strip()
                matches = candidates.get(wav.stem, [])
                if matches:
                    for text, scenario in sorted(matches, key=lambda x: similarity(transcript,x[0]), reverse=True):
                        writer.writerow([wav.name,str(wav),transcript,text,f'{similarity(transcript,text):.3f}',scenario,'review_required'])
                else:
                    writer.writerow([wav.name,str(wav),transcript,'','','','no_candidate_review_required'])
            except Exception as exc:
                errors += 1
                writer.writerow([wav.name,str(wav),'','','','',f'error: {exc}'])
                print(f' ERROR: {exc}',file=sys.stderr,flush=True)
            out.flush()
    print(f'Finished: {len(targets)} WAVs, {errors} error(s); results need listening review.')
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(main())
