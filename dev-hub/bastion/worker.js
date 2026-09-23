import {makeAuthority} from "../specialists/core.js";
export default makeAuthority({role:"bastion",scope:"SECURITY_DATA",blockSeverities:["BLOCK","CRITICAL"],reviseSeverities:["WARNING"]});
