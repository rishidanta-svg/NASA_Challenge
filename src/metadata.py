"""Validate the two team NISAR metadata formats at their ingestion boundary."""
import re
import pandas as pd


def read_nisar_metadata(path):
    frame = pd.read_csv(path)
    # Preserve original identifiers; canonical granule is a name or CMR concept ID.
    for canonical, aliases in {'granule': ['granule_ur', 'concept_id'], 'begin_utc': ['acquisition_utc']}.items():
        if canonical not in frame:
            source = next((a for a in aliases if a in frame), None)
            if source:
                frame[canonical] = frame[source]
    required = ['date_key', 'granule', 'begin_utc', 'pixel_m_x', 'pixel_m_y']
    missing = sorted(set(required) - set(frame))
    if missing:
        raise ValueError(f'{path}: missing NISAR metadata columns: {missing}')
    if frame.empty or frame[required].isna().any().any():
        raise ValueError(f'{path}: NISAR metadata contains empty required values')
    if frame.date_key.duplicated().any():
        raise ValueError(f'{path}: duplicate analysis epoch; monthly scoring cannot collapse multiple acquisitions')
    for row in frame.itertuples():
        stamp = pd.Timestamp(row.begin_utc)
        if stamp.tzinfo is None:
            raise ValueError(f'{path}: acquisition time must have an explicit UTC offset')
        if not re.fullmatch(r'\d{4}-\d{2}', row.date_key):
            raise ValueError(f'{path}: invalid analysis epoch {row.date_key}')
        embedded = re.search(r'(\d{8}T\d{6})', row.granule)
        if embedded and pd.Timestamp(embedded[1], tz='UTC') != stamp:
            raise ValueError(f'{path}: granule timestamp disagrees with begin_utc')
        if not all(pd.notna(v) and float(v) > 0 and float(v) < float('inf') for v in (row.pixel_m_x, row.pixel_m_y)):
            raise ValueError(f'{path}: pixel spacing must be finite and positive')
    return frame
