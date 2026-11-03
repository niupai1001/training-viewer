"""Validate one Training Viewer Log Protocol v1.0 run directory.

Usage: python tools/validate_log.py examples/segformer_baseline
Requires: pip install jsonschema
"""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

BASE = Path(__file__).resolve().parents[1]

def read_json(path: Path):
    def reject_nonfinite(value):
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)

def check(path: Path, schema: dict, label: str) -> tuple[int, int]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    failed = total = 0
    if not path.exists():
        if label == "run":
            print(f"ERROR required file missing: {path}")
            return 1, 0
        print(f"NOTE optional file missing: {path}")
        return 0, 0
    if path.suffix == '.jsonl':
        # Never consume a partial append: files without a terminating newline
        # have their last line treated as in-flight.
        raw = path.read_bytes()
        lines = raw.split(b'\n')
        if lines and lines[-1]:
            print(f"NOTE trailing incomplete line deferred: {path}")
        valid_lines = lines[:-1]
        for lineno, line in enumerate(valid_lines, start=1):
            if not line.strip():
                continue
            total += 1
            try:
                obj = json.loads(line.decode('utf-8'), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
                issues = sorted(validator.iter_errors(obj), key=lambda x: list(map(str,x.path)))
                if issues:
                    raise ValueError('; '.join(x.message for x in issues))
                if label == 'metrics' and any(not math.isfinite(float(v)) for v in obj['metrics'].values()):
                    raise ValueError('non-finite metric')
                if label == 'events' and obj['type'] == 'artifact':
                    relative = Path(obj['path'])
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('artifact path outside run directory')
                    resolved = (path.parent/relative).resolve()
                    if not resolved.is_relative_to(path.parent.resolve()):
                        raise ValueError('artifact symlink outside run directory')
                    if not resolved.is_file():
                        print(f"WARN missing artifact at {path.name}:{lineno}: {relative}")
            except (UnicodeError, ValueError, json.JSONDecodeError) as e:
                print(f"ERROR {path.name}:{lineno}: {e}")
                failed += 1
    else:
        total += 1
        try:
            obj = read_json(path)
            issues = sorted(validator.iter_errors(obj), key=lambda x: list(map(str,x.path)))
            if issues:
                raise ValueError('; '.join(x.message for x in issues))
        except (ValueError, json.JSONDecodeError) as e:
            print(f"ERROR {path.name}: {e}")
            failed += 1
    return failed, total

def main() -> int:
    if len(sys.argv)!=2:
        print('Usage: python tools/validate_log.py PATH_TO_RUN_DIRECTORY')
        return 2
    folder=Path(sys.argv[1]).resolve()
    fails = total = 0
    run_schema='run.schema.json'
    try:
        version=read_json(folder/'run.json').get('schema_version')
        if version=='1.1':
            run_schema='run-1.1.schema.json'
    except (OSError, ValueError, AttributeError):
        pass
    for name,schema_name,label in [('run.json',run_schema,'run'),('metrics.jsonl','metrics.schema.json','metrics'),('events.jsonl','events.schema.json','events')]:
        schema=read_json(BASE/'schemas'/schema_name)
        f,n=check(folder/name,schema,label)
        fails+=f;total+=n
    print(f'Validation: checked {total} record(s), {fails} error(s)')
    return 1 if fails else 0

if __name__ == '__main__':
    raise SystemExit(main())
