# R10K CPU Architecture Report

## Introduction

This document provides a detailed walkthrough of the R10K CPU, its control/data paths, and behaviors under different settings. The design borrows the major R10K ideas (register renaming, active list, issue queues).

## High-Level Microarchitecture

- Single-issue frontend feeding an out-of-order scheduler with in-order retirement. One instruction is decoded each cycle and can be issued to the ALU or LSU when operands are ready.

- Resources (see `main.py`): 32-entry Active List (ROB), 32-entry ALU queue, 32-entry LSQ, 64 physical integer registers, 32 architectural registers (64 = 32 + 32, 32 for renaming).

- ISA coverage: RV32I ALU ops **w/o** `Store Byte` and `Store Half` support.

## Behaviors

### Frontend, Prediction, and Speculation

- **Branch prediction** (`downstreams/predictor.py`): the current build wires an `AlwaysBranchPredictor`, so conditional branches are predicted taken. Prediction feeds `fetcher_impl` so taken branches fetch from PC+imm, otherwise PC+4.

- **Speculation tracking & Flushing** (`downstreams/speculation_state.py`): decoder sets `into_speculating` on a decoded branch; it blocks decoding further branches while speculating. Speculation ends when the branch at the Active List head retires. Commit raises `flush_recover` on mispredicts and always flushes on jumps (JAL/JALR). Fetcher receives `FetcherFlushEntry` to redirect PC. All queues (Active List, ALUQ, LSQ) clear on flush, and renaming structures restore committed state.

### Flush Handling

- **MapTable** (`downstreams/map_table.py`): packed table holding speculative and committed logical->physical mappings. Rename writes update the speculative table; on flush it is reset to the committed table. Commit writes install architectural mappings. Inside the downstream, we have seperated `_spec_table` and `_committed_table` (_spec_table holds the speculative mappings, commit_table holds the committed mappings). When flushing, we write the whole committed table back to the spec_table to restore the state.

  **Design considerations for MapTable**:
  - We only keep **1 level of speculation** (with only 1 _spec_table). Nested speculation would stall further branches until the current speculation resolves.
  - Because it is too expensive to have 32 external write ports to write the map_table simultaneously when flushing, we design the map table as a single 192 Bits (32 * 6 Bits) wide register, and write back the whole committed table would only require 1 write external port.

- **FreeList** (`downstreams/free_list.py`): circular queue of free physical registers (excluding x0). Snapshot of the head is taken when entering speculation; on flush it restores the head/count to reclaim wrong-path allocations.

- **RegisterReady** (`downstreams/register_ready.py`): packed readiness bits. Dest registers are marked not-ready at decode; ALU and WriteBack mark them ready on completion. On flush all bits reset to ready to match the rolled-back map table. Similar to MapTable, as we need to write 64 * Bits(1)(1) to set all the registers ready when flushing, **we design the register ready as a single 64 Bits wide register**, and write back all the bits to Int(64)(-1) when flushing.

### Queues

- **Active List (ROB)** (`downstreams/active_list.py`): holds PC, dest logical/physical pairs, old mapping, immediate, branch metadata, and readiness. Stores and EBREAK are marked ready on insertion; others are marked ready by ALU/WriteBack. Provides `set_ready` to update branch outcome or JALR target.

- **ALU Queue** (`downstreams/alu_queue.py`): accepts ALU-tagged ops, tracks issued bit, and selects the first valid entry whose required operands are ready per `RegisterReady`. Sources are resolved via `operant*_from` selectors (RS1/RS2/IMM/PC/4). Only one instruction issues per cycle.

- **LSQ + Store Buffer** 
  Loads cannot pass an older valid store in the LSQ selection scan.

  - **LSQ** holds both loads and stores. Scheduler only selects loads that are ready on RS1, unissued, and not blocked by an older valid store (enforced by a `seen_store` scan). `pop_enable` from commit removes the head entry; stores are copied into a single-entry store buffer on commit to be executed after architectural retirement.

  - **Store buffer**: one-entry `RegArray` (`main.py` + `modules/scheduler.py`). Gives priority to committed stores; cleared once scheduled.

  **Why we design it this way to have a `Store Buffer` instead of just having the store in the LSQ?**
  In our design, store instruction is executed only when it is committed. When commiting, we pop the store from the LSQ and active list. If we do not have a store buffer, we need to keep it in LSQ and pop it next cycle, which means we need to have a way to mark the store in LSQ as committed but not pop it yet. This would complicate the LSQ design. 

### Scheduling & Execution

- **Scheduler** (`modules/scheduler.py`, `downstreams/scheduler_down.py`): arbitrates ALU and LSU issues each cycle. Marks queue entries issued before invoking functional units. Flush prevents new issues but does not explicitly clear the store buffer.

- **ALU** (`modules/alu.py`): implements RV32I ALU ops, SLT/SLTU comparisons, shifts, and branch condition evaluation. Computes `branch_taken` as (result != 0) xor `branch_flip`. JALR writes PC+4 to rd and also passes the computed target back to the Active List.

- **LSU & WriteBack** 
  As SRAM has 1-cycle latency, loads complete in the WriteBack stage while ALU do not need WriteBack.

  - **LSU** (`modules/lsu.py`): computes address = rs1 + imm, word-aligned by dropping low 2 bits. Uses memory’s synchronous read/write interface; loads are marked active when `is_load` and valid, stores when committed (`is_store` and valid).

  - **WriteBack** (`modules/writeback.py`): on load completion, extracts byte/half/word and sign/zero-extends per `op_type`; writes to the physical register file and marks ready. Also marks the corresponding Active List entry ready. Stores do nothing in writeback because they were already committed.

## What could be improved

- Prediction is fixed to “always taken”.

- Only one speculative branch is allowed.

- Only support full-word stores; add byte/half support.

## Architectural Graphs

### Frontend, Prediction, and Speculation
```text
Frontend / Fetch / Speculation
    +---------------------+            +------------------+
    | Commit flush_recover|--flush-->--| FetcherImpl/PC   |
    |  (PC+imm / PC+4)    |            |  (PC_reg[0])     |
    +---------------------+            +---------+--------+
                                               PC|
                                                 v
                                       +------------------+
                                       | Instruction SRAM |
                                       +---------+--------+
                                             dout|
                                                 v
    +--------------+      predict_branch      +---------+
    | Predictor    |<------------------------>| Decoder |
    | (AlwaysTake) |                          | (1-wide)|
    +--------------+                          +----+----+
```

### Rename, Issue, Execute
```text
Decode/Rename -> Issue -> Execute -> Commit

            +---------+    alloc      +----------+        mark not-ready
            | FreeList|<--------------| Decoder  |----------------------+
            +----+----+               +----+-----+                      |
                 ^                         |                            |
                 | commit free             | rename (spec map)          |
            +----+----+               +----+-----+                      |
            | Commit |--------------->| MapTable |<---------------------+
            +----+----+               +----+-----+    mark ready (ALU/WB)
                 |                         |                            |
                 | push ROB entry          |                            v
                 v                         v                     +-------------+
           +-----------+            +------------+               | RegisterReady|
           | ActiveList|<-----------| Decoder    |               +------+------+
           +--+-----+--+            +------------+                      |
              |     |                                                   |
              |pop  |push                                              read
              v     v                                                   |
  +------------+   +------------+                             +---------+------+
  | ALU Queue  |   |    LSQ     |                             | Physical Regs |
  | (32)       |   |   (32)     |                             |    64x32      |
  +------+-----+   +------+-----+                             +---------------+
         |                |
         |issue ready     |issue load (no older store)
         v                v
     +---------+     +---------+
     |  ALU    |     |  LSU    |
     +----+----+     +----+----+
          |               |
          | rd/branch     | load data
          v               v
     +---------+     +-----------+
     | RegFile |<----| WriteBack |
     +----+----+     +-----------+
```

### Memory Ordering
```text
Memory ordering
    LSQ
     | scan: pick first ready LOAD with no older valid store
     v
  Data SRAM <---- Store Buffer (1 entry, holds committed store)
     |
     v
  WriteBack --> RegFile + RegisterReady + ActiveList.ready
```
