import {describe,expect,it} from 'vitest';
import {CoastalEvidenceSchema,TransectDetailSchema} from '../../src/api/schemas';
import {profileCsv,studyBrief} from '../../src/lib/exports';

const evidence=CoastalEvidenceSchema.parse({processing_version:'verified-1',status:'conditional',reasons:[],terrain:{status:'supported',reasons:[],mean_m:-.3144888,native_paired_cells:17466,datum:'NAVD88',acquisitions:[{epoch:'June',acquired_at:'2026-06-19T00:31:04Z',source_id:'<script>alert(1)</script>'}]},radar_disagreement:{status:'conditional',reasons:[]},validation:{scope:'Local October check',targets:{fixed_mhw_contour:{raw_vs_tide:{status:'conditional',n:36,methods:{raw:{n:36,rmse_m:7.41573,mae_m:7.1,bias_m:-7.1},tide:{n:36,rmse_m:3.72829,mae_m:3.3,bias_m:-3.1}},rmse_reduction_percent:{tide:49.7245}},raw_vs_tide_vs_setup:{status:'withheld',n:0},by_date:{}}}}});

describe('scientific exports',()=>{
  it('reports measured values, target scope, withheld models and escaped provenance',()=>{
    const html=studyBrief(evidence,null,'2026-11-15T00:00:00Z');
    expect(html).toContain('-0.31 m');expect(html).toContain('17,466');
    expect(html).toContain('7.42 m');expect(html).toContain('3.73 m');
    expect(html).toContain('horizontal position error');expect(html).toContain('not a general accuracy claim');
    expect(html).toContain('not available in this export');
    expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<script>alert');
  });
  it('retains validated improvement metadata rather than silently discarding it',()=>{
    expect(evidence.validation.targets.fixed_mhw_contour?.raw_vs_tide.rmse_reduction_percent?.tide).toBeCloseTo(49.7245);
  });
  it('preserves missing profile returns and exports measured changes with explicit coordinates',()=>{
    const t=TransectDetailSchema.parse({type:'Feature',geometry:{type:'LineString',coordinates:[[-75.75,36.18],[-75.751,36.18]]},properties:{id:'FRF-950',label:'Section 3',frf_y_m:950,x_origin_frf_m:50,x_reference:'Distance from line start'},profiles:[{epoch_label:'June',acquired_at:'2026-06-19T00:31:04Z',source:'LiDAR',vertical_datum:'NAVD88',units:'m',points:[{x_m:0,z_m:3},{x_m:1,z_m:2}]},{epoch_label:'October',acquired_at:'2026-10-16T23:33:04Z',source:'LiDAR',vertical_datum:'NAVD88',units:'m',points:[{x_m:1,z_m:1.5},{x_m:2,z_m:1}]}],boundaries:[],measured_change:{status:'supported',reasons:[],change_profile:[{x_m:1,dz_m:-.5}]}});
    const csv=profileCsv(t).split('\r\n');
    expect(csv).toHaveLength(4);
    expect(csv[1]).toContain('"0","50","3","",""');
    expect(csv[2]).toContain('"1","51","2","1.5","-0.5"');
    expect(csv[3]).toContain('"2","52","","1",""');
    expect(csv[0]).toContain('vertical_datum');
  });
});
