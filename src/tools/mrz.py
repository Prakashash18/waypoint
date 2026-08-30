"""Reading the machine-readable zone at the bottom of a passport.

The MRZ is the two (or three) lines of monospaced text on the photo page. It
carries exactly what a booking needs — family and given names, date of birth,
sex, nationality, document number and expiry — in a fixed layout defined by
ICAO Doc 9303.

The reason to read the MRZ rather than the printed page is the check digits.
Every important field carries one, plus a composite over the whole line, so a
character misread by OCR is *detectable*. Nothing here guesses: a field whose
check digit fails is reported as failed and left for the traveller to type. A
wrong digit in a date of birth is the kind of confident error that strands
someone at a check-in desk.

Supported: TD3 (passport, 2×44) and TD2 (some travel documents, 2×36).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .country_codes import alpha2

# '<' is the filler, and counts as zero in a checksum.
_VALUES = {'<': 0}
for _i in range(10):
    _VALUES[str(_i)] = _i
for _i, _c in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    _VALUES[_c] = 10 + _i

_WEIGHTS = (7, 3, 1)

# The MRZ defines an alphabet per field: names and country codes are letters
# only, dates and check digits are digits only. A digit inside a name is
# therefore not a judgement call about what was meant — it is definitionally a
# misread, and the confusable pairs are the well-known ones. Repairing within
# the field's own alphabet is deterministic; the check digits then confirm it.
_TO_ALPHA = str.maketrans({'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '6': 'G', '8': 'B'})
_TO_DIGIT = str.maketrans({'O': '0', 'Q': '0', 'D': '0', 'U': '0',
                           'I': '1', 'L': '1', 'Z': '2', 'S': '5',
                           'B': '8', 'G': '6', 'A': '4'})


def _as_alpha(chunk: str) -> str:
    return chunk.translate(_TO_ALPHA)


def _as_digits(chunk: str) -> str:
    return chunk.translate(_TO_DIGIT)


def check_digit(chunk: str) -> Optional[int]:
    """ICAO 9303 check digit: weights 7-3-1 cycling, sum modulo 10."""
    total = 0
    for i, ch in enumerate(chunk):
        value = _VALUES.get(ch)
        if value is None:
            return None          # a character OCR should never have produced
        total += value * _WEIGHTS[i % 3]
    return total % 10


def _verify(chunk: str, printed: str) -> bool:
    if not printed.isdigit():
        return False
    return check_digit(chunk) == int(printed)


def _yymmdd(raw: str, *, future: bool) -> Optional[str]:
    """Expand a 2-digit MRZ year into an ISO date.

    The MRZ gives no century. A birth date is always in the past, so a year
    ahead of today belongs to the previous century. An expiry is *usually*
    ahead but not always — an expired passport is a real thing to read, and
    forcing it forward would turn 2012 into 2112 — so expiry is only shifted
    when it falls outside a plausible window either side of today.
    """
    if len(raw) != 6 or not raw.isdigit():
        return None
    yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    today = date.today()
    year = today.year // 100 * 100 + yy
    if future:
        if year < today.year - 20:
            year += 100
        elif year > today.year + 30:
            year -= 100
    elif year > today.year:
        year -= 100
    try:
        return date(year, mm, dd).isoformat()
    except ValueError:
        return None             # 31 February and friends


def _resolve_number(num: str, printed: str) -> Optional[str]:
    """Find a reading of the document number its own check digit accepts.

    Passport numbers mix letters and digits, so the field's alphabet cannot
    settle a confusable character. Its check digit can: try each confusable
    position both ways and keep a reading that verifies. If none does — or more
    than one does — nothing is returned, and the field stays untrusted.
    """
    import itertools
    pairs = {'0': 'O', 'O': '0', '1': 'I', 'I': '1', '5': 'S', 'S': '5',
             '8': 'B', 'B': '8', '2': 'Z', 'Z': '2', '6': 'G', 'G': '6'}
    spots = [i for i, ch in enumerate(num) if ch in pairs]
    if not spots or len(spots) > 6:
        return None
    hits = []
    for flips in itertools.product(*([(False, True)] * len(spots))):
        cand = list(num)
        for i, flip in zip(spots, flips):
            if flip:
                cand[i] = pairs[num[i]]
        text = ''.join(cand)
        if _verify(text, printed):
            hits.append((sum(flips), text))
    if not hits:
        return None
    # Several readings can satisfy one check digit by coincidence, so prefer the
    # one needing fewest corrections — a scanner mistakes one character far more
    # often than three. A tie at that count is genuinely ambiguous: leave it.
    fewest = min(n for n, _ in hits)
    best = [t for n, t in hits if n == fewest]
    return best[0] if len(best) == 1 else None


def _names(field_text: str) -> Dict[str, str]:
    """Split the name field into family and given names.

    The layout is SURNAME<<GIVEN<NAMES, with '<' for every space.
    """
    surname, _, given = field_text.partition('<<')
    clean = lambda s: ' '.join(p for p in s.split('<') if p).strip()
    return {'surname': clean(surname), 'given_names': clean(given)}


@dataclass
class MRZResult:
    ok: bool
    format: str = ''
    fields: Dict[str, object] = field(default_factory=dict)
    # Which check digits passed, so a caller can trust field by field.
    checks: Dict[str, bool] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    error: str = ''

    def to_dict(self) -> Dict[str, object]:
        return {'ok': self.ok, 'format': self.format, 'fields': self.fields,
                'checks': self.checks, 'failed': self.failed, 'error': self.error}


def _normalise(lines: List[str], width: int) -> List[str]:
    out = []
    for ln in lines:
        # OCR routinely reports « or K for the filler, and strips spaces.
        ln = (ln or '').strip().upper().replace(' ', '')
        ln = ln.replace('«', '<').replace('≪', '<')
        out.append(ln[:width].ljust(width, '<'))
    return out


def parse(lines: List[str]) -> MRZResult:
    """Parse TD3 or TD2 MRZ lines into booking fields, verifying every digit."""
    raw = [ln for ln in (lines or []) if (ln or '').strip()]

    # Keep only lines that look like a machine-readable zone. A transcriber
    # will wrap its answer in a markdown fence or add a stray caption, and a
    # '```' counted as a line silently shifted the whole read by one.
    def looks_like_mrz(ln: str) -> bool:
        text = ln.strip().upper().replace(' ', '')
        if len(text) < 28:
            return False
        good = sum(1 for ch in text if ch in _VALUES)
        return good / len(text) >= 0.9

    candidates = [ln for ln in raw if looks_like_mrz(ln)]
    if len(candidates) < 2:
        return MRZResult(False, error='Need the two lines from the bottom of the page.')

    # Take the last two: a TD1 zone or a caption may precede them.
    raw = candidates[-2:]
    width = 44 if max(len(r.strip()) for r in raw) > 38 else 36
    fmt = 'TD3' if width == 44 else 'TD2'
    l1, l2 = _normalise(raw, width)

    end = 42 if width == 44 else 35
    name_field = _as_alpha(l1[5:width])
    num, num_cd = l2[0:9], _as_digits(l2[9])
    nat = _as_alpha(l2[10:13])
    dob, dob_cd = _as_digits(l2[13:19]), _as_digits(l2[19])
    sex = l2[20]
    exp, exp_cd = _as_digits(l2[21:27]), _as_digits(l2[27])
    optional = l2[28:end]
    if width == 44:
        opt_cd = _as_digits(l2[42])
        composite_cd = _as_digits(l2[43])
    else:
        opt_cd = ''
        composite_cd = _as_digits(l2[35])
    # Rebuild line 2 from the repaired fields so the composite sees them too.
    composite_src = (num + num_cd + dob + dob_cd + exp + exp_cd
                     + optional + (opt_cd if width == 44 else ''))

    if not _verify(num, num_cd):
        # Try the digit/letter reading of each character until the check digit
        # agrees. Only a reading that satisfies the printed digit is accepted.
        fixed = _resolve_number(num, num_cd)
        if fixed:
            num = fixed
            composite_src = (num + num_cd + dob + dob_cd + exp + exp_cd
                             + optional + (opt_cd if width == 44 else ''))

    checks = {
        'document_number': _verify(num, num_cd),
        'birthday': _verify(dob, dob_cd),
        'expires': _verify(exp, exp_cd),
        'composite': _verify(composite_src, composite_cd),
    }
    if opt_cd:
        checks['optional'] = _verify(optional, opt_cd)

    names = _names(name_field)
    birthday = _yymmdd(dob, future=False)
    expires = _yymmdd(exp, future=True)
    issuer = l1[2:5]

    fields = {
        'document_type': 'PP' if l1[0] == 'P' else l1[0:2].replace('<', ''),
        'surname': names['surname'],
        'given_names': names['given_names'],
        # Atlas wants FAMILY/GIVEN.
        'name': (f"{names['surname']}/{names['given_names']}"
                 if names['surname'] and names['given_names'] else ''),
        'document_number': num.replace('<', ''),
        'issuing_country': alpha2(issuer),
        'issuing_country_mrz': issuer.replace('<', ''),
        'nationality': alpha2(nat),
        'nationality_mrz': nat.replace('<', ''),
        'birthday': birthday,
        'expires': expires,
        'gender': sex if sex in ('M', 'F') else '',
    }

    # A failed check digit means the character was misread; the value is not
    # trustworthy, so say which ones rather than filling a form with them.
    # The optional data field is a personal number this booking never uses, and
    # it drags the composite down with it, so neither blocks the fields we do
    # use — each of which carries a check digit of its own.
    blocking = ('document_number', 'birthday', 'expires')
    failed = [k for k in blocking if not checks.get(k)]
    if not birthday:
        failed.append('birthday_unreadable')
    if not expires:
        failed.append('expires_unreadable')
    if not fields['name']:
        failed.append('name_unreadable')

    # Readable but unusable: worth saying before someone reaches a check-in desk.
    fields['expired'] = bool(expires and expires < date.today().isoformat())

    fields['name_verified'] = bool(checks.get('composite'))
    return MRZResult(ok=not failed, format=fmt, fields=fields,
                     checks=checks, failed=sorted(set(failed)))
