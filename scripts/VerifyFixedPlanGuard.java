package org.c2smart.matsimnyc;
import java.nio.file.*;
import org.matsim.api.core.v01.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.controler.events.BeforeMobsimEvent;
public final class VerifyFixedPlanGuard {
 public static void main(String[] args) throws Exception {
  var s=ScenarioUtils.createScenario(ConfigUtils.createConfig());var f=s.getPopulation().getFactory();
  var p=f.createPerson(Id.createPersonId("fixture"));var plan=f.createPlan();
  var home=f.createActivityFromCoord("Home",new Coord(1,2));home.setEndTime(25200);plan.addActivity(home);plan.addLeg(f.createLeg("walk"));plan.addActivity(f.createActivityFromCoord("Home",new Coord(3,4)));p.addPlan(plan);s.getPopulation().addPerson(p);
  var file=Files.createTempFile("fixed-plan-guard-", ".json");
  try {
   var guard=new FixedPlanGuard(s,file.toString());plan.setScore(123.0);guard.notifyBeforeMobsim(new BeforeMobsimEvent(null,0,false));
   if(!Files.readString(file).contains("\"changed\":0"))throw new AssertionError("Score should not change semantic fingerprint");
   home.setEndTime(25201);boolean rejected=false;
   try {guard.notifyBeforeMobsim(new BeforeMobsimEvent(null,0,false));} catch(RuntimeException e){rejected=true;}
   if(!rejected||!Files.readString(file).contains("\"changed\":1"))throw new AssertionError("Changed plan must be rejected before mobsim");
  } finally {Files.deleteIfExists(file);}
  System.out.println("PASS: frozen guard ignores old scores and rejects activity time changes before traffic execution");
 }
}
