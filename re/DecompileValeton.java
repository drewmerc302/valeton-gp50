// DecompileValeton.java — Ghidra headless postScript.
// Decompiles the Valeton 5868USB.dylib conversion + MIDI-send functions and their
// direct callees, to recover: the SnapTone refit (_namConvertClo*) and the packet
// builder + checksum (_sendMidiMessage). Also lists 256-entry byte/int tables
// (CRC-table hint). Output -> re/ghidra_valeton_out.txt
// @category Valeton

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class DecompileValeton extends GhidraScript {

    static final String[] TARGET_SUBSTR = {
        "namConvertClo", "appNamConvert", "sendMidiMessage", "openMidiFilePath",
        "convertNormWavData", "registerSendPort"
    };
    static final String OUT = "/Users/drewmerc/workspace/valeton/re/ghidra_valeton_out.txt";

    DecompInterface di;
    PrintWriter w;
    Set<Long> done = new HashSet<>();

    @Override
    public void run() throws Exception {
        di = new DecompInterface();
        di.openProgram(currentProgram);
        w = new PrintWriter(new FileWriter(OUT));
        w.println("== Valeton 5868USB.dylib decompile ==");
        w.println("program: " + currentProgram.getName());

        FunctionManager fm = currentProgram.getFunctionManager();
        List<Function> targets = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) {
            String n = f.getName();
            for (String s : TARGET_SUBSTR) {
                if (n.contains(s)) { targets.add(f); break; }
            }
        }
        w.println("matched target functions: " + targets.size());
        for (Function f : targets) w.println("  " + f.getName() + " @ " + f.getEntryPoint());
        w.println();

        // decompile each target + its direct callees (1 level)
        for (Function f : targets) {
            dumpFunction(f, "TARGET");
            for (Function callee : f.getCalledFunctions(monitor)) {
                dumpFunction(callee, "  callee-of " + f.getName());
            }
        }

        // scan for 256-entry constant tables (CRC-table hint) in initialized memory
        w.println("\n== candidate 256-entry byte tables (CRC hint) ==");
        scanTables();

        w.close();
        println("wrote " + OUT);
    }

    void dumpFunction(Function f, String tag) {
        long key = f.getEntryPoint().getOffset();
        if (done.contains(key)) return;
        done.add(key);
        w.println("\n---------------------------------------------------------------");
        w.println("[" + tag + "] " + f.getName() + " @ " + f.getEntryPoint()
                + "  size=" + f.getBody().getNumAddresses());
        try {
            DecompileResults r = di.decompileFunction(f, 90, monitor);
            if (r != null && r.decompileCompleted() && r.getDecompiledFunction() != null) {
                w.println(r.getDecompiledFunction().getC());
            } else {
                w.println("  <decompile failed: " + (r == null ? "null" : r.getErrorMessage()) + ">");
            }
        } catch (Exception e) {
            w.println("  <exception: " + e.getMessage() + ">");
        }
    }

    void scanTables() {
        // Look for runs of 256 distinct-ish bytes that resemble a permutation/CRC table.
        var mem = currentProgram.getMemory();
        for (var block : mem.getBlocks()) {
            if (!block.isInitialized() || block.isExecute()) continue;
            long start = block.getStart().getOffset();
            long end = block.getEnd().getOffset();
            for (long a = start; a + 256 < end; a += 64) {
                try {
                    byte[] buf = new byte[256];
                    mem.getBytes(toAddr(a), buf);
                    Set<Integer> uniq = new HashSet<>();
                    for (byte b : buf) uniq.add(b & 0xFF);
                    // a byte CRC/sbox table tends to be a permutation (256 unique) — flag high-uniqueness runs
                    if (uniq.size() >= 240) {
                        w.println(String.format("  0x%x: %d unique bytes in 256 (permutation-like)", a, uniq.size()));
                    }
                } catch (Exception ignore) {}
            }
        }
    }
}
