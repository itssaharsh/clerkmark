# Clerkmark — demo script (120s)

**hook** `0:00.0` When someone without a lawyer files a brief written with a chatbot, court staff look up every case by hand. [[0.4]] They are never sure whether a missing case is fake, or simply not in the free database.

**problem** `0:14.0` Two thousand seventy-nine court decisions so far, more than half of them from people representing themselves. [[0.3]] Clerkmark fixes that at the intake desk.

**run** `0:24.9` Drop the filing, and Clerkmark checks every citation against a free law library. [[0.4]] Twenty-three citations, classed in seconds, each with the rule that decided it printed under the row.

**rows** `0:37.5` Line eight is likely not a real case: page 366 belongs to Greenleaf v. Garlock, and no case named Miller sits in that volume. [[0.3]] Line nine is different: a state slip citation the free library cannot check. A naive checker prints the same not found for both.

**page** `0:58.4` The evidence is one click away. The page line six cites belongs to J.D. v. Azar, and the reporter's own record says so, with links to the free files.

**quote** `1:10.5` Real case, wrong quote. On line sixteen the memo underlines the passage, marks the words that differ, and shows the closest text in the opinion.

**eval** `1:21.1` Twenty citations with known answers, scored on every run. [[0.3]] Twenty of twenty right, and zero real cases called fake. That last number is the promise.

**tech** `1:33.2` Underneath, eyecite finds the citations, the Caselaw Access Project's free files supply every volume, page and opinion, a deterministic rule decides the class, and an optional model only advises. Statutes, short forms and pin pages stay out of scope, and the memo says so.

**end** `1:53.7` Clerkmark. A triage aid, not a finding. Repo and live link in the description.

