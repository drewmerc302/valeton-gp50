// FindRefit.java — locate + decompile the NAM->SnapTone refit (converThread.run()
// and threadEntryProc) in 5868USB.dylib, plus dump strings they reference (model hints).
// @category Valeton
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.StringDataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class FindRefit extends GhidraScript {
    static final String OUT = "/Users/drewmerc/workspace/valeton/re/ghidra_refit.txt";
    static final Set<String> LAUNCHERS = new HashSet<>(Arrays.asList(
        "_namConvertClo", "_namConvertCloData", "_appNamConvertClo", "_appNamConvertCloData"));
    DecompInterface di;
    PrintWriter w;
    Set<Long> dumped = new HashSet<>();

    public void run() throws Exception {
        di = new DecompInterface();
        di.openProgram(currentProgram);
        w = new PrintWriter(new FileWriter(OUT));
        var fm = currentProgram.getFunctionManager();
        var rm = currentProgram.getReferenceManager();

        // find the converThread data object address
        Address ct = null;
        for (Symbol s : currentProgram.getSymbolTable().getAllSymbols(true)) {
            if (s.getName().contains("converThread")) { ct = s.getAddress(); w.println("converThread @ " + s.getAddress() + " (" + s.getName() + ")"); break; }
        }
        Set<Function> refit = new LinkedHashSet<>();
        // threadEntryProc
        for (Function f : fm.getFunctions(true))
            if (f.getName().contains("threadEntryProc") || f.getName().contains("runThread")) refit.add(f);
        // functions referencing converThread object + the param slots stashed by the launcher
        if (ct != null) {
            for (long off : new long[]{0, 0x1d0, 0x1d8, 0x1e0, 0x1e8, 0x218, 0x220, 0x22c}) {
                for (Reference r : rm.getReferencesTo(ct.add(off))) {
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    if (f != null && !LAUNCHERS.contains(f.getName())) refit.add(f);
                }
            }
        }
        w.println("refit candidate functions: " + refit.size());
        for (Function f : refit) w.println("  " + f.getName() + " @ " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());

        // decompile candidates + their direct callees; dump strings referenced
        Set<Function> toDump = new LinkedHashSet<>(refit);
        for (Function f : refit)
            for (Function c : f.getCalledFunctions(monitor)) toDump.add(c);

        for (Function f : toDump) dumpFunc(f);

        // strings referenced anywhere in the refit candidates (model hints)
        w.println("\n== strings referenced by refit candidates ==");
        Set<String> seen = new TreeSet<>();
        for (Function f : refit) {
            for (Instruction ins : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                for (Reference r : ins.getReferencesFrom()) {
                    Data d = getDataAt(r.getToAddress());
                    if (d != null && d.hasStringValue()) {
                        String v = d.getDefaultValueRepresentation();
                        if (v != null && v.length() > 3) seen.add(v);
                    }
                }
            }
        }
        for (String s : seen) w.println("  " + s);

        w.close();
        println("wrote " + OUT + " (" + toDump.size() + " funcs)");
    }

    void dumpFunc(Function f) {
        if (!dumped.add(f.getEntryPoint().getOffset())) return;
        w.println("\n----------------------------------------------------");
        w.println("FUNC " + f.getName() + " @ " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());
        try {
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            if (r != null && r.getDecompiledFunction() != null) w.println(r.getDecompiledFunction().getC());
            else w.println("  <decompile failed>");
        } catch (Exception e) { w.println("  <ex: " + e.getMessage() + ">"); }
    }
}
