/**
 * Runtime-validated data contract between the POLTERGEIST frontend and the
 * FastAPI backend. Human-readable version: docs/frontend-api-contract.md.
 *
 * Conventions
 *  - GeoJSON coordinates: EPSG:4326 lon/lat (RFC 7946).
 *  - Raster tiles: EPSG:3857 XYZ templates ({z}/{x}/{y}).
 *  - Timestamps: ISO-8601 with explicit offset, UTC preferred ("...Z").
 *  - Units are declared on every quantitative field; distances/elevations in metres.
 */
import { z } from 'zod';

const isoDateTime = z.string().datetime({ offset: true });
const lngLat = z.tuple([z.number().gte(-180).lte(180), z.number().gte(-90).lte(90)]);
const bbox = z.tuple([z.number(), z.number(), z.number(), z.number()]);

/** Returned with HTTP 200 when an endpoint exists but its product is not produced yet. */
export const UnavailableSchema = z.object({
  status: z.literal('unavailable'),
  reason: z.string(),
  expected: z.string().optional(),
});
export type Unavailable = z.infer<typeof UnavailableSchema>;

/** RFC 7807 problem details (errors). */
export const ProblemSchema = z.object({
  type: z.string().optional(),
  title: z.string(),
  status: z.number().int(),
  detail: z.string().optional(),
});

export const ProvenanceSchema = z.object({
  source: z.string(),
  product_id: z.string().nullish(),
  processing: z.string().nullish(),
  url: z.string().url().nullish(),
});

// ---------- /api/study-area ----------
export const StudyAreaSchema = z.object({
  type: z.literal('Feature'),
  geometry: z.object({
    type: z.literal('Polygon'),
    coordinates: z.array(z.array(lngLat).min(4)).min(1),
  }),
  properties: z.object({
    name: z.string(),
    analysis_crs: z.string().regex(/^EPSG:\d+$/),
    frf_y_range_m: z.tuple([z.number(), z.number()]),
    transect_ids: z.array(z.string()).optional(),
  }),
});
export type StudyArea = z.infer<typeof StudyAreaSchema>;

// ---------- /api/acquisitions ----------
export const SensorSchema = z.enum(['NISAR', 'SENTINEL-1', 'SENTINEL-2', 'LIDAR', 'MODEL', 'OTHER']);
export type Sensor = z.infer<typeof SensorSchema>;

export const AcquisitionSchema = z.object({
  id: z.string(),
  sensor: SensorSchema,
  product: z.string(),
  acquired_at: isoDateTime,
  acquired_end: isoDateTime.nullish(),
  polarizations: z.array(z.string()).nullish(),
  orbit_direction: z.enum(['ascending', 'descending']).nullish(),
  cloud_cover_pct: z.number().min(0).max(100).nullish(),
  qa: z.record(z.unknown()).nullish(),
  source_url: z.string().url().nullish(),
});
export type Acquisition = z.infer<typeof AcquisitionSchema>;
export const AcquisitionListSchema = z.array(AcquisitionSchema);

// ---------- /api/layers ----------
export const LayerGroupSchema = z.enum(['measured', 'sensor', 'model', 'reference']);
export type LayerGroup = z.infer<typeof LayerGroupSchema>;

export const LayerKindSchema = z.enum(['raster_xyz', 'image', 'geojson', 'raster_dem']);

export const ColormapSchema = z.object({
  type: z.enum(['sequential', 'diverging', 'categorical']),
  min: z.number(),
  max: z.number(),
  /** [value, css colour] pairs, ascending by value. */
  stops: z.array(z.tuple([z.number(), z.string()])).min(2),
  nodata_color: z.string().nullish(),
});
export type Colormap = z.infer<typeof ColormapSchema>;

export const LayerDescriptorSchema = z
  .object({
    id: z.string(),
    /** Frontend overlay slot this layer fills (see src/config/slots.ts). */
    slot: z.string(),
    title: z.string(),
    group: LayerGroupSchema,
    sensor: SensorSchema,
    kind: LayerKindSchema,
    /** raster_xyz / raster_dem tile templates. */
    tiles: z.array(z.string()).nullish(),
    tile_size: z.number().int().nullish(),
    /** raster_dem only. */
    encoding: z.enum(['terrarium', 'mapbox']).nullish(),
    /** image (PNG/JPEG) URL or geojson URL. */
    url: z.string().nullish(),
    /** image only: TL, TR, BR, BL corners. */
    coordinates: z.tuple([lngLat, lngLat, lngLat, lngLat]).nullish(),
    bounds: bbox.nullish(),
    minzoom: z.number().nullish(),
    maxzoom: z.number().nullish(),
    units: z.string().nullable(),
    quantity: z.string().nullish(),
    colormap: ColormapSchema.nullish(),
    /** Single acquisition time; null for multi-epoch products (e.g. differences). */
    acquired_at: isoDateTime.nullish(),
    epoch_label: z.string(),
    /** Date used to match this layer to the timeline; null = time-independent. */
    reference_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullish(),
    native_crs: z.string(),
    native_resolution_m: z.number().positive().nullish(),
    vertical_datum: z.string().nullish(),
    /** true for model-inferred (not directly measured) quantities. */
    inferred: z.boolean(),
    status: z.enum(['available', 'unavailable']),
    reason: z.string().nullish(),
    qa: z.record(z.unknown()).nullish(),
    provenance: ProvenanceSchema,
  })
  .superRefine((l, ctx) => {
    if (l.status !== 'available') return;
    if ((l.kind === 'raster_xyz' || l.kind === 'raster_dem') && !l.tiles?.length)
      ctx.addIssue({ code: 'custom', message: `${l.id}: ${l.kind} requires tiles[]` });
    if (l.kind === 'image' && (!l.url || !l.coordinates))
      ctx.addIssue({ code: 'custom', message: `${l.id}: image requires url and coordinates` });
    if (l.kind === 'geojson' && !l.url)
      ctx.addIssue({ code: 'custom', message: `${l.id}: geojson requires url` });
    if (l.kind === 'raster_dem' && !l.encoding)
      ctx.addIssue({ code: 'custom', message: `${l.id}: raster_dem requires encoding` });
    if (l.group === 'model' && !l.inferred)
      ctx.addIssue({ code: 'custom', message: `${l.id}: model layers must set inferred=true` });
    if (l.group === 'measured' && l.inferred)
      ctx.addIssue({ code: 'custom', message: `${l.id}: measured layers cannot be inferred` });
  });
export type LayerDescriptor = z.infer<typeof LayerDescriptorSchema>;
export const LayerListSchema = z.array(LayerDescriptorSchema);

// ---------- /api/terrain/change ----------
export const TerrainEpochSchema = z.object({
  label: z.string(),
  survey_start: isoDateTime,
  survey_end: isoDateTime.nullish(),
  product_id: z.string().nullish(),
});

export const TerrainChangeSchema = z.object({
  layer: LayerDescriptorSchema,
  epochs: z.tuple([TerrainEpochSchema, TerrainEpochSchema]),
  /** Optional per-epoch DEM tiles for 3D (raster_dem descriptors). */
  dems: z.array(LayerDescriptorSchema).optional(),
  vertical_datum: z.string(),
  units: z.literal('m'),
  uncertainty_m: z.number().nonnegative().nullish(),
  stats: z
    .object({
      mean_m: z.number(),
      min_m: z.number(),
      max_m: z.number(),
      net_volume_m3: z.number().nullish(),
      valid_area_m2: z.number().nullish(),
    })
    .nullish(),
});
export type TerrainChange = z.infer<typeof TerrainChangeSchema>;

// ---------- /api/transects and /api/transects/{id} ----------
const profilePoint = z.object({ x_m: z.number().finite(), z_m: z.number().finite() });

export const ProfileSchema = z
  .object({
    epoch_label: z.string(),
    acquired_at: isoDateTime.nullable(),
    source: z.string(),
    vertical_datum: z.string(),
    units: z.literal('m'),
    points: z.array(profilePoint).min(2),
  })
  .refine((p) => p.points.every((v, i) => i === 0 || v.x_m > p.points[i - 1]!.x_m), {
    message: 'profile x_m must be strictly increasing',
  });
export type Profile = z.infer<typeof ProfileSchema>;

export const BoundaryTypeSchema = z.enum(['radar', 'optical', 'terrain']);
export const BoundaryPickSchema = z.object({
  type: BoundaryTypeSchema,
  sensor: SensorSchema,
  /** e.g. "HH/HV GCOV transition", "NDWI waterline", "z = 1.0 m NAVD88 contour". */
  definition: z.string(),
  epoch_label: z.string(),
  acquired_at: isoDateTime.nullable(),
  x_m: z.number().finite(),
  uncertainty_m: z.number().nonnegative().nullish(),
});
export type BoundaryPick = z.infer<typeof BoundaryPickSchema>;

export const TransectSummarySchema = z.object({
  type: z.literal('Feature'),
  geometry: z.object({ type: z.literal('LineString'), coordinates: z.array(lngLat).min(2) }),
  properties: z.object({
    id: z.string(),
    label: z.string(),
    frf_y_m: z.number().nullish(),
    /** Cross-shore reference: x_m measured along the line from its first coordinate. */
    x_reference: z.string(),
  }),
});
export type TransectSummary = z.infer<typeof TransectSummarySchema>;
export const TransectCollectionSchema = z.object({
  type: z.literal('FeatureCollection'),
  features: z.array(TransectSummarySchema),
});

export const TransectDetailSchema = TransectSummarySchema.extend({
  profiles: z.array(ProfileSchema),
  boundaries: z.array(BoundaryPickSchema),
});
export type TransectDetail = z.infer<typeof TransectDetailSchema>;

// ---------- /api/analysis/{id} ----------
export const AnalysisSchema = z.object({
  transect_id: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  generated_at: isoDateTime,
  inferred: z.literal(true),
  target_epoch_label: z.string(),
  vertical_datum: z.string(),
  units: z.literal('m'),
  /** z_m predicted, sigma_m one-standard-deviation uncertainty. */
  points: z
    .array(z.object({ x_m: z.number().finite(), z_m: z.number().finite(), sigma_m: z.number().nonnegative() }))
    .min(2),
  uncertainty_method: z.string(),
  inputs: z.array(z.string()),
  skill: z.record(z.number()).nullish(),
});
export type Analysis = z.infer<typeof AnalysisSchema>;

// ---------- /api/environment/latest ----------
export const EnvironmentObservationSchema = z.object({
  variable: z.string(),
  label: z.string(),
  /** null when the station reports no current value. Never synthesised. */
  value: z.number().nullable(),
  units: z.string(),
  observed_at: isoDateTime.nullable(),
  kind: z.enum(['observation', 'prediction']),
  station_id: z.string(),
  station_name: z.string(),
  provider: z.string(),
  datum: z.string().nullish(),
  qc_flag: z.string().nullish(),
  quality: z.enum(['preliminary', 'verified', 'unknown']).nullish(),
  extra: z.record(z.union([z.string(), z.number(), z.null()])).nullish(),
  source_url: z.string().url().nullish(),
  error: z.string().nullish(),
});
export type EnvironmentObservation = z.infer<typeof EnvironmentObservationSchema>;

export const EnvironmentLatestSchema = z.object({
  retrieved_at: isoDateTime,
  observations: z.array(EnvironmentObservationSchema),
});
export type EnvironmentLatest = z.infer<typeof EnvironmentLatestSchema>;

// Horizontal boundary analysis is a separate product from elevation reconstruction.
export const BoundaryAnalysisSchema = z.object({
  transect_id: z.string(), quantity: z.literal('cross-shore boundary position'),
  coordinate_reference: z.string(), inferred: z.literal(true),
  quality_checks: z.array(z.object({check:z.string(), status:z.enum(['PASS','FAIL','NOT RUN']), detail:z.string()})),
  records: z.array(z.object({
    epoch: z.string(), feature: z.enum(['waterline', 'dunetoe']),
    x_frf_m: z.number().finite().nullable(), status: z.string(), source: z.string(),
    cv_rmse_m: z.number().nonnegative().nullable(),
    interval90_frf_m: z.tuple([z.number().finite(), z.number().finite()]).nullable(),
    observations: z.array(z.object({
      sensor: z.string(), product: z.string(), acquisition_id: z.string(),
      acquired_at: isoDateTime.nullable(), x_frf_m: z.number().finite().nullable(),
      lidar_offset_hours: z.number().finite().nullable(),
    })).optional(),
  })),
  validation: z.array(z.object({method: z.string(), N: z.number().int(), RMSE_m: z.number().nonnegative().nullable()})),
  limitations: z.array(z.string()),
});
export type BoundaryAnalysis = z.infer<typeof BoundaryAnalysisSchema>;
