#!/usr/bin/env node
import fs from "node:fs";
import {evaluateAuthorityVerdict} from "../specialists/core.js";

const input=JSON.parse(fs.readFileSync(0,"utf8"));
const config={
  role:String(input.role||""),
  scope:String(input.scope||""),
  blockSeverities:Array.isArray(input.block_severities)?input.block_severities:[],
  reviseSeverities:Array.isArray(input.revise_severities)?input.revise_severities:[]
};
const event=(severity)=>({severity});
const cases={
  unverified:evaluateAuthorityVerdict(config,[],false),
  no_evidence:evaluateAuthorityVerdict(config,[],true),
  info:evaluateAuthorityVerdict(config,[event("INFO")],true),
  warning:evaluateAuthorityVerdict(config,[event("WARNING")],true),
  block:evaluateAuthorityVerdict(config,[event("BLOCK")],true),
  critical:evaluateAuthorityVerdict(config,[event("CRITICAL")],true)
};
process.stdout.write(JSON.stringify({
  schema:"chacha.dev/specialist-authority-benchmark/v1",
  role:config.role,scope:config.scope,cases
})+"\n");
