# HOI4 Factory Optimizer

A tool for **Hearts of Iron IV** that looks at the divisions you want to train,
reads their actual equipment requirements, and works out how to allocate your
military factories so you can field those divisions as fast as possible — in a
balanced way that avoids bottlenecks.

It is designed to be **mod-agnostic**: it reads the *actual* equipment and
template definitions from your active game + mods rather than hard-coding a list
of equipment types, so it keeps working when equipment/units are added or changed
by mods.

## Status

🚧 Early setup. Architecture is being decided — see [`docs/DESIGN.md`](docs/DESIGN.md).

## The core goal

> When I set up any kind of division to train, analyze its equipment needs and
> fill them in a balanced manner that maximizes the number of divisions I can
> create, taking resource optimization into account.

## Important constraint (read this first)

Hearts of Iron IV mods are **declarative data/script**, not a general scripting
runtime. Crucially, **assigning military factories to production lines is a manual
player action** and HOI4 exposes **no modding hook** that fires when you queue a
division, reads that template's equipment shortfall, and reassigns factories on
the player's behalf. The AI production system (`common/ai_strategy*`) only steers
**AI-controlled countries**, not the human player's production screen.

So the "seamless, automatic, in-game" version of this idea is **not achievable as
a pure Workshop mod**. What *is* achievable is an **external companion tool** that
reads your game/mod data (and optionally a save) and tells you the optimal factory
allocation, which you then apply. See [`docs/DESIGN.md`](docs/DESIGN.md) for the
full analysis and the options.

## Layout (planned)

```
hoi4-factory-optimizer/
├── docs/            # design notes, constraint analysis, algorithm write-up
├── src/             # optimizer engine (once approach is confirmed)
└── data/            # sample template/equipment/save fixtures for testing
```
