// FindRun.java — read AppNamConvertThread vtable @ 0x1884b8, decompile its methods
// (run() = the NAM->SnapTone refit) + callees 2 levels, dump strings/float consts.
// @category Valeton
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class FindRun extends GhidraScript {
    static final String OUT = "/Users/drewmerc/workspace/valeton/re/ghidra_run.txt";
    static final long VTABLE = 0x1884b8L;
    DecompInterface di;
    PrintWriter w;
    Set<Long> dumped = new HashSet<>();

    public void run() throws Exception {
        di = new DecompInterface();
        di.openProgram(currentProgram);
        w = new PrintWriter(new FileWriter(OUT));
        var fm = currentProgram.getFunctionManager();

        // read vtable entries
        w.println("== AppNamConvertThread vtable @ " + toAddr(VTABLE) + " ==");
        List<Function> methods = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            long ptr;
            try { ptr = getLong(toAddr(VTABLE + i * 8L)); } catch (Exception e) { break; }
            if (ptr == 0) continue;
            Address fa = toAddr(ptr & 0xffffffffffL);
            Function f = fm.getFunctionAt(fa);
            if (f == null) f = fm.getFunctionContaining(fa);
            w.println(String.format("  [%2d] %#x -> %s", i, ptr, f == null ? "?" : (f.getName() + " size=" + f.getBody().getNumAddresses())));
            if (f != null && !methods.contains(f)) methods.add(f);
        }

        // decompile each vtable method + callees to depth 2
        for (Function f : methods) dumpDeep(f, 2);

        w.println("\n== strings + notable float consts referenced ==");
        Set<String> strs = new TreeSet<>();
        for (Function f : methods) collectStrings(f, strs, 2, new HashSet<>());
        for (String s : strs) w.println("  " + s);

        w.close();
        println("wrote " + OUT);
    }

    void dumpDeep(Function f, int depth) {
        if (f == null || depth < 0) return;
        if (!dumped.add(f.getEntryPoint().getOffset())) return;
        int sz = (int) f.getBody().getNumAddresses();
        // skip tiny stubs
        if (sz <= 16) return;
        w.println("\n----------------------------------------------------");
        w.println("FUNC " + f.getName() + " @ " + f.getEntryPoint() + " size=" + sz + " depth=" + depth);
        try {
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            if (r != null && r.getDecompiledFunction() != null) w.println(r.getDecompiledFunction().getC());
        } catch (Exception e) { w.println("  <ex " + e.getMessage() + ">"); }
        try {
            for (Function c : f.getCalledFunctions(monitor)) dumpDeep(c, depth - 1);
        } catch (Exception ignore) {}
    }

    void collectStrings(Function f, Set<String> out, int depth, Set<Long> seen) {
        if (f == null || depth < 0 || !seen.add(f.getEntryPoint().getOffset())) return;
        for (Instruction ins : currentProgram.getListing().getInstructions(f.getBody(), true)) {
            for (Reference r : ins.getReferencesFrom()) {
                Data d = getDataAt(r.getToAddress());
                if (d != null && d.hasStringValue()) {
                    String v = d.getDefaultValueRepresentation();
                    if (v != null && v.length() > 3) out.add(v);
                }
            }
        }
        try { for (Function c : f.getCalledFunctions(monitor)) collectStrings(c, out, depth - 1, seen); } catch (Exception ignore) {}
    }
}
