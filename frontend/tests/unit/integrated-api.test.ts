import {describe,it,expect,beforeAll} from 'vitest';
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
import {CoastalEvidenceSchema,NisarEvidenceSchema,AnalysisSchema,TransectDetailSchema,LayerListSchema,AcquisitionListSchema} from '../../src/api/schemas';

describe.skipIf(!process.env.POLTERGEIST_PYTHON)('live backend/frontend contracts',()=>{
  let payload:Record<string,unknown>;
  beforeAll(()=>{
    const script=`import json\nfrom backend.app import create_app\nfrom fastapi.testclient import TestClient\nc=TestClient(create_app())\npaths={'coastal':'/api/coastal/observations','nisar':'/api/coastal/nisar','analysis':'/api/analysis/FRF-950','transect':'/api/transects/FRF-950','layers':'/api/layers','acquisitions':'/api/acquisitions'}\nprint(json.dumps({k:c.get(p).json() for k,p in paths.items()}))`;
    payload=JSON.parse(execFileSync(process.env.POLTERGEIST_PYTHON!,['-c',script],{cwd:resolve(process.cwd(),'..'),encoding:'utf8',maxBuffer:4_000_000}));
  },30000);
  it('accepts current optical/terrain evidence and preserves the matched tide comparison',()=>{const c=CoastalEvidenceSchema.parse(payload.coastal);expect(c.validation.targets.fixed_mhw_contour?.raw_vs_tide.rmse_reduction_percent?.tide).toBeCloseTo(49.7245,3);});
  it('accepts NISAR experiment and preserves withholding',()=>{
    const n=NisarEvidenceSchema.parse(payload.nisar);
    expect(n.terrain_ablation.terrain_model_deployment?.status).toBe('withheld');
    expect(n.shoreline.epochs.june?.comparability?.status).toBe('failed');
    expect(n.terrain_ablation.metrics?.B?.n).toBe(168);
  });
  it('accepts measured transects and acquisition-tagged analysis',()=>{
    expect(TransectDetailSchema.safeParse(payload.transect).success).toBe(true);
    expect(AnalysisSchema.safeParse(payload.analysis).success).toBe(true);
  });
  it('accepts the complete layer/acquisition catalog',()=>{
    const layers=LayerListSchema.parse(payload.layers);expect(layers.some(l=>l.slot==='nisar-hh-land-water-candidate')).toBe(true);
    expect(AcquisitionListSchema.parse(payload.acquisitions)).toHaveLength(28);
  });
});
