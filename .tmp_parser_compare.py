import json
import sys
from pathlib import Path
from collections import Counter

if len(sys.argv) != 4:
    print('usage: python .tmp_parser_compare.py <repo_root> <corpus_dir> <out_json>')
    sys.exit(2)

repo_root = Path(sys.argv[1]).resolve()
corpus_dir = Path(sys.argv[2]).resolve()
out_json = Path(sys.argv[3]).resolve()

sys.path.insert(0, str(repo_root / 'src'))

from core.config import load_config  # type: ignore
from parsers.registry import REGISTRY  # type: ignore

cfg = load_config(str(repo_root), 'default_config.yaml')
allowed = set(getattr(cfg.indexing, 'supported_extensions', []) or [])

rows = []
counts = Counter()
for p in sorted([x for x in corpus_dir.rglob('*') if x.is_file()]):
    ext = p.suffix.lower()
    status = 'UNKNOWN'
    chars = 0
    parser = None
    reason = None
    if ext not in allowed:
        status = 'FILTERED_ALLOWLIST'
    else:
        info = REGISTRY.get(ext)
        if info is None:
            status = 'NO_REGISTERED_PARSER'
        else:
            parser_obj = info.parser_cls()
            parser = info.name
            try:
                if hasattr(parser_obj, 'parse_with_details'):
                    text, details = parser_obj.parse_with_details(str(p))
                else:
                    text = parser_obj.parse(str(p))
                    details = {}
                text = text or ''
                chars = len(text.strip())
                reason = details.get('reason') if isinstance(details, dict) else None
                status = 'TEXT_OK' if chars > 0 else 'EMPTY_TEXT'
            except Exception as e:
                status = 'PARSER_EXCEPTION'
                reason = f'{type(e).__name__}: {e}'
    counts[status] += 1
    rows.append({
        'file': str(p),
        'name': p.name,
        'ext': ext,
        'status': status,
        'chars': chars,
        'parser': parser,
        'reason': reason,
    })

payload = {
    'repo_root': str(repo_root),
    'corpus_dir': str(corpus_dir),
    'totals': dict(counts),
    'rows': rows,
}
out_json.parent.mkdir(parents=True, exist_ok=True)
out_json.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps(payload['totals'], indent=2))
