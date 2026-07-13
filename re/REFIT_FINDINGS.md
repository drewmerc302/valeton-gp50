# NAM → SnapTone refit (reverse-engineered from 5868USB.dylib)

The conversion runs on class **`AppNamConvertThread`** (vtable `0x1884b8`, `run()` @ `0x4f30`).
Ghidra call graph + strings + math signatures.

## Pipeline (AppNamConvertThread::run)

1. **`run()`** → `namConverterCloData` (raw-data path) or `namConverter` (file path),
   selected by a flag at `this+0x220`.
2. **`getConvertNormalWav`** — load + normalize the DI wav (bundled `flutter_assets/
   assets/wavs/nam_input_wav.wav`).
3. **`getNamOutput` (6.5 KB)** — parse the `.nam` JSON (keys `architecture`/`config`/
   `weights`/`metadata`/`sample_rate`/`version`; error `"Corrupted model file is missing
   weights."`) and **run the genuine NAM WaveNet inference** — it uses
   `nam::activations::Activation::using_fast_tanh` (NeuralAmpModelerCore's own code, statically
   linked). Output = the amp's target response to the DI.
4. **`startClone` (32.5 KB)** — **fit a compact proprietary model** to the (DI → NAM-output)
   pair. Uses an **IR convolver** (`convolverInit`, `zzy_ir_instance_f32`), `log2`/`exp2`/
   `expf` shaping, small dims (loops bounded at 16), then **quantizes floats → bytes**
   (`>>8/>>16/>>24`) to produce the ~2755-byte SnapTone.
5. Serialize + upload via the write protocol (see SNAPTONE_PROTOCOL.md).

## Conclusion

**SnapTone is a refit, definitively — not a repackage.** Valeton runs the real NAM to
generate reference audio, then fits a much smaller proprietary model (evidence points to a
block model: a static nonlinearity + a linear IR/filter, ~16-wide, quantized), which is why
it's ~20× smaller than the NAM's weights and can run real-time on the pedal DSP.

## Implications for the product
- **Feature 4 (generate SnapTones ourselves, no Suite):** would require replicating
  `startClone` — the compact model format + the fitting math (a 32 KB routine). Feasible but
  a large RE project. Until then, SnapTone payloads must come from a Suite conversion.
- **Features 5/6 (reassign/replace SnapTone/IR across patches):** do NOT need the refit — they
  only move/reference existing SnapTones. Unblocked by the cracked write protocol + checksum;
  need only a patch-write capture to learn the patch-body format.

## Key addresses (5868USB.dylib arm64)
- `AppNamConvertThread::run` @ 0x4f30 · `getNamOutput` @ 0x6480 · `startClone` @ 0x15904
- `getConvertNormalWav` @ 0x82d0 · `namConverterCloData` @ 0x5d64 · `namConverter` @ 0x53bc
- CRC-8/0x07 table @ 0xf5f10 · `getMidiMessage` (packet+checksum) @ 0x4c910
- Ghidra scripts: DecompileValeton / FindCrcUser / FindRefit / FindRun (in `re/`).
