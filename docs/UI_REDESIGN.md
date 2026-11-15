# Poltergeist interface

The integrated React interface uses a full-map layout, neutral chrome and one panel at a time. Explore introduces the study; Layers provides a single overlay choice; Compare opens June/October elevation comparison automatically; Findings starts with two feature estimates and reveals acquisition/validation tables on request. About holds sources, map help and optional current NOAA conditions. Escape closes the active panel and profile. Only available overlays are selectable. There are no default opacity, tilt or exaggeration sliders.

The background is Esri World Imagery with provider attribution. It is orientation imagery, not historical survey imagery. The survey selector changes scientific overlays and measured terrain. MapLibre displays 2D/3D terrain with the USACE LiDAR DEM at the study site and regional terrain in gaps. True scale is the default; a twofold enhancement is an explicit optional setting. Comparison uses each side's corresponding survey terrain.

Google Photorealistic 3D Tiles are not connected. They require a Google Cloud project, an enabled Map Tiles API, billing and an API key, plus a compatible 3D Tiles renderer. No key or billing project was provided. The About panel offers a direct Google Earth location link. Current satellite imagery over surveyed elevation is not presented as Google's photorealistic mesh.

The existing localhost:5173 dev process was serving stale transformed modules. The verified production preview uses localhost:4174, with its API at localhost:8002. These are local preview addresses, not deployment configuration. To build for another API, set VITE_API_BASE_URL before `npm run build` and allow the actual frontend origin in POLTERGEIST_CORS_ORIGINS.

Browser checks: real satellite imagery, connected study layers, 2D/3D state, June/October comparison selection, findings loaded from API and a 390px-wide mobile bottom panel. TypeScript, production build and 13 frontend unit tests pass. The updated end-to-end scenario is supplied for reproducible local testing; this turn's interaction verification used the browser directly.
