# Runtime asset provenance

The character sprites and leaf texture were generated for this project and are included locally so the application works offline. Character motion, masks, lighting and cloud flow are implemented by the renderer.

## Generated example house

`examples/house.json` retains the authorized configuration's projector polygons and effect settings. It contains no embedded photos, camera calibration, photo measurements, personal setup notes, location names or private paths. All labels are English. `examples/layout.png` is a diagram drawn from those coordinates; the bay glazing divisions are illustrative and do not change the projector masks.

The built-in image generation tool created `examples/house-day.png` from the coordinate diagram, then created an initial night version from that generated image. Those initial generations used no original house photograph. The revised `examples/house-night.png` uses the generated night image as its edit target and a local real night photograph solely to guide lighting, exposure and phone-camera quality. The fictional architecture and composition are retained; the real house, streetlight and other scene details are not copied. The real photograph remains in the ignored local archive. The generated references approximate the layout and should be aligned before use on a real building.

Day prompt:

> Use case: sketch-to-render. Asset: synthetic daylight example house for an offline projection mapping editor. The supplied reference image is a diagram drawn ONLY from configuration polygon coordinates, not a photograph. Render a fictional red-brown brick house facade with EXACTLY this silhouette and camera framing. Keep the portrait 800:1280 ratio, roof finial at (317,145), steep white-trimmed gable apex at (317,160), left roof end (75,526), right roof end (740,735), slim attic window x304..343 y392..492, right upper two-pane window x400..536 y640..776, left upper window hidden by dense leafy foreground tree x50..345 y527..990, low projecting three-sided bay window with white flat roof trim x320..625 y888..907 and dark glazing down to y1000. House ends at y1000; foreground below to y1280, sky above. Preserve all these relative positions precisely, including the asymmetric perspective and offset apex. Realistic architectural materials, white painted wood trim, cloudy soft daylight, empty neutral surroundings. No house number, address, street signs, text, people, vehicles, watermarks or identifiable neighboring buildings. This is invented example imagery, not a reconstruction of an actual photograph. Match the diagram's layout while replacing flat diagram colors with plausible texture.

Initial night prompt:

> Use case: lighting-weather. Edit target: the supplied AI-generated fictional house image, itself based only on a polygon configuration diagram. Create the matching night-time example. Change ONLY time of day and lighting to dark blue hour / early night with soft ambient moonlight, a dark navy sky, slightly warm interior light behind the same windows. Keep every architectural feature, tree leaf silhouette, exact perspective, crop, resolution, roof corners, attic window, two-pane upper window, bay window, materials, framing and every object in exactly the same pixel position. Do not add projection effects or decorations. Retain legibility of the brick facade in the shadows. No text, house numbers, addresses, watermarks, people or vehicles.

Revised night prompt (built-in image generation tool):

> Use case: lighting-weather. Asset type: replacement fictional night reference photograph for a projection mapping desktop app. Input image 1 (examples/house-night.png) is the EDIT TARGET and sole source of architecture, tree, foreground, framing and exact geometric layout. Input image 2 is a real nighttime photograph used ONLY as a reference for exposure, ambient lighting and consumer phone camera quality. Edit image 1 to resemble an ordinary phone photo taken at true night as in image 2. Preserve image 1's exact fictional house, roof silhouette and finial, all window and bay corners, tree silhouette, bushes, grass, perspective, crop, aspect ratio, and resolution (992 by 1586). Change ONLY lighting, sky appearance and photographic finish. Match image 2's nearly black, very faintly charcoal-gray sky without conspicuous clouds or bright blue twilight; subdued neutral gray-brown brick in deep shadow; dim pale roof trim; natural uneven low-intensity ambient illumination with some soft neutral/warm spill on lower facade and leaves, much darker upper facade and foreground. Keep only the narrow attic window and ground-floor bay lit: the attic is a modest pale warm-white slit and the bay has bright warm-white household interior light with slight clipped highlights and soft bloom. The two-pane upstairs window should be unlit/dark, still showing its pale frame and faint curtains/reflections. Match the reference's everyday low-light smartphone quality: slightly soft edges and foliage, restrained fine luminance/chroma noise and mild noise reduction smearing, limited shadow detail, modest highlight bloom. Retain enough faint facade and trim visibility for alignment. Avoid the existing target's polished architectural render, crisp uniformly visible individual bricks, saturated blue sky, dramatic clouds, uniform moonlight and uniformly amber glowing windows. IMPORTANT: ignore the real reference house design and its objects entirely; do not copy any architecture, camera framing, street lamp or pole, bright streetlight orb, glare streaks, window-glass reflections, indoor window frame, garden layout, shed or personal details. No new objects, projection effects, decorations, text, addresses, logos, people, vehicles, or watermark. Preserve target composition and pixel positions.

The generated replacement is 992 × 1585 pixels; the example configuration records that actual size and retains its existing 800 × 1280 display placement and projector polygons.

## Replacement smoke textures

The built-in image generation tool produced four new RGBA textures. Each replaces the old periodic noise field with irregular billows and fine wisps. The renderer's existing two-layer tiling, motion and loop timing are retained. The generated textures request matching edges; generated edge continuity is approximate.

### blue-purple.png

> Use case: stylized-concept. Asset type: square tileable volumetric smoke VFX texture for Halloween projection mapping. Brand-new asset. Thick beautiful rolling billows of colored smoke with fine turbulent wisps, soft depth, substantial dark transparent gaps between cloud masses, no regular stripes, no uniform noise or rainbow. Palette strictly deep electric blue with violet shadows and blue luminous highlights. Colored light stays saturated, no white hotspots. Orthographic flat texture, no perspective, no ground, no horizon, no identifiable objects. Fill the entire square naturally with varied medium and large eddies, seamlessly tile on all four edges. True RGBA transparency with soft alpha, transparent spaces between clouds. No text, border, characters, scenery, black background or checkerboard pattern. The software scrolls and warps this texture, so make the edges match and clouds broadly distributed.

### green-smoke.png

> Use case: stylized-concept. Asset type: square tileable volumetric smoke VFX texture for Halloween projection mapping. Brand-new asset. Thick beautiful rolling billows of colored smoke with fine turbulent wisps, soft depth, substantial dark transparent gaps between cloud masses, no regular stripes, no uniform noise or rainbow. Palette strictly emerald green with subtle teal shadows and yellow-green luminous highlights. Colored light stays saturated, no white hotspots. Orthographic flat texture, no perspective, no ground, no horizon, no identifiable objects. Fill the entire square naturally with varied medium and large eddies, seamlessly tile on all four edges. True RGBA transparency with soft alpha, transparent spaces between clouds. No text, border, characters, scenery, black background or checkerboard pattern. The software scrolls and warps this texture, so make the edges match and clouds broadly distributed.

### purple-smoke.png

> Use case: stylized-concept. Asset type: square tileable volumetric smoke VFX texture for Halloween projection mapping. Brand-new asset. Thick beautiful rolling billows of colored smoke with fine turbulent wisps, soft depth, substantial dark transparent gaps between cloud masses, no regular stripes, no uniform noise or rainbow. Palette strictly rich violet with magenta shadows and pink-violet luminous highlights. Colored light stays saturated, no white hotspots. Orthographic flat texture, no perspective, no ground, no horizon, no identifiable objects. Fill the entire square naturally with varied medium and large eddies, seamlessly tile on all four edges. True RGBA transparency with soft alpha, transparent spaces between clouds. No text, border, characters, scenery, black background or checkerboard pattern. The software scrolls and warps this texture, so make the edges match and clouds broadly distributed.

### red-fire.png

> Use case: stylized-concept. Asset type: square tileable volumetric smoke VFX texture for Halloween projection mapping. Brand-new asset. Thick beautiful rolling billows of colored smoke with fine turbulent wisps, soft depth, substantial dark transparent gaps between cloud masses, no regular stripes, no uniform noise or rainbow. Palette strictly deep crimson red with orange luminous highlights, smoky clouds rather than flames. Colored light stays saturated, no white hotspots. Orthographic flat texture, no perspective, no ground, no horizon, no identifiable objects. Fill the entire square naturally with varied medium and large eddies, seamlessly tile on all four edges. True RGBA transparency with soft alpha, transparent spaces between clouds. No text, border, characters, scenery, black background or checkerboard pattern. The software scrolls and warps this texture, so make the edges match and clouds broadly distributed.

## Other runtime assets

- `ghost.png`: translucent ivory cloth apparition.
- `young-ghost.png`: friendly cloth ghost.
- `young-skeleton.png`: friendly skeleton texture used by the articulated animation.
- `young-candle.png`: ivory candle sprite.
- `older-wraith.png`: theatrical spectral apparition.
- `tree-pattern.png`: transparent leaf and vein texture.
- `cheshire-head-v1.png`, `cheshire-wink-v1.png`: generated cat face layers for the fading and winking effect.
- `atmosphere/fire.png` and `atmosphere/camouflage-net.png`: existing procedural flame and tree textures, retained for the runtime effects.

Original procedural smoke textures, experiments and generation scripts are archived locally under the ignored `private/` directory.
