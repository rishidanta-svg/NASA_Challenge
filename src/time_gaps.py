"""Keep each lineage's exact observation times and signed satellite-minus-LiDAR gaps."""
import json
from pathlib import Path
import pandas as pd
from metadata import read_nisar_metadata
ROOT=Path(__file__).resolve().parents[1]


def main():
    lidar=pd.read_csv(ROOT/'data/processed/lidar_scan_meta.csv').set_index('date_key')
    gaps=[]
    def append(lineage,sensor,epoch,identity,satellite,reference):
        gaps.append(dict(lineage=lineage,sensor=sensor,analysis_epoch=epoch,acquisition_id=identity,
            satellite_utc=satellite,lidar_utc=reference,
            satellite_minus_lidar_hours=(pd.to_datetime(satellite,utc=True)-pd.to_datetime(reference,utc=True)).total_seconds()/3600))
    for stem,key,time in [('s1','item_id','acquisition_utc'),('s2','item_id','acquisition_utc'),('nisar','granule','begin_utc')]:
        path=ROOT/f'data/processed/{stem}_meta.csv'
        if not path.is_file():continue
        frame=read_nisar_metadata(path) if stem=='nisar' else pd.read_csv(path)
        for row in frame.to_dict('records'):
            append('main validation',stem,row['date_key'],row[key],row[time],lidar.loc[row['date_key'],'scan_utc'])
    source=json.loads((ROOT/'data/processed/verified/comparison/manifest.json').read_text())['source']
    for epoch,row in source['nisar'].items():
        append('verified map bundle','nisar',epoch,row['granule'],row['acquisition_start_utc'],source['lidar'][epoch]['timestamp_utc'])
    pd.DataFrame(gaps).to_csv(ROOT/'outputs/acquisition_time_gaps.csv',index=False)
    print(f'Wrote {len(gaps)} acquisition pair records; separate lineages retained')


if __name__=='__main__':main()
