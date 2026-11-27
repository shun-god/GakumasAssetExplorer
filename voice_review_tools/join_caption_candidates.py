"""Join uncaptioned voice files with scenario candidates by exact voice ID.
Run from GkmasObjectManager. Existing captions and audio are never modified.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voices', type=Path, default=Path('shro_voices'))
    parser.add_argument('--candidates', type=Path, default=Path('caption_candidates.csv'))
    parser.add_argument('--output', type=Path, default=Path('voice_caption_review.csv'))
    args = parser.parse_args()
    if not args.voices.is_dir(): parser.error(f'Voice directory not found: {args.voices}')
    if not args.candidates.is_file(): parser.error(f'Candidate CSV not found: {args.candidates}')
    if args.output.exists(): parser.error(f'Output exists: {args.output}; specify a different --output')
    candidates = defaultdict(lambda: defaultdict(set))
    with args.candidates.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            voice, text, source = row['voice_id'], row['candidate_text'].strip(), row['scenario']
            if text: candidates[voice][text].add(source)
    result = []
    for caption_path in sorted(args.voices.rglob('captions.csv')):
        with caption_path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('caption_status') not in ('not_applicable', 'not_found', 'scenario_not_found') or row.get('text', '').strip(): continue
                name = Path(row['filename']).name
                voice = Path(name).stem
                found = candidates.get(voice, {})
                result.append({'voice_id': voice, 'audio_path': str(caption_path.parent / name),
                    'caption_status': row['caption_status'], 'candidate_count': len(found),
                    'candidate_texts': '\n\n'.join(f'[{i}] {text}' for i, text in enumerate(sorted(found), 1)),
                    'sources': '\n'.join(f'[{i}] {", ".join(sorted(found[text]))}' for i, text in enumerate(sorted(found), 1)),
                    'verified_text': '', 'review_status': 'needs_listening'})
    with args.output.open('x', encoding='utf-8-sig', newline='') as f:
        fields = ['voice_id','audio_path','caption_status','candidate_count','candidate_texts','sources','verified_text','review_status']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(result)
    matched = sum(r['candidate_count'] > 0 for r in result)
    print(f'Output: {args.output}; {len(result)} audio rows; {matched} with candidates; {len(result)-matched} without candidates.')
    print('Candidate text is context, not a verified transcript. Listen before filling verified_text.')

if __name__ == '__main__':
    main()
