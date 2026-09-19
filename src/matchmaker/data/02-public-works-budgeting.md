# Brief 02: Public Works Budgeting and Adjudication
**Author(s):** Jonathan Accelnorm
**Problem:** Procurement Transparency  
**Entity:** Government of Córdoba Province / IERAL  
**Version:** 0.1

---

# Context

## Problem Statement
*Provided by BlockchainGov*
Public works contracting in the Government of Córdoba Province (and any provincial/national government) is vulnerable at key decision points (i.e., tender design, evaluation, awarding, cost adjustments). Documents are fragmented and editable, allowing favoritism, inflated budgets, and ex-post adjustments that lack transparency.

## Current Practices
- Fragmented and editable document systems
- No immutable audit trail
- Vulnerable to favoritism and budget inflation

# Assessment

## Executive Summary
Blockchain could provide an immutable, transparent, and accountable trail for the entire contracting process, from tender design to awarding, reducing corruption and waste.

## Need for Blockchain
Blockchain is particularly justified when:
- Key procurement and contract modification decisions are dispersed across multiple systems or offices, making ex-post reconstruction of the full history difficult or manipulable.
- There is a history or credible risk of document tampering (e.g., retroactive changes to tender specs, evaluation reports, or addenda) and distrust between implementing agencies, auditors, and citizens.
- Multiple independent actors (contracting authority, treasury, audit court, external monitors) need a **shared, tamper-evident log** of all steps, but cannot rely on a single IT operator as the arbiter of truth.
- The government wants to enable **public verification** of timelines and decisions (who did what, and when) without exposing sensitive internal data fields.

## Related, Existing Implementations

| Category | Solutions / Examples |
|----------|----------------------|
| Procurement & timestamping | Aon procurement on blockchain; Baseline Protocol; OpenTimestamps; World Bank Open Contracting pilots using blockchain anchoring for tenders and contracts |
| Construction management (off-chain, relevant stack) | Procore; PlanGrid; Oracle Construction and Engineering; Autodesk Construction Cloud — widely used project management and documentation tools that could feed data into an onchain audit layer |
| Public sector pilots | **WEF/IDB/Colombia Blockchain Pilot** — school meal procurement PoC with Procuraduría General; **Georgia/Bitfury Exonum** — blockchain timestamping for NAPR land registry (model for procurement audit trails); **BIM-Blockchain Digital Twin** — automated construction payments via smart contracts + IoT verification (reduces payment verification from days to minutes); **Infrastructure Tokenization** (World Bank research) — tokenizing infrastructure projects for democratized financing. Also explored by Mattereum. |

---

## Potential Blockchain Solutions

### Transparency & Audit Trails

| Concept | Description |
|---------|-------------|
| **End-to-end Public Spending Transparency Platform** | Blockchain enables the immutability of certain data, creates asset passports for public assets such as medical equipment and medicine lots, facilitates capital raising for public goods and co-investments with the province, and allows for citizen challenges to budgeting and public spending. |
| **Procurement Lifecycle Anchoring** | Every key document (tender specs, bid submissions, evaluation reports, award decisions, change orders) is hashed and timestamped onchain at creation; any subsequent modification becomes detectable; auditors and citizens can verify the complete procurement history without accessing sensitive bid details. |
| **Multi-Party Tender Commitment Protocol** | Bidders submit encrypted bids to a smart contract before deadline; bids are revealed simultaneously after deadline via threshold decryption; prevents last-minute bid manipulation and ensures all parties can verify fair timing. |

### Cost Control & Accountability

| Concept | Description |
|---------|-------------|
| **Smart Contract Cost Adjustment Limits** | Contract modification rules encoded in smart contracts; cost overruns beyond threshold (e.g., 15%) require multi-sig approval from treasury, audit court, and contracting authority; automatic alerts to oversight bodies when thresholds approach. |
| **Milestone-Based Payment Release** | Construction payments locked in escrow smart contracts; funds release automatically when IoT sensors or independent inspectors verify milestone completion (foundation poured, structure complete, etc.); reduces payment fraud and incentivizes timely completion. |
| **Contractor Performance Bonds Onchain** | Performance guarantees tokenized as onchain bonds; automatic slashing if project fails quality audits or timeline commitments; bond history creates verifiable contractor reputation across provinces. |

### Citizen Oversight & Participation

| Concept | Description |
|---------|-------------|
| **Citizen Watchdog DAO** | Community members stake tokens to participate in procurement oversight; verified irregularity reports earn rewards from slashed contractor bonds; creates economic incentive for citizen monitoring without requiring government resources. |
| **Public Works Progress NFTs** | Each major project mints progress NFTs with photos, inspection reports, and completion status; citizens can track projects in their neighborhood; creates public accountability and engagement with infrastructure investments. |
| **Participatory Infrastructure Prioritization** | Citizens vote onchain to prioritize which public works projects receive funding; quadratic voting prevents plutocracy; results are binding commitments anchored onchain for accountability. |

### Financing & Investment

| Concept | Description |
|---------|-------------|
| **Tokenized Municipal Infrastructure Bonds** | Public works projects funded via tokenized bonds; retail investors can participate with small amounts; smart contracts automate coupon payments and principal return; creates new funding source while increasing public investment in local infrastructure. |
| **Outcome-Linked Infrastructure Financing** | Bond yields tied to project outcomes (e.g., road quality metrics, usage data); investors earn more when infrastructure performs well; aligns incentives between financiers, contractors, and citizens. |

---

## Implementation

## Leadership Buy-in Strategy

**Potential Approaches:**
- Position as **'protection for honest officials'** — immutable records defend against future accusations
- Show **$ savings** from reduced cost overruns (e.g., 10-15% on inflated contracts)
- Reference successful implementations (e.g., Colombia, Georgia)
- Engage other institutions as allies, such as the Tribunal de Cuentas

**Recommended First Step:**  
Once procurement data and workflows are in a standard format, such as OCDS (Open Contracting Data Standard), add a blockchain timestamping layer for immutability and end-to-end audit trails. Pilot on high-visibility project with citizen oversight.