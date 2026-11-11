# Bill of materials

What the Cul2vate install uses. Prices are what Cul2vate paid in April 2026.

| Item | What we used | Qty | Notes |
|---|---|---|---|
| IP camera | Hikvision AcuSense 5MP varifocal | 1 | $329.95. Needs an ISAPI snapshot URL with digest auth. DC12V or PoE. |
| PoE+ injector | TP-Link Omada POE160S, gigabit | 1 | 802.3af/at. Powers the camera over the Cat6 run. |
| ChArUco sign | 36×44 in Dibond, matte laminate, 6 pre-drilled ¼ in holes | 1 | $200 printed locally. Board parameters below. |
| Masonry screws | ¼ in Tapcon, plus spacers | 6 | Mount the sign flat on the wall. |
| Floor tape | Yellow | 1 roll | Marks the staging zone. Only goods inside it count. |
| Cat6 cable | Outdoor-rated | 1 run | Network switch or extender → injector → camera. |
| iPad | Any spare iPad that runs Scriptable | 1 | Stays on the charger at the dock. |

## Board parameters

| Setting | Value |
|---|---|
| Dictionary | `DICT_6X6_50` |
| Grid | 8 × 10 squares |
| Square size | 4.0 in |
| Pattern area | 32 × 40 in, inside a 36 × 44 in print with a 2 in border |
| Markers | 40 |
| Inner corners | 63 |

The prompt tells the model the 4 in square size. An older generator from the Branch
prototype used `DICT_4X4_50` with 6 in squares, which does not match this board.

You also need a Wi-Fi network that puts the iPad and the camera on the same LAN, and a
hammer drill with a masonry bit for the sign.

Not needed: a scale, a speaker, a hardware button, or any on-site computer. The iPad
is the button and pulls the frame itself.
