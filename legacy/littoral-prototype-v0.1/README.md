# Littoral — Coastal Analysis Workstation

First UI release for Duck coastal reconstruction. Independent NASA Space Apps project, not an official operational service.

## Run
Serve dist/ using a static server. No build step or runtime dependencies. Font loading is optional; system fallbacks work offline.

## Working interactions
Four workspaces; synthetic map pan/zoom; selectable linked transects; layer controls; acquisition comparison swipe; profile hover readouts; analysis alignment sensitivity; timeline filters; schema-checked browser-local profile imports; session JSON export and help dialog.

## Data state
All initial geometry and curves are synthetic. No raster or actual satellite observation is embedded. Dataset register describes planned inputs. Profile template downloads from Evidence. Imports replace profiles, not the schematic map. Session export includes the profiles; imported sessions restore profiles only, not every saved display setting. No server upload or persistent browser storage is used.

## Profile contract
JSON label + profiles[]. Each profile: unique id, label, units: m, source, verticalDatum, june: [{x,z}], october: [{x,z}]. Cross-shore x values must strictly increase. Both epochs must use a common local horizontal and vertical reference. Optional boundaries: {radar,waterJune,waterOctober}, all in the same x frame. June/October remain fixed UI epoch slots in this release. Do not load differently dated observations without first adapting the epoch model.

Before real-data integration: replace schematic map with georeferenced layers, connect actual acquisition records and datum/QA metadata, add field-validation and uncertainty displays. Imported values are rendered as supplied, not scientifically verified.

## Checks
JavaScript syntax passed. Profile ingestion accepted a valid fixture and rejected duplicate IDs, unsorted distances, nonfinite heights, wrong units and missing source. Browser checks confirmed transect selection updates the linked profile, expanded analysis preserves selection, alignment slider updates, event filters work and the evidence register opens. Profile file selection and mobile browser layout have not yet been end-to-end tested.
