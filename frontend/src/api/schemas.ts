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

export const AcquisitionEnvironmentSummarySchema = z.object({
  water_level_m_mllw: z.number().nullable().optional(),
  water_level_timestamp_utc: z.string().nullable().optional(),
  water_level_offset_s: z.number().nullable().optional(),
  tide_prediction_m_mllw: z.number().nullable().optional(),
  predicted_tide_stage: z.string().nullable().optional(),
  predicted_tide_slope_m_per_h: z.number().nullable().optional(),
  observed_minus_predicted_m: z.number().nullable().optional(),
  wave_hs_m_17m: z.number().nullable().optional(),
  wave_tp_s_17m: z.number().nullable().optional(),
  wave_dir_deg_17m: z.number().nullable().optional(),
  wave_17m_timestamp_utc: z.string().nullable().optional(),
  wave_17m_offset_s: z.number().nullable().optional(),
  wave_hs_m_26m: z.number().nullable().optional(),
  wave_tp_s_26m: z.number().nullable().optional(),
  wind_speed_ms: z.number().nullable().optional(),
  wind_dir_deg: z.number().nullable().optional(),
  rain_10min_mm: z.number().nullable().optional(),
  rain_24h_mm: z.number().nullable().optional(),
  rain_72h_mm: z.number().nullable().optional(),
  wave_hs_24h_max_m_17m: z.number().nullable().optional(),
  total_water_level_2pct_navd88_m: z.number().nullable().optional(),
  qualifying_station_matches: z.number().int().optional(),
});
export type AcquisitionEnvironmentSummary = z.infer<typeof AcquisitionEnvironmentSummarySchema>;

export const AcquisitionSchema = z.object({
  id: z.string(),
  sensor: SensorSchema,
  product: z.string(),
  acquired_at: isoDateTime,
  acquired_end: isoDateTime.nullish(),
  group: z.enum(['june', 'october', 'additional']).nullish(),
  observation_index: z.number().int().nullish(),
  reference_id: z.string().nullish(),
  reference_utc: z.string().nullish(),
  offset_from_reference_seconds: z.number().nullish(),
  aligned_geotiff: z.string().nullish(),
  polarizations: z.array(z.string()).nullish(),
  orbit_direction: z.enum(['ascending', 'descending']).nullish(),
  cloud_cover_pct: z.number().min(0).max(100).nullish(),
  qa: z.record(z.unknown()).nullish(),
  source_url: z.string().url().nullish(),
  environment: AcquisitionEnvironmentSummarySchema.nullish(),
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
  /** Distance along the transect line from its start coordinate (m). */
  x_m: z.number().finite(),
  /** Absolute USACE FRF cross-shore coordinate x (m). */
  x_frf_m: z.number().finite().nullish(),
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
    x_origin_frf_m: z.number().finite().nullish(),
    /** Cross-shore reference: x_m measured along the line from its first coordinate. */
    x_reference: z.string(),
  }),
});
export type TransectSummary = z.infer<typeof TransectSummarySchema>;
export const TransectCollectionSchema = z.object({
  type: z.literal('FeatureCollection'),
  features: z.array(TransectSummarySchema),
});

const ReliabilitySchema = z.enum(['supported', 'conditional', 'withheld']);
const TidePositionSchema = z.object({
  x_frf_m: z.number().finite().nullable(),
  x_m: z.number().finite().nullable(),
  status: ReliabilitySchema,
  reasons: z.array(z.string()),
  sigma_m: z.number().finite().nonnegative().nullish(),
  shift_m: z.number().finite().nullish(),
  slope_sensitivity_frf_m: z.tuple([z.number().finite(), z.number().finite()]).nullish(),
  slope: z.object({
    slope_m_per_m: z.number().finite().nullish(),
    slope_p10_p90_m_per_m: z.tuple([z.number().finite(), z.number().finite()]).nullish(),
    coreg_qc_flag: z.number().nullish(),
    sample_rows: z.number().int().nullish(),
    acquired_at: isoDateTime.nullish(),
  }).passthrough().optional(),
}).passthrough();

const MatchedConditionsSchema = z.object({
  water_level_m_mllw: z.number().nullable(),
  water_level_timestamp_utc: isoDateTime.nullish(),
  water_level_offset_s: z.number().nullish(),
  tide_prediction_m_mllw: z.number().nullable().optional(),
  predicted_tide_stage: z.string().nullable().optional(),
  predicted_tide_slope_m_per_h: z.number().nullable().optional(),
  observed_minus_predicted_m: z.number().nullable().optional(),
  wave_hs_m_17m: z.number().nullable(),
  wave_tp_s_17m: z.number().nullable(),
  wave_dir_deg_17m: z.number().nullish(),
  wave_hs_m_26m: z.number().nullable().optional(),
  wave_tp_s_26m: z.number().nullable().optional(),
  wind_speed_ms: z.number().nullable(),
  wind_dir_deg: z.number().nullable().optional(),
  wind_gust_ms: z.number().nullish(),
  rain_10min_mm: z.number().nullable().optional(),
  rain_24h_mm: z.number().nullable(),
  total_water_level_2pct_navd88_m: z.number().nullable().optional(),
  qualifying_station_matches: z.number().int().nullable().optional(),
}).passthrough();

const WaterlineEpochSchema = z.object({
  date: z.string(),
  acquisition_id: z.string(),
  acquired_at: isoDateTime,
  optical_qa: z.object({
    study_cells: z.number().int().optional(),
    clear_cells: z.number().int().optional(),
    cloud_cells: z.number().int().optional(),
    shadow_cells: z.number().int().optional(),
    cloud_fraction_of_scl_cells: z.number().nullable().optional(),
  }).passthrough().optional(),
  ndwi: TidePositionSchema,
  mndwi: TidePositionSchema,
  tide: TidePositionSchema,
  setup: TidePositionSchema,
  environment: MatchedConditionsSchema.nullable(),
});
export type WaterlineEpoch = z.infer<typeof WaterlineEpochSchema>;

const MeasuredChangeSchema = z.object({
  status: ReliabilitySchema,
  reasons: z.array(z.string()),
  datum: z.string().optional(),
  change_profile: z.array(z.object({ x_m: z.number().finite(), dz_m: z.number().finite() })),
});

const ErrorMetricsSchema = z.object({
  n: z.number().int().positive(),
  rmse_m: z.number().finite().nonnegative(),
  mae_m: z.number().finite().nonnegative(),
  bias_m: z.number().finite(),
});
const ValidationComparisonSchema = z.object({
  rmse_reduction_percent: z.record(z.number().finite()).optional(),
  status: ReliabilitySchema,
  n: z.number().int().nonnegative(),
  reason: z.string().optional(),
  methods: z.record(ErrorMetricsSchema).optional(),
});

export const CoastalEvidenceSchema = z.object({
  processing_version: z.string(),
  status: ReliabilitySchema,
  reasons: z.array(z.string()),
  coordinate: z.string().optional(),
  target: z.object({
    value: z.number().finite(),
    unit: z.string(),
    vertical_datum: z.string(),
    station_id: z.string(),
    source: z.string().optional(),
    description: z.string(),
  }).optional(),
  terrain: z.object({
    status: ReliabilitySchema,
    reasons: z.array(z.string()),
    datum: z.string().optional(),
    processing_version: z.string().optional(),
    native_paired_cells: z.number().int().optional(),
    mean_m: z.number().finite().nullable().optional(),
    method: z.string().optional(),
    acquisitions: z.array(z.object({
      epoch: z.string(),
      acquired_at: isoDateTime,
      source_id: z.string(),
      quality: z.object({
        coregQCFlag: z.number().nullable().optional(),
        rmsReflectorError: z.number().nullable().optional(),
        assessmentPlanesOffset: z.number().nullable().optional(),
      }).passthrough().optional(),
    }).passthrough()).optional(),
  }).passthrough().optional(),
  radar_disagreement: z.object({
    status: ReliabilitySchema,
    reasons: z.array(z.string()),
    matched_radar_cells: z.number().int().optional(),
    opposite_radar_cells: z.number().int().optional(),
    strict_overlap_cells: z.number().int().optional(),
    opposite_strict_cells: z.number().int().optional(),
    s1_minus_nisar_seconds: z.object({ june: z.number(), october: z.number() }).optional(),
    acquisitions: z.record(z.record(z.object({
      id: z.string(),
      acquired_at: isoDateTime,
      track: z.number().optional(),
      orbit_direction: z.string().optional(),
      look_direction: z.string().optional(),
      environment: MatchedConditionsSchema.nullable().optional(),
    }).passthrough())).optional(),
  }).passthrough(),
  validation: z.object({
    scope: z.string(),
    targets: z.record(z.object({
      raw_vs_tide: ValidationComparisonSchema,
      raw_vs_tide_vs_setup: ValidationComparisonSchema,
      by_date: z.record(ValidationComparisonSchema),
    })),
  }),
}).passthrough();
export type CoastalEvidence = z.infer<typeof CoastalEvidenceSchema>;

export const TransectDetailSchema = TransectSummarySchema.extend({
  profiles: z.array(ProfileSchema),
  boundaries: z.array(BoundaryPickSchema),
  measured_change: MeasuredChangeSchema.optional(),
});
export type TransectDetail = z.infer<typeof TransectDetailSchema>;

// ---------- /api/analysis/{id} ----------
export const ReconstructedWaterlineSchema = z.object({
  x_frf_m: z.number().finite().nullable(),
  x_m: z.number().finite().nullable(),
  cv_rmse_m: z.number().nonnegative().nullable(),
  source: z.string(),
  status: z.string(),
  acquired_at: isoDateTime.nullish(),
  granule_id: z.string().nullish(),
  tide_aware_experimental_x_frf_m: z.number().finite().nullish(),
  tide_aware_experimental_x_m: z.number().finite().nullish(),
  tide_aware_cv_rmse_m: z.number().nonnegative().nullish(),
  mndwi_x_frf_m: z.number().finite().nullish(),
});
export type ReconstructedWaterline = z.infer<typeof ReconstructedWaterlineSchema>;

export const ReconstructedDunetoeSchema = z.object({
  accepted_x_frf_m: z.number().finite().nullable(),
  accepted_x_m: z.number().finite().nullable(),
  bayes_map_x_frf_m: z.number().finite().nullable(),
  bayes_map_x_m: z.number().finite().nullable(),
  bayes_median_x_frf_m: z.number().finite().nullable(),
  bayes_median_x_m: z.number().finite().nullable(),
  ci90_low_frf_m: z.number().finite().nullable(),
  ci90_low_m: z.number().finite().nullable(),
  ci90_high_frf_m: z.number().finite().nullable(),
  ci90_high_m: z.number().finite().nullable(),
  posterior_sd_m: z.number().nonnegative().nullable(),
  vv_vh_disagreement_m: z.number().nonnegative().nullable(),
  vv_vh_disagreement_limit_m: z.number().nonnegative().nullable(),
  cv_rmse_conservative_m: z.number().nonnegative().nullable(),
  baseline_weighted_x_frf_m: z.number().finite().nullish(),
  radar_vv_x_frf_m: z.number().finite().nullable(),
  radar_vv_x_m: z.number().finite().nullable(),
  radar_vh_x_frf_m: z.number().finite().nullable(),
  radar_vh_x_m: z.number().finite().nullable(),
  nisar_hh_x_frf_m: z.number().finite().nullish(),
  nisar_hh_x_m: z.number().finite().nullish(),
  nisar_hv_x_frf_m: z.number().finite().nullish(),
  nisar_hv_x_m: z.number().finite().nullish(),
  source: z.string(),
  status: z.string(),
  acquired_at: isoDateTime.nullish(),
  granule_id: z.string().nullish(),
});
export type ReconstructedDunetoe = z.infer<typeof ReconstructedDunetoeSchema>;

export const ValidationLidarRefsSchema = z.object({
  wetdry_x_frf_m: z.number().finite().nullable(),
  wetdry_x_m: z.number().finite().nullable(),
  dunetoe_x_frf_m: z.number().finite().nullable(),
  dunetoe_x_m: z.number().finite().nullable(),
  contour_1p5m_x_frf_m: z.number().finite().nullable(),
  contour_1p5m_x_m: z.number().finite().nullable(),
  usage: z.string(),
});
export type ValidationLidarRefs = z.infer<typeof ValidationLidarRefsSchema>;

export const AnalysisEpochSchema = z.object({
  date: z.string(),
  epoch_label: z.string(),
  waterline: ReconstructedWaterlineSchema,
  dunetoe: ReconstructedDunetoeSchema,
  validation_lidar: ValidationLidarRefsSchema,
});
export type AnalysisEpoch = z.infer<typeof AnalysisEpochSchema>;

export const PhysicsModelOutputSchema = z.object({
  status: z.enum(['available', 'unavailable']),
  reason: z.string().nullish(),
  vertical_datum: z.string().nullish(),
  target_epoch_label: z.string().nullish(),
  points: z
    .array(z.object({ x_m: z.number().finite(), z_m: z.number().finite(), sigma_m: z.number().nonnegative() }))
    .default([]),
});
export type PhysicsModelOutput = z.infer<typeof PhysicsModelOutputSchema>;

export const AnalysisSchema = z.object({
  transect_id: z.string(),
  frf_y_m: z.number().finite(),
  x_origin_frf_m: z.number().finite(),
  x_reference: z.string(),
  analysis_crs: z.string().regex(/^EPSG:\d+$/),
  model_name: z.string(),
  model_version: z.string(),
  state_scope: z.string(),
  inferred: z.literal(true),
  units: z.literal('m'),
  uncertainty_method: z.string(),
  inputs: z.array(z.string()),
  epochs: z.array(AnalysisEpochSchema).min(1),
  october_minus_june: z
    .object({
      waterline_shift_m: z.number().finite().nullable(),
      dunetoe_shift_m: z.number().finite().nullable(),
    })
    .nullish(),
  skill: z.record(z.number().nullable()).nullish(),
  coastal_observations: z.object({
    processing_version: z.string(),
    waterlines: z.array(WaterlineEpochSchema),
    terrain: MeasuredChangeSchema,
  }).optional(),
  physics_model: PhysicsModelOutputSchema.nullish(),
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

// Independent NISAR experiments. Withheld products never require fabricated metrics.
export const NisarEvidenceSchema=z.object({
  processing_version:z.string(),
  input_qa:z.object({status:z.string(),reason:z.string().optional()}).passthrough(),
  shoreline:z.object({status:z.string(),epochs:z.record(z.object({
    candidate_rows:z.number().int().nonnegative().optional(),
    comparability:z.object({status:z.string()}).passthrough().optional(),
  }).passthrough()).default({})}).passthrough(),
  terrain_ablation:z.object({
    status:z.string(),n:z.number().int().nonnegative(),reason:z.string().optional(),
    scientific_target:z.string(),units:z.literal('m'),
    metrics:z.record(ErrorMetricsSchema).optional(),
    acquisition_pairs:z.record(z.object({june_id:z.string(),october_id:z.string(),june_utc:isoDateTime,october_utc:isoDateTime}).passthrough()).optional(),
    per_strip:z.array(z.object({frf_y_start_m:z.number(),n:z.number().int(),C_minus_B_rmse_m:z.number().finite()}).passthrough()).optional(),
    ablation:z.object({C_minus_B_rmse_m:z.number().finite(),C_minus_B_rmse_percent:z.number().finite().nullable(),strips_with_lower_rmse_for_C:z.number().int()}).passthrough().optional(),
    terrain_model_deployment:z.object({status:z.string(),reason:z.string()}).optional(),
  }).passthrough(),
}).passthrough();
export type NisarEvidence=z.infer<typeof NisarEvidenceSchema>;
