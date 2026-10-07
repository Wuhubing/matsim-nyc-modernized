package org.c2smart.matsimnyc;
import java.util.*;
import java.nio.file.*;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.gbl.MatsimRandom;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.replanning.*;
import org.matsim.core.replanning.choosers.*;
import org.matsim.api.core.v01.replanning.PlanStrategyModule;
import org.matsim.core.replanning.selectors.RandomPlanSelector;
import org.matsim.core.scenario.ScenarioUtils;
/** Synthetic checks for W2 (RecordingStrategyChooser) and W3 (TargetedInnovationChooser). */
public class VerifyReplanningChoosers {
 static PlanStrategy selector(){return new PlanStrategyImpl.Builder(new RandomPlanSelector<>()).build();}
 static PlanStrategy innovation(){return new PlanStrategyImpl.Builder(new RandomPlanSelector<>()).addStrategyModule(new PlanStrategyModule(){
  public void prepareReplanning(ReplanningContext c){} public void handlePlan(Plan p){} public void finishReplanning(){}}).build();}
 static StrategyChooser.Weights<Plan,Person> weights(List<PlanStrategy> s,double... w){
  return new StrategyChooser.Weights<>(){public int size(){return s.size();} public double getWeight(int i){return w[i];}
   public GenericPlanStrategy<Plan,Person> getStrategy(int i){return s.get(i);} public double getTotalWeights(){return Arrays.stream(w).sum();}};}
 static ReplanningContext context(int it){return ()->it;}
 public static void main(String[] args) throws Exception {
  var scenario=ScenarioUtils.createScenario(ConfigUtils.createConfig()); var pop=scenario.getPopulation();
  for(int i=0;i<1000;i++){var p=pop.getFactory().createPerson(Id.createPersonId("m"+i));PopulationUtils.putSubpopulation(p,"man");pop.addPerson(p);}
  for(int i=0;i<200;i++){var p=pop.getFactory().createPerson(Id.createPersonId("o"+i));PopulationUtils.putSubpopulation(p,"outside");pop.addPerson(p);}
  List<PlanStrategy> man=List.of(selector(),innovation(),innovation(),innovation()), outside=List.of(selector());
  var wMan=weights(man,.7,.1,.1,.1); var wOut=weights(outside,1); var wOff=weights(man,.7,0,0,0);
  // W2: recording draws nothing itself, so the delegate's choices and the RNG stream are unchanged.
  List<Object> plain=new ArrayList<>(), recorded=new ArrayList<>();
  MatsimRandom.reset(4711); var weighted=new WeightedStrategyChooser<Plan,Person>();
  for(int it=1;it<=5;it++){weighted.beforeReplanning(context(it));for(Person p:pop.getPersons().values())plain.add(weighted.chooseStrategy(p,PopulationUtils.getSubpopulation(p),context(it),p.getId().toString().startsWith("m")?wMan:wOut));}
  double nextPlain=MatsimRandom.getRandom().nextDouble();
  MatsimRandom.reset(4711); var rec=new RecordingStrategyChooser(new WeightedStrategyChooser<>());
  for(int it=1;it<=5;it++){rec.beforeReplanning(context(it));for(Person p:pop.getPersons().values()){var s=rec.chooseStrategy(p,PopulationUtils.getSubpopulation(p),context(it),p.getId().toString().startsWith("m")?wMan:wOut);recorded.add(s);
   if(!rec.names().get(rec.strategy(p.getId())).equals(s.toString()) || rec.innovative(rec.strategy(p.getId()))!=ReplanningUtils.isInnovativeStrategy(s))throw new AssertionError("recorded code");}}
  if(!plain.equals(recorded) || nextPlain!=MatsimRandom.getRandom().nextDouble())throw new AssertionError("recording changed the draws");
  System.out.println("PASS: recording chooser reproduces the default chooser's decisions and random stream over 5 iterations");
  // W3: realised budget, ranking, epsilon share, outside never targeted, switch-off.
  double[] prio=new double[Id.getNumberOfIds(Person.class)]; Arrays.fill(prio,Double.NaN); var r=new Random(1);
  for(Person p:pop.getPersons().values())prio[p.getId().index()]=r.nextDouble();
  var file=Files.createTempFile("priority",".csv"); var b=new StringBuilder("person_id,priority\n");
  for(Person p:pop.getPersons().values())b.append(p.getId()).append(',').append(prio[p.getId().index()]).append('\n'); Files.writeString(file,b);
  var targeted=new TargetedInnovationChooser(pop,TargetedInnovationChooser.fromFiles(file),0.1,4711); Files.delete(file);
  targeted.beforeReplanning(context(3)); int inno=0,top=0,outsideInno=0;
  List<Person> ranked=pop.getPersons().values().stream().map(p->(Person)p).filter(p->p.getId().toString().startsWith("m")).sorted(Comparator.comparingDouble((Person p)->prio[p.getId().index()]).reversed()).toList();
  Set<Id<Person>> best=new HashSet<>(); for(Person p:ranked.subList(0,270))best.add(p.getId());
  for(Person p:pop.getPersons().values()){boolean m=p.getId().toString().startsWith("m");var s=targeted.chooseStrategy(p,PopulationUtils.getSubpopulation(p),context(3),m?wMan:wOut);
   if(ReplanningUtils.isInnovativeStrategy(s)){if(m){inno++;if(best.contains(p.getId()))top++;}else outsideInno++;}
   if(ReplanningUtils.isInnovativeStrategy(s)!=targeted.marked(p.getId()))throw new AssertionError("marked agents must innovate, others select");}
  if(inno!=300||top!=270||outsideInno!=0||!targeted.budgets().equals(Map.of("man",300,"outside",0)))throw new AssertionError(inno+" "+top+" "+outsideInno+" "+targeted.budgets());
  System.out.println("PASS: targeted chooser marks exactly B = 300 of 1000 (270 highest priority + 30 random), outside never innovates");
  targeted.beforeReplanning(context(9)); int off=0;
  for(Person p:pop.getPersons().values())if(ReplanningUtils.isInnovativeStrategy(targeted.chooseStrategy(p,PopulationUtils.getSubpopulation(p),context(9),p.getId().toString().startsWith("m")?wOff:wOut)))off++;
  if(off!=0)throw new AssertionError("innovation after switch-off: "+off);
  System.out.println("PASS: with innovation weights at 0 (after the 80% switch-off) nobody innovates");
  // eps = 1: same decision distribution as the default (per-person innovation rate and strategy proportions).
  int iterations=400; var random=new TargetedInnovationChooser(pop,null,1.0,4711); var dflt=new WeightedStrategyChooser<Plan,Person>();
  Map<GenericPlanStrategy<Plan,Person>,Integer> cr=new HashMap<>(), cd=new HashMap<>(); int[] perPerson=new int[prio.length];
  MatsimRandom.reset(1);
  for(int it=0;it<iterations;it++){random.beforeReplanning(context(it));dflt.beforeReplanning(context(it));
   for(Person p:pop.getPersons().values()){if(!p.getId().toString().startsWith("m"))continue;
    var s=random.chooseStrategy(p,"man",context(it),wMan);cr.merge(s,1,Integer::sum);if(ReplanningUtils.isInnovativeStrategy(s))perPerson[p.getId().index()]++;
    cd.merge(dflt.chooseStrategy(p,"man",context(it),wMan),1,Integer::sum);}}
  double n=iterations*1000.;
  for(var s:man){double a=cr.getOrDefault(s,0)/n,d=cd.getOrDefault(s,0)/n;if(Math.abs(a-d)>0.005)throw new AssertionError(s+" "+a+" vs "+d);}
  var rates=ranked.stream().mapToDouble(p->perPerson[p.getId().index()]/(double)iterations).summaryStatistics();
  if(Math.abs(rates.getAverage()-0.3)>1e-9||rates.getMin()<0.2||rates.getMax()>0.4)throw new AssertionError(rates.toString());
  System.out.println("PASS: epsilon = 1 matches the default's strategy proportions within 0.005 and gives every agent an innovation rate near 0.3 ("+String.format("%.3f-%.3f",rates.getMin(),rates.getMax())+")");
 }
}
