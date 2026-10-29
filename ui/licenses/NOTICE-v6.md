# Third-party notices: v6 UI

Everything below is self-hosted in `ui/`. The app loads nothing from the network.

| Component | Version / file | Licence | Notes |
|---|---|---|---|
| three.js | r164 (npm `three@0.164.1`): `vendor/three/build/three.module.min.js`, and 8 postprocessing + 4 shader modules under `vendor/three/examples/jsm/` | MIT (`three.js-r164-MIT.txt`) | Copied unmodified. Keep the licence text alongside. |
| Big Shoulders Display | weight 900, latin + latin-ext (`fonts/BigShouldersDisplay-900-*.woff2`) | SIL OFL 1.1 (`BigShouldersDisplay-OFL.txt`) | Google Fonts build. |
| Martian Mono | variable wght 100–800, wdth 75–112.5, latin + latin-ext (`fonts/MartianMono-var-*.woff2`) | SIL OFL 1.1 (`MartianMono-OFL.txt`) | Google Fonts build. |
| Noto Sans JP | weight 400, subset to 危険注意 only (`fonts/NotoSansJP-400-kiken-chui.woff2`) | SIL OFL 1.1 (`NotoSansJP-OFL.txt`; Reserved Font Name "Source") | Google Fonts subset (`text=` API). The family name is "Noto Sans JP", not "Source", so the RFN clause is respected. |

OFL fonts may be bundled with software. They may not be sold on their own, and the licence must ship with them.

The legacy v5 UI's licences (Bungee, Geist Pixel, Pixelarticons) stay in this folder for `ui/legacy/`.
