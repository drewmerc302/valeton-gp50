// FindCrcUser.java — find code that references the CRC-8/0x07 table at 0xf5f10
// and decompile those functions (the checksum routine) + their callers.
// @category Valeton
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class FindCrcUser extends GhidraScript {
    static final String OUT = "/Users/drewmerc/workspace/valeton/re/ghidra_crc_user.txt";
    static final long[] TABLE_ADDRS = {0xf5f10L, 0xf5f00L};

    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        PrintWriter w = new PrintWriter(new FileWriter(OUT));
        ReferenceManager rm = currentProgram.getReferenceManager();
        var fm = currentProgram.getFunctionManager();

        Set<Function> users = new LinkedHashSet<>();
        for (long ta : TABLE_ADDRS) {
            Address t = toAddr(ta);
            w.println("== refs to table @ " + t + " ==");
            // references TO the table address (and a window after it, since code may
            // compute base+offset)
            for (long off = 0; off < 0x100; off += 4) {
                Address a = toAddr(ta + off);
                for (Reference r : rm.getReferencesTo(a)) {
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    if (f != null) {
                        users.add(f);
                        w.println("  " + r.getFromAddress() + " (in " + f.getName() + ") -> +" + off);
                    }
                }
            }
        }
        // also scan whole program for instructions whose scalar operand == table base
        w.println("\n== functions referencing the table (decompiled) ==");
        Set<Function> all = new LinkedHashSet<>(users);
        // include callers so we see what data is fed in
        for (Function f : users) {
            for (Function c : f.getCallingFunctions(monitor)) all.add(c);
        }
        for (Function f : all) {
            w.println("\n----------------------------------------------------");
            w.println("FUNC " + f.getName() + " @ " + f.getEntryPoint()
                    + " size=" + f.getBody().getNumAddresses());
            try {
                DecompileResults r = di.decompileFunction(f, 90, monitor);
                if (r != null && r.getDecompiledFunction() != null)
                    w.println(r.getDecompiledFunction().getC());
                else
                    w.println("  <decompile failed>");
            } catch (Exception e) {
                w.println("  <ex: " + e.getMessage() + ">");
            }
        }
        w.close();
        println("wrote " + OUT + " (" + all.size() + " funcs)");
    }
}
