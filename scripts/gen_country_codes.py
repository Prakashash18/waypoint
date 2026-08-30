import pycountry
rows = []
for c in pycountry.countries:
    a3 = getattr(c, 'alpha_3', None); a2 = getattr(c, 'alpha_2', None)
    if a3 and a2:
        rows.append((a3, a2, c.name))
rows.sort()
out = ['"""ICAO/ISO 3166-1 alpha-3 → alpha-2, for reading a passport\'s MRZ.',
       '',
       'A passport encodes country as three letters; Atlas wants two. Generated',
       'from pycountry (ISO 3166-1) rather than written from memory, because a',
       'wrong country on a ticket is the kind of confident error this app exists',
       'to avoid. Codes absent here resolve to None, and the traveller is asked.',
       '',
       'Regenerate with: pip install pycountry && python scripts/gen_country_codes.py',
       '"""',
       '',
       'ALPHA3_TO_ALPHA2 = {']
for a3, a2, name in rows:
    out.append(f"    '{a3}': '{a2}',  # {name}")
out += ['}', '',
        '# The MRZ also carries a few codes that are not countries.',
        'NON_COUNTRY = {',
        "    'UNO': 'United Nations organization official',",
        "    'UNA': 'United Nations specialised agency official',",
        "    'XOM': 'Sovereign Military Order of Malta',",
        "    'XCC': 'Caribbean Community',",
        "    'XXA': 'Stateless person',",
        "    'XXB': 'Refugee (1951 Convention)',",
        "    'XXC': 'Refugee (other)',",
        "    'XXX': 'Unspecified nationality',",
        '}',
        '',
        '',
        'def alpha2(code):',
        '    """Two-letter code for an MRZ country, or None when it is not one."""',
        '    if not code:',
        '        return None',
        "    return ALPHA3_TO_ALPHA2.get(code.strip().upper())",
        '']
open('src/tools/country_codes.py','w').write('\n'.join(out))
print('countries mapped:', len(rows))
