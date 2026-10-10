import { test } from "node:test";
import assert from "node:assert/strict";
import { snapshotFromResult, filterItems, summaries, leaseRemaining } from "./view.mjs";
test("unknown and expired leases never count as free",()=>{
  const items=[{lock:{state:"free"}},{lock:{state:"expired"}},{lock:{state:"unknown"}},{lock:{state:"unavailable"}}];
  assert.deepEqual(summaries(items,"locks"),[["Devices",4],["Free",1],["Held",0],["Expired / unknown",3]]);
});
test("countdown reaches elapsed without claiming the lock is free",()=>{
  assert.equal(leaseRemaining({state:"held",remainingSeconds:30},31),"Elapsed · refresh to verify");
  assert.equal(leaseRemaining({state:"expired"},0),"Expired · directory still present");
});
test("filter uses literal case-insensitive names, tasks, and serials",()=>{
  const items=[{name:"Pixel",serial:"emulator-5554"},{serial:"phone",lock:{task:"Login"}}];
  assert.deepEqual(filterItems(items,"LOGIN"),[items[1]]);assert.deepEqual(filterItems(items,"<script>"),[]);
});
test("duplicate running instances count one configured AVD",()=>{
  assert.equal(summaries([{name:"phone",configured:true,state:"online"},{name:"phone",configured:true,state:"online"}],"emulator")[0][1],1);
});
test("malformed and failed protocol snapshots are rejected",()=>{
  assert.throws(()=>snapshotFromResult({isError:true},"locks"));assert.throws(()=>snapshotFromResult({structuredContent:{adb:{}}},"emulator"));
});
