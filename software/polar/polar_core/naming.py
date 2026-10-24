"""User-configurable filename fields; no user-supplied regular expressions."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
import re

from .batch_contact_angle import image_metadata, choose_images, well_key
from .science import finite

NUMBER = r'(?<![0-9.pP+-])-?\d+(?:[.p-]\d+)?'
FIELDS = {'well': r'[A-Za-z]+\d+', 'z': NUMBER, 'time': r'\d+(?:[.-]\d+)?',
          'position': r'[A-Za-z][A-Za-z0-9_.-]*?'}
DEFAULT_PATTERN = '*plate.{well}_t={time}s_z={z}mm*'


@lru_cache(maxsize=128)
def compile_pattern(pattern):
    if not isinstance(pattern,str) or not 1<=len(pattern)<=300:
        raise ValueError('Enter a filename pattern of 1–300 characters.')
    if pattern.count('*')>4:
        raise ValueError('Use at most four * wildcards in a filename pattern.')
    parts=re.split(r'(\{[^{}]*\}|\*)',pattern)
    fields=[];regex=[]
    for part in parts:
        if not part:continue
        if part=='*':regex.append('.*?')
        elif part.startswith('{'):
            name=part[1:-1]
            if name not in FIELDS:raise ValueError('Available fields are {well}, {z}, {time} and {position}. Use * for other text.')
            if name in fields:raise ValueError(f'Use {{{name}}} only once.')
            fields.append(name);regex.append(f'(?P<{name}>{FIELDS[name]})')
        else:
            if '{' in part or '}' in part:raise ValueError('Check the braces around each field.')
            regex.append(re.escape(part))
    if 'well' not in fields:raise ValueError('The pattern needs {well}, for example plate.{well}.')
    # Prevent a wildcard or adjacent numeric field from silently truncating a field.
    for i,part in enumerate(parts):
        if part.startswith('{') and i+1<len(parts):
            following=next((x for x in parts[i+1:] if x),'')
            if following=='*' or following.startswith('{'):
                raise ValueError('Put fixed text after each field, such as _ after {well}, mm after {z}, or s after {time}.')
    return re.compile('^'+''.join(regex)+'$',re.IGNORECASE),frozenset(fields)


def naming_settings(raw):
    source=raw.get('filename_format','cubos')
    unit=raw.get('time_unit','s');kind=raw.get('time_kind','elapsed')
    if source not in ('cubos','custom'):raise ValueError('Choose CubOS names or a custom filename pattern.')
    if unit not in ('s','min','h') or kind not in ('elapsed','index'):raise ValueError('Choose valid time-label units and interpretation.')
    out=dict(filename_format=source,filename_pattern=str(raw.get('filename_pattern',DEFAULT_PATTERN)),time_unit=unit,time_kind=kind,
             time_interval=finite(raw.get('time_interval',60),'Scan interval',.000001,1e9),
             first_scan=int(finite(raw.get('first_scan',0),'First scan number',0,1)))
    if float(raw.get('first_scan',0)) not in (0,1):raise ValueError('First scan number must be 0 or 1.')
    if source=='custom':
        _,fields=compile_pattern(out['filename_pattern'])
        suffix=re.search(r'\{time\}(seconds?|secs?|s|minutes?|mins?|min|hours?|hrs?|h)(?=[^A-Za-z]|$)',out['filename_pattern'],re.IGNORECASE)
        if suffix and kind=='elapsed':
            stated=suffix[1].lower()
            stated_unit='s' if stated.startswith('s') else 'min' if stated.startswith('m') else 'h'
            if unit!=stated_unit:raise ValueError('The time-unit suffix in your pattern differs from the selected Time unit. Make them agree.')
        if 'z' not in fields and raw.get('zg_fallback') in (None,''):
            raise ValueError('Include {z} in the pattern, or supply a fallback gantry Z under Calibration.')
    else:fields=frozenset()
    if raw.get('grouping')=='timepoints' and 'time' not in fields:
        raise ValueError('For time-series focus stacks, choose a custom pattern containing {time}.')
    if raw.get('grouping')=='positions' and 'position' not in fields:
        raise ValueError('For position scans, choose a custom pattern containing {position}.')
    if 'position' in fields and raw.get('grouping','wells') not in ('positions','frames'):
        raise ValueError('Choose Position scan or Individual frames to keep {position} labels separate.')
    if raw.get('grouping')=='positions' and 'time' in fields:
        raise ValueError('Position scans group one focus stack per well and position. Use separate runs for repeated times.')
    return out


def decimal_number(text):
    # Filename decimal markers: 122p8 -> 122.8; 59-300 -> 59.300.
    text=text.lower().replace('p','.')
    if text.startswith('-'):text='-'+text[1:].replace('-','.')
    else:text=text.replace('-','.')
    try:return Decimal(text)
    except InvalidOperation as error:raise ValueError('Invalid numeric filename field.') from error


def filename_metadata(filename,settings):
    name=Path(filename).name
    if len(name)>255:raise ValueError('Image filename is longer than 255 characters.')
    if settings.get('filename_format','cubos')=='cubos':
        try:return image_metadata(Path(name))
        except ValueError:
            fallback=settings.get('zg_fallback')
            if fallback is None:raise
            # Preserve the existing standalone-image fallback without inventing a well.
            well=re.search(r'(?:^|_)plate\.([A-Za-z]+\d+)(?=_)',name)
            return dict(well=well[1].upper() if well else Path(name).stem,zg_mm=fallback,brightness_group='unspecified')
    regex,_=compile_pattern(settings['filename_pattern'])
    match=regex.fullmatch(name)
    if not match:raise ValueError('Filename does not match the selected naming pattern.')
    fields=match.groupdict()
    zg=float(decimal_number(fields['z'])) if 'z' in fields else settings['zg_fallback']
    zg=finite(zg,'Filename gantry Z',-10000,10000)
    brightness=re.search(r'_b(\d+(?:[.-]\d+)?)(?=_|\.)',name)
    out=dict(well=fields['well'].upper(),zg_mm=zg,brightness_group='b'+brightness[1] if brightness else 'unspecified')
    if 'position' in fields:out['position']=fields['position'].lower()
    if 'time' in fields:
        value=decimal_number(fields['time'])
        if settings['time_kind']=='index':
            if value!=value.to_integral_value():raise ValueError('Scan numbers must be whole numbers.')
            value-=Decimal(settings['first_scan'])
            if value<0:raise ValueError('Scan number precedes the configured first scan.')
            value*=Decimal(str(settings['time_interval']))
        seconds=value*{'s':Decimal(1),'min':Decimal(60),'h':Decimal(3600)}[settings['time_unit']]
        out.update(elapsed_s=finite(float(seconds),'Elapsed time',0,1e12),time_label=fields['time'])
    return out


def preview_names(names,settings):
    if not isinstance(names,list) or not 1<=len(names)<=1000:raise ValueError('Preview 1–1,000 image filenames.')
    rows=[];groups=defaultdict(list)
    for name in names:
        if not isinstance(name,str):raise ValueError('Filenames must be text.')
        row={'filename':name}
        try:
            row.update(filename_metadata(name,settings));row['status']='matched'
            key=(row['well'],row.get('elapsed_s') if settings['grouping']=='timepoints'
                 else row.get('position') if settings['grouping']=='positions' else None)
            groups[key].append(row['zg_mm'])
        except ValueError as error:row.update(status='unmatched',reason=str(error))
        rows.append(row)
    warnings=[]
    if settings['grouping']=='wells' and any(r.get('elapsed_s') is not None for r in rows):
        warnings.append('Focus stack groups by well only. Choose Time series · focus stack per time point to retain different times.')
    return dict(rows=rows,matched=sum(r['status']=='matched' for r in rows),total=len(rows),
                group_count=len(rows) if settings['grouping']=='frames' else len(groups),warnings=warnings)


def select_timepoints(candidates,step):
    groups=defaultdict(list)
    for row in candidates:
        if not row.get('well') or 'elapsed_s' not in row:raise ValueError('Every time-series image needs a well and an elapsed time.')
        groups[(row['well'],row['elapsed_s'])].append(row)
    selected=[]
    for (well,seconds),rows in sorted(groups.items(),key=lambda item:(well_key(item[0][0]),item[0][1])):
        item=choose_images(rows,step)[0]
        item['elapsed_s']=seconds
        selected.append(item)
    return selected


def select_positions(candidates,step):
    """Keep wells and offset labels separate while selecting focus within each."""
    groups=defaultdict(list)
    for row in candidates:
        if not row.get('well') or not row.get('position'):
            raise ValueError('Every position-scan image needs a well and a position label.')
        groups[(row['well'],row['position'])].append(row)
    selected=[]
    for (well,position),rows in sorted(groups.items(),key=lambda item:(well_key(item[0][0]),item[0][1])):
        item=choose_images(rows,step)[0]
        item['position']=position
        selected.append(item)
    return selected
