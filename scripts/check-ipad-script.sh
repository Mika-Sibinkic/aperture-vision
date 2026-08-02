#!/usr/bin/env bash
# Verify the iPad script is actually runnable — not merely syntactically valid.
#
# `node --check` passes on a file whose functions have been deleted, which is exactly
# how three functions (chooseMode, runDonation, showHistory) reached the device and
# failed with "Can't find variable" in front of the user. Syntax checking is not
# enough; this loads the script under stubbed Scriptable globals and asserts every
# entry point resolves.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:-camera-access/ipad/aperture-pull.js}"
# Normalise to an absolute path: callers pass both relative and absolute.
case "$FILE" in /*) ABS="$FILE" ;; *) ABS="$PWD/$FILE" ;; esac

node --check "$ABS"
echo "syntax ......... ok"

for f in chooseMode runDonation showHistory selfTest finishAlert progressTable \
         grabFrame postToRelay withTimeout showResult showError resolveConfig \
         runSetup shrink withRetry readState writeState statePath headerLookup \
         md5 parseAuthHeader buildDigestAuth main; do
  grep -q "function $f(" "$ABS" || { echo "MISSING FUNCTION: $f"; exit 1; }
done
echo "definitions .... ok"

node -e '
const fs=require("fs"),vm=require("vm");
let src=fs.readFileSync(process.argv[1],"utf8").replace(/if \(typeof module !== "undefined".*?\n\}/s,"");
const noop=()=>{};const stub=new Proxy(function(){},{get:()=>stub,apply:()=>stub,construct:()=>stub});
const g={Alert:stub,UITable:stub,UITableRow:stub,Request:stub,Data:stub,Image:stub,DrawContext:stub,
 Size:stub,Rect:stub,UUID:{string:()=>"x".repeat(36)},Keychain:{contains:()=>true,get:()=>"v",set:noop},
 FileManager:{local:()=>({joinPath:(a,b)=>b,fileExists:()=>false,readString:()=>"{}",writeString:noop,libraryDirectory:()=>"/"})},
 Timer:{schedule:noop},Script:{complete:noop},config:{runsInApp:false},args:{},console,log:noop,logError:noop};
vm.createContext(g);
vm.runInContext(src+"\n;globalThis.__p=[chooseMode,runDonation,showHistory,selfTest,main].map(f=>typeof f);",g,{timeout:5000});
if(g.__p.some(t=>t!=="function")) { console.error("ENTRY POINT NOT A FUNCTION:",g.__p.join(",")); process.exit(1); }
' "$ABS"
echo "runtime load ... ok"

node -e '
const m=require(process.argv[1]);
if(m.md5("abc")!=="900150983cd24fb0d6963f7d28e17f72"){console.error("MD5 BROKEN");process.exit(1)}
const www="Digest realm=\"testrealm@host.com\", qop=\"auth\", nonce=\"dcd98b7102dd2f0e8b11d0f600bfb0c093\", opaque=\"x\"";
const r=m.buildDigestAuth("Mufasa","Circle Of Life","GET","/dir/index.html",www,"0a4f113b","00000001").match(/response="([0-9a-f]+)"/)[1];
if(r!=="6629fae49393a05397450978507c4ef1"){console.error("RFC 2617 DIGEST BROKEN");process.exit(1)}
' "$ABS"
echo "digest ......... ok"
echo "PASS — safe to generate and transfer"
