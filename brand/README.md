# Brand assets

Brand artwork for Aeolus (created 2026-06-05). Mark = a cyan wind-gust → spiral
curl (a nod to Aeolus, Greek keeper of the winds); wordmark in Helvetica Neue.
Brand cyan: **#29AFCA**. Wordmark slate: **#243B53** (light) / white (dark).

| File | Size | Use |
|---|---|---|
| `icon.png` | 256×256 | HA `icon.png` (square, transparent) |
| `icon@2x.png` | 512×512 | HA `icon@2x.png` |
| `logo.png` | ≤256 longest side | HA `logo.png` (mark + wordmark, light UIs) |
| `logo@2x.png` | ≤512 longest side | HA `logo@2x.png` |
| `dark_logo.png` | ≤256 | HA `dark_logo.png` (white wordmark, dark UIs) |
| `dark_logo@2x.png` | ≤512 | HA `dark_logo@2x.png` |

All PNG, real alpha transparency, trimmed, centered. `dark_icon` intentionally
omitted — the cyan mark reads on both light and dark backgrounds.

## Remaining for the `brands` quality-scale rule
Submit these to **[home-assistant/brands](https://github.com/home-assistant/brands)**
under `custom_integrations/aeolus/` (icons → `icon.png`/`icon@2x.png`, logos →
`logo.png`/`logo@2x.png`, plus the `dark_logo*` variants). The brands repo runs an
image-optimization check; run the finals through `pngquant`/`optipng` if CI asks.
HA Core also serves this in-tree `brand/` copy for post-install icons.

Regeneration: the keying/trim/typeset steps are scripted (Pillow + numpy, venv
`~/venvs/aeolus`); source art in `~/Documents/Home Assistant Work/Aeolus/`.
