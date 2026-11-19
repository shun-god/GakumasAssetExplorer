"""Export character WAV tracks and captions into per-archive folders."""

import csv
import json
import re
import sys
from argparse import ArgumentParser
from fnmatch import fnmatchcase
from pathlib import Path
from tempfile import TemporaryDirectory

import GkmasObjectManager as gom
from GkmasObjectManager.const import CHARACTER_ABBREVS
from GkmasObjectManager.utils import nocache


CAPTION_FIELDS = ("filename", "text", "caption_status")
ADVENTURE_PREFIX = "sud_vo_adv_"


def output_matches(folder: Path, count: int) -> bool:
    if count == 0:
        return not folder.exists()
    try:
        with (folder / "captions.csv").open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != list(CAPTION_FIELDS):
                return False
            names = [row["filename"] for row in reader]
        return (
            len(names) == len(set(names)) == count
            and set(names) == {wav.name for wav in folder.glob("*.wav") if wav.is_file()}
            and all((folder / name).stat().st_size > 0 for name in names)
        )
    except (OSError, UnicodeError, csv.Error):
        return False


def save_checkpoint(path: Path, completed: dict[str, int]) -> None:
    with TemporaryDirectory(dir=path.parent) as temporary:
        pending = Path(temporary) / path.name
        pending.write_text(json.dumps(completed, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)


@nocache
def read_archive(resource, resources, characters):
    stem = Path(resource.name).stem
    adventure = stem.startswith(ADVENTURE_PREFIX)
    segments = resource.media.read_named_segments()
    tracks = {character: [] for character in characters}
    if adventure:
        cue_pattern = re.compile(rf"{re.escape(stem)}_([a-z]+)-\d+\.wav")
        for name, audio in segments:
            cue = cue_pattern.fullmatch(name)
            if cue and cue[1] in tracks:
                tracks[cue[1]].append((name, audio))
    else:
        if len(segments) == 1:
            segments = [(f"{stem}.wav", segments[0][1])]
        tracks = dict.fromkeys(characters, segments)

    captions = {}
    if adventure and any(tracks.values()):
        script_name = f"{stem.removeprefix('sud_vo_')}.txt"
        try:
            script = resources[script_name]
        except KeyError:
            pass
        else:
            media = script.media
            media.reporter.register()
            captions = media.caption_map
    return tracks, captions


def write_archive(stem, segments, captions, output: Path) -> int:
    adventure = stem.startswith(ADVENTURE_PREFIX)
    folder = output / stem
    if not segments:
        if folder.exists():
            raise FileExistsError(f"Existing output differs: {folder}. Use a new output folder.")
        return 0

    with TemporaryDirectory(dir=output) as temporary:
        pending = Path(temporary) / stem
        pending.mkdir()
        rows = []
        for name, audio in sorted(segments, key=lambda segment: segment[0]):
            if Path(name).name != name or Path(name).suffix != ".wav":
                raise ValueError(f"Invalid WAV filename: {name!r}")
            with (pending / name).open("xb") as file:
                audio.export(file, format="wav")
            text = captions.get(Path(name).stem, "")
            status = "not_applicable"
            if adventure:
                status = "matched" if text else "not_found"
            rows.append((name, text, status))

        with (pending / "captions.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.writer(file)
            writer.writerow(CAPTION_FIELDS)
            writer.writerows(rows)

        if folder.exists():
            # Allow recovery when the prior run published the folder before saving its checkpoint.
            if not output_matches(folder, len(rows)) or any(
                file.read_bytes() != (folder / file.name).read_bytes()
                for file in pending.iterdir()
            ):
                raise FileExistsError(
                    f"Existing output differs: {folder}. Use a new output folder."
                )
        else:
            pending.rename(folder)
    return len(rows)


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("characters", nargs="+", choices=sorted(CHARACTER_ABBREVS))
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output folder for one character, or parent folder for multiple characters",
    )
    parser.add_argument(
        "--manifest", type=Path, help="Load a saved manifest instead of fetching the latest"
    )
    parser.add_argument("--archive", default="*", help="Glob matching ACB filenames")
    args = parser.parse_args()

    characters = list(dict.fromkeys(args.characters))
    parent = args.output if len(characters) > 1 and args.output else Path(".")
    outputs = {character: parent / f"{character}_voices" for character in characters}
    if len(characters) == 1 and args.output:
        outputs[characters[0]] = args.output
    checkpoints = {
        character: folder / ".completed.json" for character, folder in outputs.items()
    }
    try:
        completed = {}
        for character, checkpoint in checkpoints.items():
            records = {}
            if checkpoint.exists():
                records = json.loads(checkpoint.read_text(encoding="utf-8-sig"))
            if not isinstance(records, dict):
                raise ValueError(f"Invalid checkpoint: {checkpoint}")
            completed[character] = records
        manifest = gom.load(args.manifest) if args.manifest else gom.fetch()
    except Exception as error:
        parser.exit(1, f"{error}\n")

    resources = manifest.resources
    archives = sorted(
        (
            resource
            for resource in resources
            if resource.name.startswith("sud_vo_")
            and resource.name.endswith(".acb")
            and fnmatchcase(resource.name, args.archive)
        ),
        key=lambda resource: resource.name,
    )
    failures = skipped = exported = tracks = 0
    for resource in archives:
        stem = Path(resource.name).stem
        tokens = set(re.split(r"[_-]", stem))
        key = f"captions-v1:{resource.name}:{resource.md5}"
        pending = []
        for character, output in outputs.items():
            if not stem.startswith(ADVENTURE_PREFIX) and character not in tokens:
                continue
            count = completed[character].get(key)
            if type(count) is int and output_matches(output / stem, count):
                skipped += 1
            else:
                pending.append(character)
        if not pending:
            continue
        try:
            segments, captions = read_archive(resource, resources, pending)
        except Exception as error:
            print(f"{resource.name}: {error}", file=sys.stderr)
            failures += len(pending)
            continue
        for character in pending:
            output = outputs[character]
            try:
                output.mkdir(parents=True, exist_ok=True)
                count = write_archive(stem, segments[character], captions, output)
                completed[character][key] = count
                save_checkpoint(checkpoints[character], completed[character])
            except Exception as error:
                print(f"{resource.name} ({character}): {error}", file=sys.stderr)
                failures += 1
                continue
            exported += 1
            tracks += count

    if not (exported or skipped or failures):
        parser.exit(1, "No matching voice archives.\n")
    print(
        f"Processed {exported} archive/character pair(s), wrote {tracks} track(s), "
        f"skipped {skipped}, failed {failures}."
    )
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
