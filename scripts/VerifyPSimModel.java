package org.c2smart.matsimnyc;
import java.nio.file.*;
import java.util.*;
/** Parity of the Java tree evaluator with scikit-learn on exported sample rows. Usage: MODEL (expects MODEL.parity.csv) */
public final class VerifyPSimModel {
 public static void main(String[] args) throws Exception {
  var model=NycPSim.Correction.load(Path.of(args[0]));
  var parity=Path.of(args[0].replaceAll("\\.txt$",".parity.csv"));
  double worst=0;int n=0;
  for(String line:Files.readAllLines(parity)){
   double[] v=Arrays.stream(line.split(",")).mapToDouble(Double::parseDouble).toArray();
   double got=model.predict(Arrays.copyOf(v,7));worst=Math.max(worst,Math.abs(got-v[7]));n++;
  }
  if(worst>1e-9)throw new AssertionError("max abs difference "+worst);
  System.out.println("PASS: Java correction matches scikit-learn on "+n+" rows (max abs diff "+worst+")");
 }
}
