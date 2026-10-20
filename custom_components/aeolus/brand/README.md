# Brand assets

Brand artwork for Aeolus (created 2026-06-05). Mark = a cyan wind-gust → spiral
curl (a nod to Aeolus, Greek keeper of the winds); wordmark in Helvetica Neue.
Brand cyan: **#29AFCA**. Wordmark slate: **#243B53** (light) / white (dark).

| File | Size | Use |
|---|---|---|
| `icon.png` | 256×256 | HA `icon.png` (square, transparent) |
| `icon@2x.png` | 512×512 | HA `icon@2x.png` |
| `dark_icon.png` | 256×256 | HA `dark_icon.png` (brighter cyan #73CBDC, dark UIs) |
| `dark_icon@2x.png` | 512×512 | HA `dark_icon@2x.png` |
| `logo.png` | ≤256 longest side | HA `logo.png` (mark + wordmark, light UIs) |
| `logo@2x.png` | ≤512 longest side | HA `logo@2x.png` |
| `dark_logo.png` | ≤256 | HA `dark_logo.png` (white wordmark, dark UIs) |
| `dark_logo@2x.png` | ≤512 | HA `dark_logo@2x.png` |

All PNG, real alpha transparency, trimmed, centered. `dark_icon` uses a brighter
cyan (#73CBDC = brand cyan lifted ~35% toward white) for crispness on dark UIs.

## The `brands` quality-scale rule
Satisfied in-tree. Home Assistant 2026.3 and later serves these files from
`custom_components/aeolus/brand/` through its Brands Proxy, so no
home-assistant/brands pull request is needed. That repository now closes
submissions for custom integrations automatically.

Regeneration: the keying/trim/typeset steps are scripted (Pillow + numpy, venv
`~/venvs/aeolus`); the source art is kept outside this repository.
