# SailFrames v2.0.0 — Shopping List

**Scope:** Components needed to deploy the v2.0.0 horn detection feature on RC signal-boat units.
**Quantity assumption:** 80-unit fleet, of which ~4-6 will be RC units (signal boats across two clubs + spares).
**Approach:** KY-038 mounted **inside** sealed B1 enclosure. No acoustic vent. Microphone listens through the polycarbonate lid at <2m from horn. No drilling, no Gore, no cable glands.

---

## Required for v2.0.0 deployment

### 1. KY-038 sound sensor modules

**Recommended: Meccanixity 4-pack from Amazon — $6.79**

Specs confirmed for your fleet:
- Electret condenser microphone + LM393 comparator
- Digital output (HIGH when sound > threshold)
- Adjustable trimpot for threshold
- 4-pin header: VCC, GND, DOUT, AOUT
- Operates 3.3V (matches your J_AUX pin 1 supply)
- Standard sensitivity (NOT the higher-sensitivity KY-037 variant)

**Quantity to buy: 2 × 4-packs = 8 modules (~$14)**

Covers:
- 4-6 RC units (signal-boat installations across both clubs)
- 2-3 bench testing modules
- Spares

**Why KY-038 and not KY-037:**
The KY-037 is the higher-sensitivity variant of the same family. For a horn at <2m firing directly at the sensor, the KY-038's standard sensitivity is the right choice — it's loud enough to trigger easily, but discriminates better against background noise (wind, distant horns, voices) than the more sensitive KY-037 would.

The horn signal reaching the KY-038 through the polycarbonate lid will be ~89-104 dB SPL. Background marine noise is ~50-70 dB SPL. That's a 30+ dB signal-to-noise margin — plenty of room to set a threshold that triggers reliably on the horn but rejects everything else.

**Amazon link**: search "MECCANIXITY KY-038 4 Pcs" or click any KY-038 4-pack from a Prime seller.

**Backup options if Meccanixity is out of stock:**
- Any KY-038 4-pack or 5-pack from a Prime seller, $5-12 range
- AliExpress 10-packs at ~$8 with 2-4 week shipping
- HiLetgo, ELEGOO, KEYESTUDIO branded equivalents — all the same circuit

---

### 2. J_AUX pin headers

For the B1 v1 PCB. Already covered in B1 BOM if J_AUX header was added.

**If not already in BOM:**
- **Würth 61300611121** — 1×6 vertical pin header, 2.54 mm pitch, gold-plated
- DigiKey part 732-5402-ND, $0.18 each
- Order 100 for $18 (covers 80-unit fleet + spares)

---

### 3. Connection between KY-038 and J_AUX

Three wires needed per RC unit: 3V3, GND, AUX_INT (DOUT from sensor → GPIO36 on ESP32).

**Option A: Dupont jumper wires (easiest for pilot)**
- 20cm female-to-female Dupont jumpers, 40-pack
- Amazon search: "Dupont jumper wire 40-pin 20cm female-to-female"
- ~$5 for a 40-pack
- Connects directly between KY-038's 4-pin header and J_AUX 6-pin header

**Option B: Soldered wire harness (for production cleanliness)**
- 22 AWG silicone-jacketed wire in 3 colors (red/black/yellow)
- Short pre-crimped 0.1" socket housings if you want professional connectors
- Hand-cut 5-8 cm lengths, strip, solder to KY-038 pads, terminate at J_AUX side with a connector or direct solder
- ~$10 in materials, plus your time

For initial pilot and the first 4-6 RC units, **Option A (Dupont jumpers)** is fine — they're reliable when installed inside a sealed enclosure with no vibration/strain.

---

### 4. Mechanical mounting hardware

To secure the KY-038 inside the B1 enclosure:

**Option A: Hot glue (simplest)**
- A few dots of hot glue on the back of the KY-038 PCB, stick to the inside of the B1 lid with mic facing outward
- $5 hot glue gun if you don't have one; otherwise zero cost
- Easy to remove if you need to adjust trimpot

**Option B: M2.5 standoffs + adhesive base**
- 4 × M2.5 brass standoffs, 5-8 mm tall
- 4 × M2.5 screws
- Adhesive-back nylon spacers as the base, glued to the lid
- ~$5 from Amazon
- Cleaner, more serviceable; allows easy KY-038 swap if needed

Either works. For the pilot, hot glue is fine.

---

## Total cost summary

| Item                                  | Quantity | Cost          |
|---------------------------------------|----------|---------------|
| KY-038 sound sensor modules           | 2×4-pack | $14           |
| J_AUX pin headers (if not in BOM)     | 100      | $18           |
| Dupont jumper wires (40-pack)         | 1        | $5            |
| Hot glue or M2.5 hardware             | -        | $5            |
|                                       |          |               |
| **Total (with headers)**              |          | **$42**       |
| **Total (headers already in BOM)**    |          | **$24**       |

Per-RC-unit cost: about $3 in materials.

---

## Order timing

**Today: order from Amazon Prime for tomorrow delivery**
- 2 × Meccanixity KY-038 4-packs ($14)
- Dupont jumper wires 40-pack ($5)
- (Optional) Hot glue gun if needed ($5)

Total: ~$19, in your hands tomorrow.

**Next week: bench test on E1**
- Wire one KY-038 to any spare GPIO on an E1 dev board
- Adjust trimpot, blow an air horn at 1-2m, verify clean triggering
- Validate the ISR-based timestamping with a few horn fires
- Confirm no false triggers from typical marina noise sources (radio, voices, halyards)

**When B1 v1 arrives from JLCPCB:**
- Wire KY-038 to J_AUX header per the firmware spec
- Mount inside B1 lid with hot glue, mic facing outward
- Tune trimpot at intended deployment position on the signal boat
- Run first field test in "log only" mode (records but doesn't broadcast MSG_START_LOCKED yet)
- Once validated, enable broadcasting and integrate into live race operations

---

## What's NOT needed

To be explicit about what you're skipping vs the previous shopping list:

- ~~Gore acoustic vent (VE7/PMF series)~~ — not needed; polycarbonate lid is acoustically transparent enough at horn SPL
- ~~Cable glands and external mount enclosures~~ — KY-038 stays inside B1
- ~~Drilling holes in B1 lid~~ — preserves IP68 integrity
- ~~Marine cable for external runs~~ — all connections internal to B1

This is significantly simpler than the previous plan. The "horn is very loud at very close range" reality of the signal-boat installation eliminates 90% of the acoustic-coupling problem.

---

## Future shopping (NOT v2.0.0, for reference)

For v2.1+ RM3100 magnetometer upgrade (deferred):

- **PNI RM3100 breakout** — Drotek Professional Grade ($45-55), or PNI direct (SKU 14190, $40), or GNSS.store module ($40)
- Buy 1 to bench-test on an E1 first
- Connects to J_AUX with same 4 wires (3V3, GND, SDA, SCL) — no AUX_INT needed since RM3100 supports polled mode

---

## Questions resolved

1. ~~Drill hole in B1 lid?~~ → **No.** KY-038 inside, acoustic path through polycarbonate is adequate.
2. ~~Internal vs external mount?~~ → **Internal.** Sealed enclosure preserved.
3. ~~Gore vent vs generic PTFE?~~ → **Neither.** No vent needed.
4. ~~Signal boat coordination?~~ → Trimpot tuned at install on each specific signal boat. RC unit is portable between signal boats; trimpot might need re-tuning if installed on different boat with different acoustics.
5. **Spare RC units per club?** → Recommend 1 spare per club beyond active count. With 2 clubs, that's 4-6 total RC units (1-2 active + 1 spare per club).
